from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestRentalBillableDays(TransactionCase):

    def test_billable_days_do_not_change_rental_period(self):
        recurrence = self.env["sale.temporal.recurrence"].search(
            [("unit", "=", "day"), ("duration", "=", 1)], limit=1
        )
        product = self.env["product.product"].create({
            "name": "Producto de alquiler de prueba",
            "rent_ok": True,
        })
        self.env["product.pricing"].create({
            "product_template_id": product.product_tmpl_id.id,
            "recurrence_id": recurrence.id,
            "price": 10.0,
        })
        start_date = fields.Datetime.now()
        return_date = start_date + timedelta(days=3)
        order = self.env["sale.order"].with_context(in_rental_app=True).create({
            "partner_id": self.env.ref("base.res_partner_1").id,
            "rental_start_date": start_date,
            "rental_return_date": return_date,
            "rental_billable_days": 1.5,
        })
        line = self.env["sale.order.line"].with_context(in_rental_app=True).create({
            "order_id": order.id,
            "product_id": product.id,
            "product_uom_qty": 1.0,
        })

        self.assertEqual(line._get_pricelist_price(), 15.0)
        self.assertEqual(order.rental_start_date, start_date)
        self.assertEqual(order.rental_return_date, return_date)
