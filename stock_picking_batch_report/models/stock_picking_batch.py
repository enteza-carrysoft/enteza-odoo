# stock_picking_batch_report/models/stock_picking_batch.py

from odoo import models, fields, api

class StockPickingBatch(models.Model):
    _inherit = 'stock.picking.batch'

    @api.multi
    def get_aggregated_products(self):
        product_data = {}
        for picking in self.picking_ids:
            for move in picking.move_lines:
                product = move.product_id
                if product not in product_data:
                    product_data[product] = 0
                product_data[product] += move.product_qty
        
        aggregated_products = []
        for product, qty in product_data.items():
            aggregated_products.append({
                'product': product,
                'quantity': qty,
            })
        return aggregated_products

