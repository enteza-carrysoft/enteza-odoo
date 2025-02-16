from odoo import fields, models

class RentalSchedule(models.Model):
    _inherit = "sale.rental.schedule"

    partner_shipping_id = fields.Many2one('sale.order', 'Lugar',readonly=True)

    def _select(self) -> SQL:
        return SQL("""%s,
            lot_info.lot_id as lot_id,
            s.warehouse_id as warehouse_id,
            s.partner_shipping_id as partner_shipping_id
        """, super(RentalSchedule, self)._select())

