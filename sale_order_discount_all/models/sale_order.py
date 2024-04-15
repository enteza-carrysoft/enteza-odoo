# Copyright (C) 2024 Manuel Calero, Abraham Carrasco (<https://xtendoo.es>).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import datetime

from odoo import fields, models, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    all_discount = fields.Float(string='Descuento en lineas (%)', digits='Discount', default=0.0)

    def action_sale_order_discount_all(self):
        for line in self.order_line:
            line.discount = self.all_discount
