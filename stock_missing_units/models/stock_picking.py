# models/stock_picking.py
from odoo import models, fields, api

class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    missing_units = fields.Integer(
        string='Missing Units',
        default=0,
        help='Number of units missing in this move line'
    )

    @api.onchange('missing_units')
    def _onchange_missing_units(self):
        for line in self:
            if line.missing_units:
                if line.missing_units > line.product_uom_qty:
                    raise ValidationError(_('Missing units cannot exceed the product quantity (%s).') % line.product_uom_qty)
                line.qty_done = max(0, line.product_uom_qty - line.missing_units)

class StockMove(models.Model):
    _inherit = 'stock.move'

    missing_units = fields.Integer(
        string='Missing Units',
        compute='_compute_missing_units',
        inverse='_inverse_missing_units',
        store=True,
        help='Total missing units across all move lines'
    )

    @api.depends('move_line_ids.missing_units')
    def _compute_missing_units(self):
        for move in self:
            move.missing_units = sum(line.missing_units for line in move.move_line_ids)

    def _inverse_missing_units(self):
        for move in self:
            if move.move_line_ids:
                total_missing = move.missing_units
                lines_count = len(move.move_line_ids)
                if lines_count > 0:
                    base_missing = total_missing // lines_count
                    remainder = total_missing % lines_count
                    for index, line in enumerate(move.move_line_ids):
                        line.missing_units = base_missing + (1 if index < remainder else 0)
                else:
                    move.missing_units = 0
