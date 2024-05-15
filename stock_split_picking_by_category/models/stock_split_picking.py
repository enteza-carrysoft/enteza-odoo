from odoo import models, fields

class StockSplitPicking(models.TransientModel):
    _inherit = "stock.split.picking"

    family_id = fields.Many2one('product.family', string="Product Family")

    def _apply_selection(self):
        """Modify to create a picking for all selected moves filtered by product family."""
        if self.family_id:
            moves = self.move_ids.filtered(lambda m: m.product_id.family_id == self.family_id)
        else:
            moves = self.mapped("move_ids")
        if moves:
            new_picking = moves.mapped("picking_id")._split_off_moves(moves)
            return self._picking_action(new_picking)
        return False

