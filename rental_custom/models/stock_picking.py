from odoo import models, fields, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    sale_order_id = fields.Many2one('sale.order', string="Sale Order", readonly=True, copy=False)
    is_rental_order = fields.Boolean(related='sale_id.is_rental_order')

    def action_create_sale_order(self):
        """Genera un pedido de venta por el material de alquiler no devuelto.

        Sólo tiene sentido sobre un albarán parcial (backorder) de una devolución de
        alquiler: ese backorder lo crea Odoo de forma nativa cuando se valida con menos
        unidades de las que constaban en la demanda, y su `product_uom_qty` es ya la
        cantidad que falta, sin necesidad de restar nada a mano.
        """
        self.ensure_one()

        if not self.is_rental_order:
            raise UserError(_('Este albarán no pertenece a un pedido de alquiler.'))

        if not self.backorder_id:
            raise UserError(
                _('Este botón sólo se usa sobre el albarán parcial (backorder) que Odoo '
                  'crea cuando falta material por devolver, no sobre el albarán original.')
            )

        if self.sale_order_id:
            raise UserError(_('Ya existe una orden de venta para este albarán.'))

        if not self.move_ids_without_package:
            raise UserError(_('No hay líneas de productos en el albarán para crear una orden de venta.'))

        partner = self.sale_id.partner_invoice_id or self.partner_id
        if not partner:
            raise UserError(_('No se pudo determinar el cliente a facturar.'))

        order_line = [(0, 0, {
            'product_id': move.product_id.id,
            'product_uom_qty': move.product_uom_qty,
            'product_uom_id': move.product_uom.id,
            'price_unit': move.product_id.lst_price,
        }) for move in self.move_ids_without_package]

        sale_order = self.env['sale.order'].create({
            'partner_id': partner.id,
            'company_id': self.company_id.id,
            'origin': self.sale_id.name or self.name,
            'order_line': order_line,
        })
        self.sale_order_id = sale_order.id

        sale_order.message_post(
            body=_('Generado desde el albarán de faltas %s, del pedido de alquiler %s.',
                   self._get_html_link(), self.sale_id._get_html_link())
        )
        self.sale_id.message_post(
            body=_('Material no devuelto facturado en %s, desde el albarán %s.',
                   sale_order._get_html_link(), self._get_html_link())
        )
        self.message_post(
            body=_('Creada la orden de venta %s por el material no devuelto.', sale_order._get_html_link())
        )

        self.action_cancel()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Sale Order'),
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': sale_order.id,
            'target': 'current',
        }
