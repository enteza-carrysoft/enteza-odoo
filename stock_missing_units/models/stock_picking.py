from odoo import models, fields, api

class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'
    
    missing_units = fields.Integer(string='Missing Units', default=0)
    
    @api.onchange('missing_units')
    def _onchange_missing_units(self):
        for line in self:
            if line.missing_units:
                line.qty_done = line.product_uom_qty - line.missing_units

class StockMove(models.Model):
    _inherit = 'stock.move'
    
    missing_units = fields.Integer(
        string='Missing Units',
        compute='_compute_missing_units',
        store=True,
        readonly=False
    )
    
    @api.depends('move_line_ids.missing_units')
    def _compute_missing_units(self):
        for move in self:
            if move.move_line_ids:
                move.missing_units = sum(move.move_line_ids.mapped('missing_units'))
            else:
                move.missing_units = 0

