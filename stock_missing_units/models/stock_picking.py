# models/stock_picking.py
from odoo import models, fields

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def action_open_missing_units_wizard(self):
        return {
            'name': 'Report Missing Units',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_picking_id': self.id},
        }

