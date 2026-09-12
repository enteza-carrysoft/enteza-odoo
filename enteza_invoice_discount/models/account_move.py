from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_open_discount_wizard(self):
        self.ensure_one()
        return {
            "name": "Descuento",
            "type": "ir.actions.act_window",
            "res_model": "account.move.discount",
            "view_mode": "form",
            "target": "new",
        }
