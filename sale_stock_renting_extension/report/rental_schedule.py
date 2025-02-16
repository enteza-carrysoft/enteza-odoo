from odoo import fields, models
from odoo.tools import SQL

class RentalSchedule(models.Model):
    _inherit = "sale.rental.schedule"

    partner_shipping_id = fields.Many2one('sale.order', 'Lugar',readonly=True)

    def _select(self) -> SQL:
        return SQL("""%s,
            s.partner_shipping_id as partner_shipping_id
        """, super(RentalSchedule, self)._select())

