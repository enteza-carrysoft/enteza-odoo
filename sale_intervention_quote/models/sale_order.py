from odoo import api, models

class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_open_intervention_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Presupuesto de intervención",
            "res_model": "intervention.quote.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_order_id": self.id},
        }
