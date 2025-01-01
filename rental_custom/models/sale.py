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

    total_stock = fields.Float(string='Stock Total', compute='_compute_total_availability', store=False)
    total_rented = fields.Float(string='Total Alquilado', compute='_compute_total_availability', store=False)
    total_available = fields.Float(string='Total Disponible', compute='_compute_total_availability', store=False)

    @api.depends('product_id', 'reservation_begin', 'return_date')
    def _compute_total_availability(self):
        for line in self:
            if line.is_rental:
                availability = self.get_total_availability(line.product_id.id, line.reservation_begin, line.return_date)
                line.total_stock = availability['total_stock']
                line.total_rented = availability['total_rented']
                line.total_available = availability['total_available']

    @api.model
    def get_total_availability(self, product_id, start_date, end_date):
        product = self.env['product.product'].browse(product_id)

        total_stock = sum(self.env['stock.quant'].search([
            ('product_id', '=', product_id),
            ('location_id.usage', '=', 'internal')
        ]).mapped('quantity'))

        total_rented = sum(self.env['sale.order.line'].search([
            ('product_id', '=', product_id),
            ('is_rental', '=', True),
            ('reservation_begin', '<=', end_date),
            ('return_date', '>=', start_date),
            ('state', '=', 'sale')
        ]).mapped('product_uom_qty'))

        total_available = total_stock - total_rented

        return {
            'product_id': product.display_name,
            'total_stock': total_stock,
            'total_rented': total_rented,
            'total_available': total_available,
        }

    @api.model
    def get_availability_data(self, product_id, start_date, end_date):
        availability_data = self.get_total_availability(product_id, start_date, end_date)
        return availability_data

