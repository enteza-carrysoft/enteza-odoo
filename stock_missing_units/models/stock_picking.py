# models/stock_picking.py
from odoo import models, fields, api

class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    missing_units = fields.Integer(string='Missing Units', default=0)

    @api.onchange('missing_units')
    def _onchange_missing_units(self):
        if self.missing_units:
             self.qty_done = self.product_uom_qty - self.missing_units

class StockMove(models.Model):
    _inherit = 'stock.move'

    missing_units = fields.Integer(
        string='Missing Units',
        related='move_line_ids.missing_units',
        readonly=False
    )

