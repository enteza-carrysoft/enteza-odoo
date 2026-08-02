"""Análisis por lotes: la red de seguridad (PRP §7.1 y §6.5).

Con D5, casi todos los déficits se detectan y se cubren al confirmar el pedido. Este proceso
es para lo que se escapa de ese camino:

- **Ampliar un pedido ya confirmado**, que hoy no vuelve a pasar por el diálogo. Es el hueco
  conocido del módulo, y esta es la red que lo recoge.
- Material que no vuelve a tiempo de un préstamo anterior.
- Cambios de fecha, cancelaciones que liberan stock, préstamos que se marcan para revisión.

🔴 **El cron no crea préstamos ni mueve nada. Solo analiza.** Lo que hace es dejar a la vista
lo que ya no cuadra, para que una persona decida. Es la misma regla de todo el módulo.

Rendimiento
-----------
El §15 pedía 1.000 productos en menos de 30 segundos y el motor no da para eso: hace una
búsqueda por producto. La salida no es optimizar el motor —eso rompería la coherencia con las
cifras del nativo— sino **mirar solo donde puede haber algo**: los productos con demanda de
alquiler confirmada dentro del horizonte. En una temporada normal eso es una fracción del
catálogo, y el resto no puede tener déficit por definición.
"""

import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class EntezaStockDeficit(models.Model):
    _name = 'enteza.stock.deficit'
    _description = 'Déficit de material de alquiler detectado por el análisis'
    _order = 'date_from, id'

    product_id = fields.Many2one(
        'product.product', string='Producto', required=True, index=True, ondelete='cascade',
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse', string='Almacén', required=True, index=True, ondelete='cascade',
    )
    company_id = fields.Many2one(
        related='warehouse_id.company_id', store=True, index=True,
    )
    date_from = fields.Datetime(string='Desde', required=True, index=True)
    date_to = fields.Datetime(string='Hasta', required=True)

    qty_deficit = fields.Float(
        string='Falta', required=True, digits='Product Unit of Measure',
    )
    qty_cubrible = fields.Float(
        string='Puede prestarse', digits='Product Unit of Measure',
        help='Lo que otra compañía del grupo tiene libre en esas fechas.',
    )
    warehouse_src_id = fields.Many2one(
        'stock.warehouse', string='Puede prestarlo', ondelete='set null',
    )
    qty_sin_cubrir = fields.Float(
        string='Sin cubrir', compute='_compute_qty_sin_cubrir', store=True,
        digits='Product Unit of Measure',
    )
    order_ids = fields.Many2many('sale.order', string='Pedidos afectados')
    date_analisis = fields.Datetime(
        string='Analizado el', default=fields.Datetime.now, readonly=True,
    )

    @api.depends('qty_deficit', 'qty_cubrible')
    def _compute_qty_sin_cubrir(self):
        for deficit in self:
            deficit.qty_sin_cubrir = max(0.0, deficit.qty_deficit - deficit.qty_cubrible)

    # ------------------------------------------------------------------
    # El análisis
    # ------------------------------------------------------------------

    @api.model
    def analizar(self, horizonte_dias=None):
        """Recorre la demanda confirmada del horizonte y anota lo que no se puede servir.

        Idempotente: cada pasada borra el análisis anterior y escribe el actual. Un déficit
        es una foto de un momento, no un histórico; guardarlos acumulados solo conseguiría
        que nadie se fiara de la lista.
        """
        motor = self.env['enteza.disponibilidad'].sudo()
        parametro = self.env['enteza.stock.loan']._parametro(
            'horizonte_analisis', 30,
        )
        dias = horizonte_dias or parametro
        desde = fields.Datetime.now()
        hasta = desde + timedelta(days=dias)

        # Solo lo confirmado cuenta como demanda (§5.7), y se excluyen los alquileres ya
        # devueltos —entre ellos los 1.153 migrados de la 15, que si no generarían déficits
        # fantasma en masa—.
        lineas = self.env['sale.order.line'].sudo().search([
            ('is_rental', '=', True),
            ('state', '=', 'sale'),
            ('return_date', '>=', desde),
            ('start_date', '<=', hasta),
            ('order_id.rental_status', '!=', 'returned'),
        ])

        # Un intervalo por combinación real: dos líneas del mismo producto para las mismas
        # fechas son la misma pregunta, y preguntarla dos veces daría dos déficits iguales.
        intervalos = {}
        for linea in lineas:
            almacen = linea.order_id.warehouse_id
            if not (almacen and linea.product_id.is_storable):
                continue
            clave = (linea.product_id, almacen, linea.start_date, linea.return_date)
            intervalos.setdefault(clave, self.env['sale.order'])
            intervalos[clave] |= linea.order_id

        self.sudo().search([]).unlink()
        valores = []
        for (producto, almacen, inicio, fin), pedidos in intervalos.items():
            disponible = motor.disponible(producto, almacen, inicio, fin)[producto.id]
            if disponible >= 0:
                continue
            falta = -disponible
            cubrible, origen = self._buscar_quien_presta(producto, almacen, inicio, fin,
                                                         falta)
            valores.append({
                'product_id': producto.id,
                'warehouse_id': almacen.id,
                'date_from': inicio,
                'date_to': fin,
                'qty_deficit': falta,
                'qty_cubrible': cubrible,
                'warehouse_src_id': origen.id if origen else False,
                'order_ids': [(6, 0, pedidos.ids)],
            })

        creados = self.sudo().create(valores) if valores else self.browse()
        self._marcar_reservas_huerfanas()
        _logger.info(
            'Análisis de préstamos: %s intervalos revisados, %s déficits',
            len(intervalos), len(creados),
        )
        return creados

    @api.model
    def _marcar_reservas_huerfanas(self):
        """Préstamos reservados cuyo pedido de origen ya no existe (§12, caso 12).

        La liberación al cancelar (`19.0.4.1.0`) debería dejar esto a cero, pero es
        precisamente por eso por lo que hace falta comprobarlo: si algún día falla, el
        material se queda inmovilizado y **nadie se entera**. Es dinero parado que no aparece
        en ninguna pantalla.

        No se libera automáticamente: se marca. Deshacer una reserva por si acaso es peor que
        enseñarla.
        """
        vivos = self.env['enteza.stock.loan'].sudo().search([
            ('state', 'in', ('reserved', 'approved')),
            ('revision_pendiente', '=', False),
        ])
        for prestamo in vivos:
            ventas = prestamo.line_ids.sale_line_id
            if not ventas:
                # Propuesto por lotes o creado a mano: no tiene pedido que vigilar.
                continue
            if all(venta.state == 'cancel' for venta in ventas.order_id):
                prestamo._marcar_para_revision(_(
                    'Todos los pedidos que justificaban este préstamo están cancelados y el '
                    'material sigue comprometido.'
                ))
                _logger.warning(
                    'Reserva huérfana detectada en el préstamo %s', prestamo.name,
                )

    @api.model
    def _buscar_quien_presta(self, producto, almacen, desde, hasta, falta):
        """Qué almacén de otra compañía puede cubrir el déficit. Misma regla que al confirmar."""
        motor = self.env['enteza.disponibilidad'].sudo()
        almacenes = self.env['stock.warehouse'].sudo().search([
            ('company_id', '!=', almacen.company_id.id),
        ])
        mejor_qty, mejor = 0.0, None
        for candidato in almacenes:
            prestable = motor.with_company(candidato.company_id).prestable(
                producto.sudo().with_company(candidato.company_id), candidato, desde, hasta,
            )[producto.id]
            if prestable > mejor_qty:
                mejor_qty, mejor = prestable, candidato
        return min(mejor_qty, falta), mejor

    @api.model
    def _cron_analizar(self):
        self.analizar()

    def action_analizar_ahora(self):
        """Botón para lanzarlo a mano sin esperar al cron."""
        self.analizar()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    # ------------------------------------------------------------------
    # Propuesta (§7.2)
    # ------------------------------------------------------------------

    def action_proponer_prestamos(self):
        """Crea préstamos en BORRADOR para los déficits que otra compañía puede cubrir.

        En borrador y no reservados a propósito: esto lo dispara alguien mirando una lista, no
        el comercial que está cerrando una venta. Quien lo revise decidirá si lo reserva, y
        entonces el material queda comprometido con el circuito de siempre.
        """
        Prestamo = self.env['enteza.stock.loan'].sudo()
        creados = Prestamo.browse()
        for deficit in self.filtered(lambda registro: registro.qty_cubrible > 0):
            fecha = Prestamo._fecha_traslado_de(deficit.date_from)
            prestamo = Prestamo.search([
                ('warehouse_src_id', '=', deficit.warehouse_src_id.id),
                ('warehouse_dest_id', '=', deficit.warehouse_id.id),
                ('date_transfer', '=', fecha),
                ('state', '=', 'draft'),
            ], limit=1)
            vals_linea = {
                'product_id': deficit.product_id.id,
                'product_uom_id': deficit.product_id.uom_id.id,
                'qty_proposed': deficit.qty_cubrible,
                'date_from': deficit.date_from,
                'date_to': deficit.date_to,
                'deficit_date': deficit.date_from,
            }
            if prestamo:
                prestamo.write({'line_ids': [(0, 0, vals_linea)]})
            else:
                prestamo = Prestamo.create({
                    'company_id': deficit.warehouse_src_id.company_id.id,
                    'company_dest_id': deficit.company_id.id,
                    'warehouse_src_id': deficit.warehouse_src_id.id,
                    'warehouse_dest_id': deficit.warehouse_id.id,
                    'date_transfer': fecha,
                    'origin': 'batch',
                    'line_ids': [(0, 0, vals_linea)],
                })
            prestamo.origin_order_ids = [(4, pedido.id) for pedido in deficit.order_ids]
            creados |= prestamo

        if not creados:
            raise UserError(_(
                'Ninguno de los déficits seleccionados se puede cubrir con material de otra '
                'compañía del grupo.'
            ))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Préstamos propuestos'),
            'res_model': 'enteza.stock.loan',
            'domain': [('id', 'in', creados.ids)],
            'view_mode': 'list,form',
        }
