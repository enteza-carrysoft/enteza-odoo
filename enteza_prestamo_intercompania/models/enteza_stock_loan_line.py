from datetime import timedelta

from odoo import api, fields, models


class EntezaStockLoanLine(models.Model):
    _name = 'enteza.stock.loan.line'
    _description = 'Línea de préstamo entre compañías'

    loan_id = fields.Many2one(
        'enteza.stock.loan', string='Préstamo', required=True, ondelete='cascade', index=True,
    )
    company_id = fields.Many2one(related='loan_id.company_id', store=True, index=True)
    state = fields.Selection(related='loan_id.state', store=True, index=True)
    # Almacenado porque el cálculo de disponibilidad filtra por almacén de origen en cada
    # confirmación de pedido: atravesar la cabecera en el dominio lo haría inviable.
    warehouse_src_id = fields.Many2one(
        related='loan_id.warehouse_src_id', store=True, index=True,
        string='Almacén de origen',
    )

    product_id = fields.Many2one(
        'product.product', string='Producto', required=True, index=True,
    )
    product_uom_id = fields.Many2one(
        'uom.uom', string='Unidad de medida',
        help='Las cantidades se guardan en la unidad de referencia del producto, igual '
             'que hace el cálculo nativo de alquiler con `product_uom_qty`. El caso de '
             'artículos gestionados en otra unidad (docenas) está pendiente y hay que '
             'resolverlo a la vez aquí y en el motor de disponibilidad.',
    )

    qty_proposed = fields.Float(string='Cantidad propuesta', digits='Product Unit of Measure')
    qty_reserved = fields.Float(
        string='Cantidad reservada', digits='Product Unit of Measure',
        help='Reservada en firme en la compañía prestamista. Es la cantidad que alimenta '
             '`prestado_a_terceros` en el cálculo de disponibilidad.',
    )
    qty_approved = fields.Float(string='Cantidad aprobada', digits='Product Unit of Measure')
    qty_sent = fields.Float(
        string='Cantidad trasladada', digits='Product Unit of Measure', readonly=True,
    )
    qty_returned = fields.Float(
        string='Cantidad devuelta', digits='Product Unit of Measure', readonly=True,
    )
    qty_pending = fields.Float(
        string='Pendiente de devolver', digits='Product Unit of Measure',
        compute='_compute_qty_pending', store=True,
    )

    # 🔴 Intervalo que ocupa la reserva. Sin él no se puede calcular `prestado_a_terceros`
    # por fecha y la reserva bloquearía el material indefinidamente (PRP §5.5).
    date_from = fields.Datetime(string='Reservado desde', required=True, index=True)
    date_to = fields.Datetime(string='Reservado hasta', required=True)

    sale_line_id = fields.Many2one(
        'sale.order.line', string='Línea de pedido', index=True, ondelete='set null',
        help='Línea de alquiler que motivó el préstamo. Permite liberar la reserva si el '
             'pedido se reduce o se cancela.',
    )
    deficit_date = fields.Date(string='Fecha del déficit')

    # Índice compuesto para el cálculo de `prestado_a_terceros`, que se ejecuta en cada
    # confirmación de pedido y tiene que resolverse rápido (PRP §6.3). Los índices por campo
    # suelto no sirven aquí: el dominio filtra siempre por los cuatro a la vez.
    #
    # Declarativo con `models.Index`, que es la forma de la 19 (ver
    # `stock.move.line._free_reservation_index`). Sustituye al `_auto_init` con
    # `tools.create_index` de la versión anterior: el ORM se encarga de crearlo y de
    # retirarlo si el modelo cambia, y no depende de que `create_index` siga expuesto en el
    # espacio de nombres `odoo.tools`, que en la 19 se ha reorganizado.
    _producto_intervalo_idx = models.Index(
        '(product_id, warehouse_src_id, date_from, date_to)',
    )

    @api.depends('qty_sent', 'qty_returned')
    def _compute_qty_pending(self):
        for linea in self:
            linea.qty_pending = linea.qty_sent - linea.qty_returned

    def _calcular_devolucion(self):
        """Cuánto de lo prestado conviene devolver y cuánto retener (PRP §7.5).

        Es el cálculo que el cliente pidió por su nombre. La idea: no devolver material que
        la receptora va a volver a necesitar dentro de unos días, porque haría falta un viaje
        de ida y otro de vuelta para nada.

            ventana  = hoy .. hoy + N días        (parámetro, 7 por defecto)
            necesita = pico de demanda de la receptora en la ventana
            propio   = lo que hay en su almacén MENOS lo que tiene prestado sin devolver
            retener  = min(pendiente, max(0, necesita - propio))
            devolver = pendiente - retener

        Ejemplo del cliente: prestadas 100, necesita 30 y no le llega con lo suyo →
        retener 30, devolver 70.

        🔴 **Si la prestamista también lo necesita, su necesidad manda** (`[PENDIENTE-5]`):
        es su material. La retención se recorta en lo que le falte a ella, y las dos cifras
        se devuelven para que el responsable vea por qué.

        Devuelve un diccionario; **no escribe nada**. La devolución es una propuesta que
        aprueba una persona (D2).
        """
        self.ensure_one()
        prestamo = self.loan_id
        motor = self.env['enteza.disponibilidad'].sudo()
        pendiente = self.qty_pending

        dias = prestamo._parametro('ventana_retencion', 7)
        desde = fields.Datetime.now()
        hasta = desde + timedelta(days=dias)

        producto = self.product_id.sudo()
        almacen_dest = prestamo.warehouse_dest_id.sudo()
        almacen_src = prestamo.warehouse_src_id.sudo()

        necesita = motor.comprometido(producto, almacen_dest, desde, hasta)[producto.id]
        # Lo prestado está físicamente en la receptora y cuenta en su parque: hay que
        # descontarlo para saber con cuánto se defiende ella sola.
        propio = motor.parque(producto, almacen_dest)[producto.id] - pendiente
        retener = min(pendiente, max(0.0, necesita - propio))

        necesita_src = motor.comprometido(producto, almacen_src, desde, hasta)[producto.id]
        falta_src = max(0.0, necesita_src - motor.parque(producto, almacen_src)[producto.id])
        retener_ajustado = max(0.0, retener - falta_src)

        return {
            'linea_id': self.id,
            'pendiente': pendiente,
            'necesita_receptora': necesita,
            'propio_receptora': propio,
            'necesita_prestamista': falta_src,
            'retener': retener_ajustado,
            'devolver': pendiente - retener_ajustado,
        }

    def _enteza_cancelar_movimientos(self):
        """Cancela los movimientos de stock que dependen de estas líneas.

        Hay que llamarlo **antes** de borrar la línea: el enlace del movimiento es
        `ondelete='set null'`, así que un borrado a secas dejaría un movimiento huérfano que
        seguiría sacando material del almacén sin que nada lo relacionara con nada.
        """
        if not self:
            return
        movimientos = self.env['stock.move'].sudo().search([
            ('enteza_loan_line_id', 'in', self.ids),
        ])
        movimientos.filtered(
            lambda mov: mov.state not in ('done', 'cancel')
        )._action_cancel()

    def _qty_comprometida(self):
        """Cantidad que esta línea compromete en la compañía prestamista.

        Mientras está en `reserved` manda lo reservado; una vez aprobada manda lo que
        autorizó el responsable, que puede haber ajustado la cantidad a la baja.
        """
        self.ensure_one()
        if self.loan_id.state == 'approved' and self.qty_approved:
            return self.qty_approved
        return self.qty_reserved
