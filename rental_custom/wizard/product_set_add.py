# Part of rental-vertical See LICENSE file for full copyright and licensing details.
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProductSetAdd(models.TransientModel):
    _inherit = "product.set.add"

    start_date = fields.Date(string="Start Date", compute="_compute_start_date", readonly=False, store=True)
    end_date = fields.Date(string="End Date", compute="_compute_end_date", readonly=False, store=True)
    warehouse_id = fields.Many2one("stock.warehouse", string="Almacén", required=True)

    @api.depends('order_id.date_order')
    def _compute_start_date(self):
        if self.order_id and self.order_id.default_start_date:
            self.start_date = self.order_id.default_start_date
        else:
            self.start_date = False

    @api.depends('order_id.date_order')
    def _compute_end_date(self):
        if self.order_id and self.order_id.default_end_date:
            self.end_date = self.order_id.default_end_date
        else:
            self.end_date = False

    def prepare_rental_so_line(
        self, sale_order_id, set_line, product, uom_id, max_sequence
    ):
        qty_to_rent = set_line.quantity * self.quantity
        # rental_type = self.env.ref('rental_base.rental_sale_type')
        line_data = self.env["sale.order.line"].new(
            {
                "order_id": sale_order_id,
                "product_id": product.id,
                "display_product_id": product.rented_product_id.id,
                "rental": True,
                "rental_qty": qty_to_rent,
                "can_sell_rental": False,
                "sell_rental_id": False,
                "rental_type": "new_rental",
                "product_uom_qty": qty_to_rent,
                "product_uom": uom_id.id,
                "sequence": max_sequence + set_line.sequence,
                "discount": set_line.discount,
                "start_date": self.start_date,
                "end_date": self.end_date,
                "warehouses_id": self.warehouse_id,
            }
        )
        line_data.rental_product_id_change()
        line_data.product_uom_change()
        line_data.product_id_change()
        line_data.onchange_start_end_date()
        line_data.rental_qty_number_of_days_change()
        line_values = line_data._convert_to_write(line_data._cache)
        return line_values
