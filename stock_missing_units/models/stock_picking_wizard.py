# models/stock_picking_wizard.py
from odoo import models, fields, api

class StockPickingWizard(models.TransientModel):
    _name = 'stock.picking.wizard'
    _description = 'Stock Picking Missing Units Wizard'

    picking_id = fields.Many2one('stock.picking', string='Picking', required=True)
    line_ids = fields.One2many('stock.picking.wizard.line', 'wizard_id', string='Lines')

    def action_apply_missing_units(self):
        for line in self.line_ids:
            move = line.move_id
            if move:
                move.quantity_done -= line.missing_units

class StockPickingWizardLine(models.TransientModel):
    _name = 'stock.picking.wizard.line'
    _description = 'Stock Picking Wizard Line'

    wizard_id = fields.Many2one('stock.picking.wizard', string='Wizard', required=True, ondelete='cascade')
    move_id = fields.Many2one('stock.move', string='Move', required=True)
    product_id = fields.Many2one('product.product', string='Product', related='move_id.product_id', readonly=True)
    reserved_qty = fields.Float(string='Reserved Quantity', related='move_id.product_uom_qty', readonly=True)
    done_qty = fields.Float(string='Done Quantity', related='move_id.quantity_done', readonly=True)
    missing_units = fields.Integer(string='Missing Units')

    @api.onchange('missing_units')
    def _onchange_missing_units(self):
        for line in self:
            if line.done_qty and line.missing_units:
                line.done_qty = line.reserved_qty - line.missing_units

