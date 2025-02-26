from odoo import models, fields

class StockSplitPicking(models.TransientModel):
    _inherit = "stock.split.picking"

    categ_ids = fields.Many2many(
        comodel_name='product.category',
        string='Categories',
        required=False,
        help="Select categories to filter moves"
    )

    def split_picking(self):
        self.ensure_one()
        picking = self.picking_id
        # Filtrar movimientos basados en categorías seleccionadas
        if self.categ_ids:
            moves_to_split = self.move_ids.filtered(lambda m: m.product_id.categ_id in self.categ_ids)
        else:
            moves_to_split = self.move_ids
        # Proceder con la división usando los movimientos filtrados
        new_picking = picking.copy({
            'name': picking.name + ' (split)',
            'move_lines': [],
            'move_line_ids': [],
        })
        for move in moves_to_split:
            new_move = move.copy({
                'picking_id': new_picking.id,
                'move_line_ids': [],
            })
            move.write({
                'quantity_done': move.quantity_done - self.quantity_to_split[move.id],
            })
            new_move.write({
                'quantity_done': self.quantity_to_split[move.id],
            })
            new_picking.move_lines |= new_move
        new_picking.action_assign()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': new_picking.id,
        }
