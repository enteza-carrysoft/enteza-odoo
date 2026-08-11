from odoo import models, fields, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    sale_order_id = fields.Many2one('sale.order', string="Sale Order", readonly=True, copy=False)
    is_rental_order = fields.Boolean(related='sale_id.is_rental_order')

    def action_create_sale_order(self):
        """Genera un pedido de venta por el material de alquiler no devuelto.

        Factura las cantidades que figuran en las líneas del albarán (`product_uom_qty`).
        El caso natural sigue siendo el albarán parcial (backorder) que Odoo crea al validar
        una devolución con menos unidades de las que constaban: ahí esa cantidad ES ya la que
        falta. Pero se puede usar sobre cualquier albarán, porque decidir cuándo procede
        facturar unas faltas es criterio del almacén y no del módulo (12/08/2026).

        Sólo quedan las dos comprobaciones que evitan un pedido incorrecto: no facturar dos
        veces el mismo albarán y no crear un pedido vacío.
        """
        self.ensure_one()

        if self.sale_order_id:
            raise UserError(_('Ya existe una orden de venta para este albarán.'))

        if not self.move_ids:
            raise UserError(_('No hay líneas de productos en el albarán para crear una orden de venta.'))

        partner = self.sale_id.partner_invoice_id or self.partner_id
        if not partner:
            raise UserError(_('No se pudo determinar el cliente a facturar.'))

        order_line = [(0, 0, {
            'product_id': move.product_id.id,
            'product_uom_qty': move.product_uom_qty,
            'product_uom_id': move.product_uom.id,
            'price_unit': move.product_id.lst_price,
            # El producto es alquilable (rent_ok) y sale_renting marca la línea como alquiler
            # por defecto en cuanto lo detecta, arrastrando al pedido entero a is_rental_order.
            # Esto es una venta normal de material perdido, no un alquiler.
            'is_rental': False,
        }) for move in self.move_ids]

        sale_order = self.env['sale.order'].create({
            'partner_id': partner.id,
            'company_id': self.company_id.id,
            'origin': self.sale_id.name or self.name,
            'order_line': order_line,
            # El material ya salió por el albarán de alquiler original y esta venta sólo
            # formaliza el cobro, pero al confirmarla Odoo generará igualmente su albarán de
            # salida: el pedido sigue el flujo nativo como cualquier otro (decisión del
            # 12/08/2026). Ese albarán hay que cancelarlo a mano, o validarlo si se prefiere
            # dejar constancia de que el material salió del almacén.
            'rental_order_id': self.sale_id.id,
            # Forzado explícito: el botón se pulsa desde un albarán de la app de Alquiler, y
            # ese contexto trae un `default_is_rental_order` ambiental que, si no se anula
            # aquí, cuela el pedido en la app de Alquiler aunque ninguna línea sea de alquiler
            # (is_rental=False en todas). No basta con las líneas, hay que fijarlo también en
            # la cabecera.
            'is_rental_order': False,
            # No es un pedido de alquiler, así que este campo queda libre para anotar la fecha
            # del evento de origen: sirve de dimensión de periodo en los informes de pérdidas.
            'event_date': self.sale_id.event_date,
        })
        self.sale_order_id = sale_order.id

        # El albarán puede no venir de un pedido (ahora el botón está en todos), así que la
        # traza al alquiler de origen sólo se escribe cuando lo hay: `_get_html_link()` y
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

        # Odoo sólo suma a `qty_returned` cuando un movimiento de devolución llega a "hecho"
        # (stock_move._action_done, en sale_stock_renting). Como este albarán se cancela en vez
        # de completarse, hay que cerrar ese hueco a mano para que el pedido deje de verse
        # como "Recogido" (con material pendiente) y pase a "Devuelto": la falta ya no se
        # espera de vuelta, se ha resuelto facturándola. `qty_lost` deja anotado, sin tocar el
        # motor nativo de alquiler, cuántas de esas "devueltas" son en realidad una pérdida
        # facturada — para no confundirlo con una devolución física real.
        #
        # Sobre un albarán ya validado no se toca nada de esto: sus movimientos llegaron a
        # "hecho", así que `qty_returned` ya lo contabilizó Odoo y volver a sumarlo lo duplicaría.
        if self.state != 'done':
            for move in self.move_ids:
                sale_line = move.sale_line_id
                if sale_line and sale_line.is_rental and move.product_id == sale_line.product_id:
                    qty_missing = move.product_uom._compute_quantity(
                        move.product_uom_qty, sale_line.product_uom_id, rounding_method='HALF-UP'
                    )
                    sale_line.qty_returned += qty_missing
                    sale_line.qty_lost += qty_missing

            # Cancelar cierra el albarán: esas unidades ya no se esperan de vuelta. Un albarán
            # en "hecho" no se puede cancelar (ni debe: el movimiento físico ya ocurrió), de
            # modo que ahí la venta de faltas se limita a facturar.
            self.action_cancel()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Sale Order'),
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': sale_order.id,
            'target': 'current',
        }
