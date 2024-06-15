# stock_picking_batch_report/models/stock_picking_batch.py

from odoo import models, fields, api

class StockPickingBatch(models.Model):
    _inherit = 'stock.picking.batch'

    def get_aggregated_products_by_category(self):
        category_data = {}
        for picking in self.picking_ids:
            for move in picking.move_lines:
                product = move.product_id
                category = product.categ_id
                if category not in category_data:
                    category_data[category] = {}
                if product not in category_data[category]:
                    category_data[category][product] = 0
                category_data[category][product] += move.product_uom_qty

        aggregated_data = []
        for category, products in category_data.items():
            product_lines = []
            for product, qty in products.items():
                product_lines.append({
                    'product': product,
                    'quantity': qty,
                })
            aggregated_data.append({
                'category': category,
                'products': product_lines,
            })
        return aggregated_data

