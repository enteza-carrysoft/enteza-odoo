from odoo import Command
from odoo.addons.sale.tests.common import TestSaleCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestRentalIncomeAccount(TestSaleCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sale_account = cls.env["account.account"].create({
            "name": "Ingresos por ventas test",
            "code": "TEST-VTA",
            "account_type": "income",
        })
        cls.rental_account = cls.env["account.account"].create({
            "name": "Ingresos por alquiler test",
            "code": "TEST-ALQ",
            "account_type": "income_other",
        })
        cls.product = cls.env["product.product"].create({
            "name": "Producto vendible y alquilable",
            "sale_ok": True,
            "rent_ok": True,
            "list_price": 100.0,
            "property_account_income_id": cls.sale_account.id,
            "property_account_rental_income_id": cls.rental_account.id,
        })

    def _make_order_line(self, is_rental):
        order_values = {
            "partner_id": self.partner_a.id,
            "order_line": [Command.create({
                "product_id": self.product.id,
                "product_uom_qty": 1.0,
                "price_unit": 100.0,
            })],
        }
        if "is_rental" in self.env["sale.order"]._fields:
            order_values["is_rental"] = is_rental
        order = self.env["sale.order"].create(order_values)
        return order.order_line.filtered(lambda line: not line.display_type)[:1]

    def test_regular_sale_uses_standard_income_account(self):
        line = self._make_order_line(is_rental=False)
        values = line._prepare_invoice_line()
        # Standard sale prepares the ordinary product/category account.
        self.assertEqual(values.get("account_id"), self.sale_account.id)

    def test_rental_uses_rental_income_account(self):
        line = self._make_order_line(is_rental=True)
        values = line._prepare_invoice_line()
        self.assertEqual(values.get("account_id"), self.rental_account.id)

    def test_rental_falls_back_to_standard_account(self):
        self.product.property_account_rental_income_id = False
        line = self._make_order_line(is_rental=True)
        values = line._prepare_invoice_line()
        self.assertEqual(values.get("account_id"), self.sale_account.id)

    def test_rental_account_is_mapped_by_fiscal_position(self):
        mapped_account = self.env["account.account"].create({
            "name": "Ingresos por alquiler mapeados",
            "code": "TEST-ALQM",
            "account_type": "income_other",
        })
        fiscal_position = self.env["account.fiscal.position"].create({
            "name": "Mapeo alquiler test",
            "account_ids": [Command.create({
                "account_src_id": self.rental_account.id,
                "account_dest_id": mapped_account.id,
            })],
        })
        line = self._make_order_line(is_rental=True)
        line.order_id.fiscal_position_id = fiscal_position
        values = line._prepare_invoice_line()
        self.assertEqual(values.get("account_id"), mapped_account.id)
