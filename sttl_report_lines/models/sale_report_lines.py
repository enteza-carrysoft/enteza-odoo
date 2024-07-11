from odoo import api, models, fields, tools


class SaleOrderLineAdd(models.Model):
    _inherit = 'sale.order.line'
    client_order_ref = fields.Char(
        'Customer Reference', related="order_id.client_order_ref")
    tag_ids = fields.Many2many(
        'crm.tag', string='Tags', related="order_id.tag_ids")
    date_order = fields.Datetime(
        'Order Date', related="order_id.date_order", store=True, index=True)
