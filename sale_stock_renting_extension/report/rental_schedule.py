from odoo import fields, models
form odoo.tools import SQL

class RentalSchedule(models.Model):
    _inherit = "sale.rental.schedule"

    partner_shipping_id = fields.Many2one('sale.order', 'Lugar',readonly=True)

