"""Diálogo que propone el préstamo antes de confirmar el pedido (PRP D5.1, §7.0 paso 2).

Aquí es donde de verdad se reserva, y por eso aquí es donde está el bloqueo de concurrencia
(§5.6) y el **recálculo desde cero**. Lo que enseñó el paso 1 son números de hace unos
segundos: entre medias ha podido pasar cualquier cosa.
"""

from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class EntezaPrestamoConfirm(models.TransientModel):
    _name = 'enteza.prestamo.confirm'
    _description = 'Confirmar pedido con préstamo entre compañías'

    order_id = fields.Many2one('sale.order', string='Pedido', required=True, readonly=True)
    line_ids = fields.One2many(
        'enteza.prestamo.confirm.line', 'wizard_id', string='Material que falta',
    )
    todo_cubierto = fields.Boolean(compute='_compute_resumen')
    nada_cubierto = fields.Boolean(compute='_compute_resumen')

    @api.depends('line_ids.qty_falta', 'line_ids.qty_prestable')
    def _compute_resumen(self):
        for asistente in self:
            lineas = asistente.line_ids
            asistente.todo_cubierto = all(
                linea.qty_prestable >= linea.qty_falta for linea in lineas
            )
            asistente.nada_cubierto = not any(linea.qty_prestable > 0 for linea in lineas)

    # ------------------------------------------------------------------
    # Aceptar (paso 2 del §7.0)
    # ------------------------------------------------------------------

    def action_confirmar(self):
        """Bloquea, recalcula, reserva y confirma. En ese orden y sin saltarse ninguno."""
        self.ensure_one()
        pedido = self.order_id

        # 1) Bloqueo. A partir de aquí nadie más puede reservar estos productos hasta que
        #    esta transacción termine.
        pedido._enteza_bloquear_productos(self.line_ids.product_id)

        # 2) Recálculo. Los campos son calculados no almacenados, pero el ORM los tiene
        #    cacheados de cuando se montó la propuesta: hay que tirar la caché o se
        #    reservaría con las cifras viejas, que es justo lo que este paso evita.
        lineas_pedido = self.line_ids.sale_line_id
        lineas_pedido.invalidate_recordset([
            'enteza_falta', 'enteza_prestable_otra', 'enteza_almacen_prestamista_id',
        ])

        empeorado = self._enteza_comprobar_propuesta()
        if empeorado:
            raise UserError(_(
                'Mientras decidías, otro pedido se ha llevado parte del material y esta '
                'propuesta ya no vale:\n\n%(detalle)s\n\n'
                'No se ha reservado nada y el pedido sigue sin confirmar. Vuelve a '
                'confirmarlo para ver la propuesta actualizada.',
                detalle='\n'.join(empeorado),
            ))

        # 3) Reserva. Si algo falla aquí, la excepción tumba la transacción entera y el
        #    pedido tampoco se confirma: nunca queda un pedido confirmado sin su préstamo.
        self._enteza_crear_prestamos()

        # 4) Confirmación, ya con permiso.
        pedido.with_context(enteza_prestamo_aceptado=True).action_confirm()

        return {'type': 'ir.actions.act_window_close'}

    def _enteza_comprobar_propuesta(self):
        """Devuelve la lista de líneas en las que la situación ha EMPEORADO.

        El criterio es lo que queda sin cubrir, no lo que se presta. Si el déficit ha bajado
        —porque se canceló otro pedido— la propuesta sigue siendo buena aunque los números
        no coincidan: se reservará menos, y eso no es un problema. Lo que no puede pasar es
        que el comercial acepte creyendo que queda cubierto y acabe con un agujero mayor.
        """
        self.ensure_one()
        avisos = []
        for linea in self.line_ids:
            venta = linea.sale_line_id
            residual_propuesto = max(0.0, linea.qty_falta - linea.qty_prestable)
            residual_ahora = max(0.0, venta.enteza_falta - venta.enteza_prestable_otra)
            redondeo = venta.product_uom_id.rounding
            if float_compare(residual_ahora, residual_propuesto,
                             precision_rounding=redondeo) > 0:
                avisos.append(_(
                    '· %(producto)s: quedarían %(ahora)s sin cubrir en vez de %(antes)s',
                    producto=linea.product_id.display_name,
                    ahora=residual_ahora, antes=residual_propuesto,
                ))
        return avisos

    def _enteza_crear_prestamos(self):
        """Deja el material reservado en firme, **acumulando en el préstamo del viaje**.

        🔴 Un préstamo es **un viaje**, no un pedido. Si ya hay uno abierto para la misma
        ruta y la misma fecha de traslado, el material nuevo se le añade en vez de crear otro
        documento: dos eventos del mismo día que necesiten material de la otra compañía
        tienen que ir en el mismo porte y generar **un solo par de albaranes** (decisión del
        cliente, 2026-08-02; el §7.2 del PRP ya lo pedía para el análisis por lotes y el
        camino de la confirmación no lo había heredado).

        Se agrupa por **almacén de origen y fecha de traslado exacta**. Un evento del sábado
        y otro del domingo dan fechas distintas y son, por tanto, dos viajes.
        """
        self.ensure_one()
        pedido = self.order_id
        Prestamo = self.env['enteza.stock.loan']
        por_viaje = defaultdict(list)
        for linea in self.line_ids:
            # Las líneas que nadie puede cubrir no generan préstamo. No es un olvido: el
            # pedido se confirma igual (PENDIENTE-8) y el déficit se queda a la vista en el
            # widget de la línea.
            if not linea.warehouse_src_id or linea.qty_prestable <= 0:
                continue
            fecha = Prestamo._fecha_traslado_de(linea.sale_line_id.start_date)
            por_viaje[(linea.warehouse_src_id, fecha)].append(linea)

        # 🔴 `sudo()` para crear el préstamo. Quien confirma un pedido es un comercial, y no
        # tiene por qué pertenecer a los grupos de préstamos —hoy, de hecho, no los tiene
        # nadie salvo `admin`—. Sin esto, confirmar un pedido con déficit reventaría con un
        # error de permisos que no dice nada del problema real.
        #
        # No es un agujero: el usuario ya ha pasado por el diálogo y ha dado el permiso que
        # pide D5.1, y lo único que se crea es un documento en `reserved`, que no mueve
        # material. El traslado físico sigue exigiendo el grupo de responsable.
        #
        # Efecto secundario a tener presente: el préstamo se crea, pero para VERLO en el menú
        # hace falta el grupo de usuario de préstamos.
        prestamos = Prestamo.sudo()
        for (almacen_origen, fecha), lineas in por_viaje.items():
            vals_lineas = [self._enteza_vals_linea(linea) for linea in lineas]
            abierto = self._enteza_prestamo_abierto(almacen_origen, fecha)
            if abierto:
                # Ya hay un viaje programado para esa ruta y ese día: se sube al mismo.
                abierto.incorporar(vals_lineas, pedido=pedido)
                prestamos |= abierto
                continue

            prestamo = Prestamo.sudo().create({
                'company_id': almacen_origen.company_id.id,
                'company_dest_id': pedido.company_id.id,
                'warehouse_src_id': almacen_origen.id,
                'warehouse_dest_id': pedido.warehouse_id.id,
                'date_transfer': fecha,
                'origin': 'confirmation',
                'origin_order_ids': [(4, pedido.id)],
                'line_ids': [(0, 0, vals) for vals in vals_lineas],
            })
            # `action_reservar` es quien pone `date_reserved` —el criterio de prioridad— y
            # revalida la disponibilidad contra el motor, ya bajo el bloqueo: es la última
            # red antes de comprometer material.
            prestamo.action_reservar()
            prestamos |= prestamo
        return prestamos

    def _enteza_vals_linea(self, linea):
        """Valores de una línea de préstamo a partir de una línea de la propuesta."""
        venta = linea.sale_line_id
        return {
            'product_id': linea.product_id.id,
            'product_uom_id': venta.product_uom_id.id,
            # Se reserva lo que la otra compañía puede dar AHORA, no lo que decía la
            # propuesta: si el déficit ha bajado, se coge menos.
            'qty_proposed': min(venta.enteza_falta, venta.enteza_prestable_otra),
            'date_from': venta.start_date,
            'date_to': venta.return_date,
            'sale_line_id': venta.id,
            'deficit_date': venta.start_date,
        }

    def _enteza_prestamo_abierto(self, almacen_origen, fecha):
        """Préstamo vivo para esa ruta y esa fecha de traslado, si lo hay.

        Se buscan solo los `reserved` y `approved`. Un `draft` es trabajo a medias de otra
        persona y no se toca; y desde `in_transit` el camión ya salió, así que lo que llegue
        después necesita un viaje nuevo por fuerza.

        `sudo()` porque el documento pertenece a la compañía prestamista: sin él, un
        comercial de la receptora no encontraría el préstamo abierto y se crearía un segundo
        documento para el mismo viaje, que es justo lo que esto evita.
        """
        return self.env['enteza.stock.loan'].sudo().search([
            ('warehouse_src_id', '=', almacen_origen.id),
            ('warehouse_dest_id', '=', self.order_id.warehouse_id.id),
            ('date_transfer', '=', fecha),
            ('state', 'in', ('reserved', 'approved')),
        ], order='id', limit=1)

    def action_cancelar(self):
        """Cerrar sin hacer nada. El pedido se queda sin confirmar."""
        return {'type': 'ir.actions.act_window_close'}


class EntezaPrestamoConfirmLine(models.TransientModel):
    _name = 'enteza.prestamo.confirm.line'
    _description = 'Línea de la propuesta de préstamo'

    wizard_id = fields.Many2one(
        'enteza.prestamo.confirm', required=True, ondelete='cascade',
    )
    sale_line_id = fields.Many2one('sale.order.line', string='Línea de pedido', required=True)
    product_id = fields.Many2one('product.product', string='Producto', readonly=True)
    qty_pedida = fields.Float(string='Pedidas', readonly=True,
                              digits='Product Unit of Measure')
    qty_falta = fields.Float(string='Faltan', readonly=True,
                             digits='Product Unit of Measure')
    qty_prestable = fields.Float(string='Se prestan', readonly=True,
                                 digits='Product Unit of Measure')
    warehouse_src_id = fields.Many2one(
        'stock.warehouse', string='Desde', readonly=True,
    )
    qty_sin_cubrir = fields.Float(
        string='Sin cubrir', compute='_compute_qty_sin_cubrir',
        digits='Product Unit of Measure',
    )

    @api.depends('qty_falta', 'qty_prestable')
    def _compute_qty_sin_cubrir(self):
        for linea in self:
            linea.qty_sin_cubrir = max(0.0, linea.qty_falta - linea.qty_prestable)
