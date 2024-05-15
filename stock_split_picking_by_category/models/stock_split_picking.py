from odoo import models, fields

class StockPicking(models.TransientModel):
    _inherit = "stock.split.picking"

#    categ_id = fields.Many2one('product.category', string="Product Category")

    categ_ids = fields.Many2many(
        comodel_name='product.category',
        string='Categoria',
        required=False,
        help="Select category"
    )

#    def _apply_selection(self):
#        """Modify to create a picking for all selected moves filtered by product family."""
#        if self.category_id:
#            moves = self.move_ids.filtered(lambda m: m.product_id.categ_id == self.categ_id)
#        else:
#            moves = self.mapped("move_ids")
#        if moves:
##            new_picking = moves.mapped("picking_id")._split_off_moves(moves)
#            return self._picking_action(new_picking)
#        return False

