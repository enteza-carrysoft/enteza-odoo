from odoo import api, models, fields, tools



class PurchaseOrderLineAdd(models.Model):
    _inherit = "purchase.order.line"

    date_order = fields.Datetime(
        'Order Date', related="order_id.date_order", store=True, index=True)
