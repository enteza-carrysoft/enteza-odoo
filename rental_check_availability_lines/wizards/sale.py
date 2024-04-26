# Part of rental-vertical See LICENSE file for full copyright and licensing details.
from odoo import _, api, exceptions, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_check_rental_availability(self):
        for order in self:
            for line in order.order_line:
                line._check_rental_availability()


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    concurrent_orders = fields.Selection(
        selection=[
            ("none", "None"),
            ("quotation", "Quotation"),
            ("order", "Order"),
        ],
        default="none",
    )

    product_id = fields.Many2one('product.product', string='Product')
    stock_available = fields.Float(string='Stock Available', compute='_compute_stock_available', store=False)


    @api.depends('product_id')
    def _compute_stock_available(self):
        for line in self:
            if line.product_id:
                stock_quant = self.env['stock.quant'].search([('product_id', '=', line.product_id.id)])
                if stock_quant:
                    line.stock_available = stock_quant.available_quantity
                else:
                    line.stock_available = 0.0
            else:
                line.stock_available = 0.0

    # TODO check here does it override from rental_pricelist or not
    @api.onchange("start_date", "end_date", "product_uom")
    def onchange_start_end_date(self):
        res = {}
        if self.start_date and self.end_date:
            number = self._get_number_of_time_unit()
            self.number_of_time_unit = number
            res = self._check_rental_availability()
        return res

    def _get_concurrent_order_lines(self):
        self.ensure_one()
        domain = []
        if self.id:
            domain = [("id", "!=", self.id)]
        domain += [
            ("state", "!=", "cancel"),
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

    def _get_concurrent_orders(self):
        self.ensure_one()
        sols = self._get_concurrent_order_lines()
        sos = sols.mapped("order_id")
        quotations = sos.filtered(lambda o: o.state in ["draft", "sent"])
        orders = sos.filtered(lambda o: o.state in ["sale"])
        return {
            "quotation": quotations,
            "order": orders,
            "sale_order_ids": quotations.ids + orders.ids,
        }

    def action_view_concurrent_orders(self):
        self.ensure_one()
        record_ids = self._get_concurrent_orders()["sale_order_ids"]
        if record_ids:
            action = self.env.ref("rental_base.action_rental_orders").read([])[0]
            action["domain"] = [("id", "in", record_ids)]
            return action
        raise exceptions.UserError(_("No found concurrent Rental Order/Quotation(s)."))

    def action_view_concurrent_orders_line(self):
        self.ensure_one()
        record_ids = self._get_concurrent_order_lines()
        if record_ids:
            action = self.env.ref("rental_check_availability_lines.action_rental_orders_lines").read([])[0]
            action["domain"] = [("id", "in", record_ids.ids)]
            return action
        raise exceptions.UserError(_("No found concurrent Rental Order/Quotation(s)."))

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
                ]
            )
            tmp_qty = sum(line.rental_qty for line in ol_lines)
            if tmp_qty > max_qty:
                max_qty = tmp_qty
        return max_qty

    def open_my_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Sales Order Lines',
            'res_model': 'sale.order.line.concurrent',
            'context': {'active_id': self.id, 'active_ids': [self.id]},
            'view_type': 'form',
            'view_mode': 'form',
            'target': 'new',
        }

    default_start_date = fields.Date(
        string='Start date',
        related='order_id.default_start_date',
        store=True
    )

    default_end_date = fields.Date(
        string='End date',
        related='order_id.default_end_date',
        store=True
    )
