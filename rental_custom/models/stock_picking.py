from odoo import models, fields, api, _
from odoo.exceptions import UserError

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    sale_order_id = fields.Many2one('sale.order', string="Sale Order", readonly=True, copy=False)

    def action_create_sale_order(self):
        for picking in self:
            if picking.sale_order_id:
                raise UserError(_('Ya existe una orden de venta para este albarán.'))
            
            if not picking.move_ids_without_package:
                raise UserError(_('No hay líneas de productos en el albarán para crear una orden de venta.'))
            
            sale_order_vals = {
                'partner_id': picking.partner_id.id,
                'origin': picking.name,
                'order_line': [],
            }
            
            for move in picking.move_ids_without_package:
                sale_order_vals['order_line'].append((0, 0, {
                    'product_id': move.product_id.id,
                    'product_uom_qty': move.product_uom_qty,
                    'product_uom': move.product_uom.id,
                    'price_unit': move.product_id.list_price,
                }))
                
            sale_order = self.env['sale.order'].create(sale_order_vals)
            picking.sale_order_id = sale_order.id

            return {
                'type': 'ir.actions.act_window',
                'name': _('Sale Order'),
                'res_model': 'sale.order',
                'view_mode': 'form',
                'res_id': sale_order.id,
                'target': 'current',
            }
