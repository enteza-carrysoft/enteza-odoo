# Copyright 2019 Tecnativa - Ernesto Tejeda
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta


class SaleOrder(models.Model):
    _inherit = "sale.order"

    event_date = fields.Date(
        string="Fecha Evento",
    )
    place_number = fields.Integer(
        string="Número Plazas",
    )

    @api.onchange("event_date")
    def event_date_change(self):
        if self.event_date:
            self.rental_start_date = self.event_date - timedelta(days=1)
            self.rental_return_date = self.event_date + timedelta(days=1)

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    event_date = fields.Date(
        related="order_id.event_date",
    )
    product_categ_id = fields.Many2one(
        related="product_id.categ_id",
        string="Categoria",
        store=True
    )
