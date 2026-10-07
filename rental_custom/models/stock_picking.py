from odoo import models, fields, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    sale_order_id = fields.Many2one('sale.order', string="Sale Order", readonly=True, copy=False)
    is_rental_order = fields.Boolean(related='sale_id.is_rental_order')

    def action_create_sale_order(self):
        """Genera un pedido de venta por el material de alquiler no devuelto.

        «Faltas» son las unidades que NO han vuelto: alquiladas 100 y 5 faltas son 95
        devueltas; 0 faltas, todo devuelto. Dos modos, según esa columna
        (`stock.move.qty_missing`):

        - **Parcial** (2026-09-28): el albarán sigue abierto y alguna línea tiene faltas
          anotadas. Se facturan SOLO esas unidades; se descuentan de la demanda del albarán y
          el resto sigue pendiente de devolución. Nació para la cesión de material entre
          compañías, un alquiler de meses en el que las pérdidas llegan sueltas.
        - **Completo**: sin faltas anotadas, se factura toda la demanda de las líneas. El caso
          natural es el albarán parcial (backorder) que Odoo crea al validar una devolución
          con menos unidades: ahí esa cantidad ES ya la que falta. Se puede usar sobre
          cualquier albarán, porque decidir cuándo procede facturar unas faltas es criterio
          del almacén y no del módulo (12/08/2026).
        """
        self.ensure_one()
        sale_order = self._create_missing_sale_order()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sale Order'),
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': sale_order.id,
            'target': 'current',
        }

    def _get_missing_moves(self):
        """Líneas con faltas anotadas en un albarán todavía abierto (modo parcial)."""
        self.ensure_one()
        if self.state in ('done', 'cancel'):
            return self.env['stock.move']
        return self.move_ids.filtered(
            lambda m: m.state not in ('done', 'cancel')
            and m.product_uom.compare(m.qty_missing, 0.0) > 0
        )

    def _create_missing_sale_order(self):
        """Crea el pedido de faltas y devuelve el `sale.order`.

        Separado del botón para que otros módulos (`enteza_venta_intercompania`) lo llamen y
        reciban el pedido, no una acción de ventana.
        """
        self.ensure_one()
        missing_moves = self._get_missing_moves()
        partial = bool(missing_moves)

        # Un albarán se factura entero una sola vez. En parcial no aplica: cada tanda de
        # faltas descuenta su cantidad de la demanda, así que repetir no duplica nada.
        if not partial and self.sale_order_id:
            raise UserError(_(
                'Ya existe una orden de venta para este albarán. Si faltan más unidades, '
                'anótalas en la columna «Faltas» y vuelve a pulsar el botón.'))

        moves = missing_moves if partial else self.move_ids
        if not moves:
            raise UserError(_('No hay líneas de productos en el albarán para crear una orden de venta.'))

        partner = self.sale_id.partner_invoice_id or self.partner_id
        if not partner:
            raise UserError(_('No se pudo determinar el cliente a facturar.'))

        SaleOrder = self.env['sale.order']
        order_line = [
            SaleOrder._prepare_missing_line_vals(
                move.product_id,
                move.qty_missing if partial else move.product_uom_qty,
                move.product_uom,
            )
            for move in moves
        ]

        # Las unidades sólo siguen en la ubicación de Alquiler si el albarán de devolución no
        # llegó a validarse. Si se validó, Odoo ya las dio por devueltas a Stock.
        from_rental_location = self.state != 'done' and bool(self.company_id.rental_loc_id) \
            and self.location_id == self.company_id.rental_loc_id

        # Cabecera compartida con «Registrar faltas» del pedido (`sale.order`), para que los
        # dos caminos den exactamente el mismo pedido de faltas.
        sale_order = SaleOrder.create(self.sale_id._prepare_missing_sale_order_vals(
            partner, self.company_id, self.sale_id.name or self.name, order_line,
            from_rental_location,
        ))
        # También en parcial, si es la primera: al validar una recogida con faltas, Odoo copia
        # «Faltas» al albarán pendiente que crea con esas unidades. Al facturarlo, todas sus
        # líneas se cancelan; sin este enlace, un segundo clic lo facturaría otra vez entero.
        if not self.sale_order_id:
            self.sale_order_id = sale_order.id

        self._post_missing_messages(sale_order)

        if partial:
            self._settle_partial_missing(missing_moves)
        elif self.state != 'done':
            self._settle_full_missing()
        return sale_order

    def _post_missing_messages(self, sale_order):
        # El albarán puede no venir de un pedido (el botón está en todos), así que la traza al
        # alquiler de origen sólo se escribe cuando lo hay: `_get_html_link()` y
        # `message_post()` hacen `ensure_one()` y reventarían con el recordset vacío.
        if self.sale_id:
            sale_order.message_post(
                body=_('Generado desde el albarán de faltas %s, del pedido de alquiler %s.',
                       self._get_html_link(), self.sale_id._get_html_link())
            )
            self.sale_id.message_post(
                body=_('Material no devuelto facturado en %s, desde el albarán %s.',
                       sale_order._get_html_link(), self._get_html_link())
            )
        else:
            sale_order.message_post(
                body=_('Generado desde el albarán de faltas %s.', self._get_html_link())
            )
        self.message_post(
            body=_('Creada la orden de venta %s por el material no devuelto.', sale_order._get_html_link())
        )

    def _mark_rental_line_lost(self, move, qty):
        """Da por resuelta `qty` de la línea de alquiler del movimiento.

        Odoo sólo suma a `qty_returned` cuando un movimiento de devolución llega a "hecho"
        (stock_move._action_done, en sale_stock_renting). Como estas unidades no van a
        volver, hay que cerrar ese hueco a mano para que el pedido pueda llegar a "Devuelto".
        `qty_lost` deja anotado, sin tocar el motor nativo de alquiler, cuántas de esas
        "devueltas" son en realidad una pérdida facturada.
        """
        sale_line = move.sale_line_id
        if sale_line and sale_line.is_rental and move.product_id == sale_line.product_id:
            qty_missing = move.product_uom._compute_quantity(
                qty, sale_line.product_uom_id, rounding_method='HALF-UP'
            )
            sale_line.qty_returned += qty_missing
            sale_line.qty_lost += qty_missing

    def _settle_full_missing(self):
        # Sobre un albarán ya validado no se toca nada: sus movimientos llegaron a "hecho",
        # así que `qty_returned` ya lo contabilizó Odoo y volver a sumarlo lo duplicaría.
        for move in self.move_ids:
            self._mark_rental_line_lost(move, move.product_uom_qty)
        # Cancelar cierra el albarán: esas unidades ya no se esperan de vuelta.
        self.action_cancel()

    def _settle_partial_missing(self, moves):
        """Descuenta las faltas de la demanda y deja el resto pendiente de devolver."""
        for move in moves:
            qty = move.qty_missing
            self._mark_rental_line_lost(move, qty)
            remaining = move.product_uom_qty - qty
            if move.product_uom.compare(remaining, 0.0) <= 0:
                move.qty_missing = 0.0
                move._action_cancel()
            else:
                # Bajar la demanda por debajo de lo reservado anula la reserva
                # (`stock.move.write`, Odoo 19): se vuelve a reservar lo que queda.
                move.write({'product_uom_qty': remaining, 'qty_missing': 0.0})
        moves.filtered(lambda m: m.state in ('confirmed', 'partially_available'))._action_assign()
