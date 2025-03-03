from odoo import models, fields, api

class StockMove(models.Model):
    _inherit = 'stock.move'
    
    missing_units = fields.Integer(string='Missing Units', default=0)
    
    @api.onchange('missing_units')
    def _onchange_missing_units(self):
        for line in self:
            if line.missing_units:
                line.quantity = line.product_uom_qty - line.missing_units

