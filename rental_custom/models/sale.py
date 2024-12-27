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

    def get_stock_rental(self,product_id,data):
        date_start=data.get('date_start',False)
        date_stop=data.get('date_stop',False)
        warehouse_id=self.env['stock.warehouse'].browse(data.get('warehouse_id',False))
        total_qty =product_id.with_context({"location": warehouse_id.rental_view_location_id.id}).qty_available
        max_ol_qty = self._get_max_overlapping_rental_qty_cus(product_id,data)
        return max_ol_qty

    def _get_concurrent_order_lines_cust(self,product_id,data):
        domain = []
        domain += [
            ("state", "!=", "cancel"),
            ("display_product_id", "=", product_id.id),
            "|",
            "&",
            ("start_date", "<=", data.get('date_stop')),
            ("end_date", ">=",data.get('date_stop')),
            "&",
            ("start_date", "<=", data.get('date_stop')),
            ("end_date", ">=", data.get('date_stop')),
        ]
        res = self.env['sale.order.line'].search(domain)
        return res

    def _get_max_overlapping_rental_qty_cus(self,product_id,data):
        lines = self._get_concurrent_order_lines_cust(product_id,data)
        max_qty = 0
        for line in lines:
            ol_lines = self.env['sale.order.line'].search(
                [
                    ("id", "in", lines.ids),
                    ("start_date", "<=", data.get('date_stop')),
                    ("end_date", ">=",data.get('date_stop')),
                ]
            )
            tmp_qty = sum(line.rental_qty for line in ol_lines)
            if tmp_qty > max_qty:
                max_qty = tmp_qty
            ol_lines = self.env['sale.order.line'].search(
                [
                    ("id", "in", lines.ids),
                    ("start_date", "<=", data.get('date_stop')),
                    ("end_date", ">=",data.get('date_stop')),
                ]
            )
            tmp_qty = sum(line.rental_qty for line in ol_lines)
            if tmp_qty > max_qty:
                max_qty = tmp_qty
        return max_qty

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

    def _prepare_new_rental_procurement_values(self, group=False):
        vals = super()._prepare_new_rental_procurement_values(group=group)
        vals["route_ids"] = self.route_id or self.warehouses_id.rental_route_id
        vals["warehouse_id"] = self.warehouses_id or False
        return vals

    def _run_rental_procurement(self, vals):
        self.ensure_one()
        procurements = [
            self.env["procurement.group"].Procurement(
                self.product_id.rented_product_id,
                self.rental_qty,
                self.product_id.rented_product_id.uom_id,
                self.warehouses_id.rental_out_location_id,
                self.name,
                self.order_id.name,
                self.order_id.company_id,
                vals,
            )
        ]
        self.env["procurement.group"].run(procurements)

    def _get_number_of_time_unit(self):
        self.ensure_one()
        number = False
        time_uoms = self._get_time_uom()
        number = 1
        return number

    @api.onchange("warehouses_id")
    def onchange_start_end_date_wh(self):
        res = {}
        if self.start_date and self.end_date:
            number = self._get_number_of_time_unit()
            self.number_of_time_unit = number
            res = self._check_rental_availability()
        return res

    def _check_rental_availability(self):
        self.ensure_one()
        res = {}
        if not self.start_date or not self.end_date or not self.rental_qty:
            return {}
        total_qty = self.product_id.rented_product_id.with_context(
            {"location": self.warehouses_id.rental_view_location_id.id}
        ).qty_available
        max_ol_qty = self._get_max_overlapping_rental_qty()
        avail_qty = total_qty - max_ol_qty
        self.product_qty_rent = avail_qty
        self.product_qty_rent_str = "En Existencia "+str(avail_qty)
        if self.rental_qty > avail_qty:
            res = self._get_concurrent_orders()
            if res["quotation"] and not res["order"]:
                self.concurrent_orders = "quotation"
            else:
                self.concurrent_orders = "order"
            res["warning"] = {
                "title": _("Not enough stock!"),
                "message": _(
                    "You want to rent %.2f %s but you only "
                    "have %.2f %s available in the selected period."
                )
                % (
                    self.rental_qty,
                    self.product_id.rented_product_id.uom_id.name,
                    avail_qty,
                    self.product_id.rented_product_id.uom_id.name,
                ),
            }
        else:
            self.concurrent_orders = "none"
        return res

    def _get_concurrent_order_lines(self):
        self.ensure_one()
        domain = []
        if self.id:
            domain = [("id", "!=", self.id)]
        domain += [
            ("state", "!=", "cancel"),
            ("warehouses_id", "=", self.warehouses_id.id),
            ("display_product_id", "=", self.display_product_id.id),
            "|",
            "&",
            ("start_date", "<=", self.start_date),
            ("end_date", ">=", self.start_date),
            "&",
            ("start_date", "<=", self.end_date),
            ("end_date", ">=", self.end_date),
        ]
        res = self.search(domain)
        return res

    def _get_max_overlapping_rental_qty(self):
        self.ensure_one()
        lines = self._get_concurrent_order_lines()
        max_qty = 0
        for line in lines:
            ol_lines = self.search(
                [
                    ("id", "in", lines.ids),
                    ("start_date", "<=", line.start_date),
                    ("end_date", ">=", line.start_date),
                    ("not_reserved", "=", False),
                ]
            )
            tmp_qty = sum(line.rental_qty for line in ol_lines)
            if tmp_qty > max_qty:
                max_qty = tmp_qty
            ol_lines = self.search(
                [
                    ("id", "in", lines.ids),
                    ("start_date", "<=", line.end_date),
                    ("end_date", ">=", line.end_date),
                    ("not_reserved", "=", False),
                ]
            )
            tmp_qty = sum(line.rental_qty for line in ol_lines)
            if tmp_qty > max_qty:
                max_qty = tmp_qty
        return max_qty

    def compute_stock(self):
        if self.product_id and self.product_id.rented_product_id:
            total_qty = self.product_id.rented_product_id.with_context(
                {"location": self.warehouses_id.rental_view_location_id.id}
            ).qty_available
            max_ol_qty = self._get_max_overlapping_rental_qty()
            avail_qty = total_qty - max_ol_qty
            self.product_qty_rent = avail_qty
            self.product_qty_rent_str = "En Existencia "+str(avail_qty)
