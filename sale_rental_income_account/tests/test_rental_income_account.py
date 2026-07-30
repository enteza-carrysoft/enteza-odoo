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
        cls.categ_sale_account = cls.env["account.account"].create({
            "name": "Ingresos por ventas categoria test",
            "code": "TEST-VTAC",
            "account_type": "income",
        })
        cls.rental_account = cls.env["account.account"].create({
            "name": "Ingresos por alquiler test",
            "code": "TEST-ALQ",
            "account_type": "income_other",
        })
        cls.categ_rental_account = cls.env["account.account"].create({
            "name": "Ingresos por alquiler categoria test",
            "code": "TEST-ALQC",
            "account_type": "income_other",
        })
        cls.category = cls.env["product.category"].create({
            "name": "Cristaleria test",
            "property_account_income_categ_id": cls.categ_sale_account.id,
            "property_account_income_rental_categ_id": cls.categ_rental_account.id,
            "sale_taxes_id": [Command.set(cls.tax_sale_a.ids)],
            "rental_taxes_id": [Command.set(cls.tax_sale_b.ids)],
        })
        cls.product = cls.env["product.product"].create({
            "name": "Producto vendible y alquilable",
            "sale_ok": True,
            "rent_ok": True,
            "list_price": 100.0,
            "categ_id": cls.category.id,
            "property_account_income_id": cls.sale_account.id,
            "property_account_rental_income_id": cls.rental_account.id,
        })
        cls.template = cls.product.product_tmpl_id

    # ------------------------------------------------------------------
    # Resolution chains (product -> category -> standard)
    # ------------------------------------------------------------------

    def test_rental_account_prefers_product_over_category(self):
        self.assertEqual(
            self.template._get_rental_income_account(self.env.company),
            self.rental_account,
        )

    def test_rental_account_falls_back_to_category(self):
        self.product.property_account_rental_income_id = False
        self.assertEqual(
            self.template._get_rental_income_account(self.env.company),
            self.categ_rental_account,
        )

    def test_rental_account_falls_back_to_standard_income_account(self):
        self.product.property_account_rental_income_id = False
        self.category.property_account_income_rental_categ_id = False
        self.assertEqual(
            self.template._get_rental_income_account(self.env.company),
            self.sale_account,
        )

    def test_sale_taxes_prefer_product_over_category(self):
        self.template.taxes_id = [Command.set(self.tax_sale_b.ids)]
        self.assertEqual(
            self.template._get_sale_income_taxes(self.env.company),
            self.tax_sale_b,
        )

    def test_sale_taxes_fall_back_to_category(self):
        self.template.taxes_id = [Command.clear()]
        self.assertEqual(
            self.template._get_sale_income_taxes(self.env.company),
            self.tax_sale_a,
        )

    def test_rental_taxes_prefer_product_over_category(self):
        self.template.rental_taxes_id = [Command.set(self.tax_sale_a.ids)]
        self.assertEqual(
            self.template._get_rental_income_taxes(self.env.company),
            self.tax_sale_a,
        )

    def test_rental_taxes_fall_back_to_category(self):
        self.assertEqual(
            self.template._get_rental_income_taxes(self.env.company),
            self.tax_sale_b,
        )

    def test_rental_taxes_fall_back_to_sale_taxes(self):
        self.category.rental_taxes_id = [Command.clear()]
        self.template.taxes_id = [Command.set(self.tax_sale_a.ids)]
        self.assertEqual(
            self.template._get_rental_income_taxes(self.env.company),
            self.tax_sale_a,
        )

    # ------------------------------------------------------------------
    # Sale order line integration
    # ------------------------------------------------------------------

    def _make_order_line(self, is_rental=False):
        order = self.env["sale.order"].create({
            "partner_id": self.partner_a.id,
            "order_line": [Command.create({
                "product_id": self.product.id,
                "product_uom_qty": 1.0,
                "price_unit": 100.0,
            })],
        })
        line = order.order_line.filtered(lambda sol: not sol.display_type)[:1]
        if is_rental:
            if "is_rental" not in line._fields:
                self.skipTest("sale_renting no esta instalado en esta base de datos")
            line.is_rental = True
            line.flush_recordset()
        return line

    def test_regular_sale_uses_standard_income_account(self):
        line = self._make_order_line()
        values = line._prepare_invoice_line()
        self.assertEqual(values.get("account_id"), self.sale_account.id)

    def test_regular_sale_keeps_product_taxes(self):
        self.template.taxes_id = [Command.set(self.tax_sale_b.ids)]
        line = self._make_order_line()
        self.assertEqual(line.tax_ids, self.tax_sale_b)

    def test_regular_sale_takes_category_taxes_when_product_is_empty(self):
        self.template.taxes_id = [Command.clear()]
        line = self._make_order_line()
        self.assertEqual(line.tax_ids, self.tax_sale_a)

    def test_rental_line_uses_rental_account_and_taxes(self):
        line = self._make_order_line(is_rental=True)
        values = line._prepare_invoice_line()
        self.assertEqual(values.get("account_id"), self.rental_account.id)
        self.assertEqual(line.tax_ids, self.tax_sale_b)

    def test_sale_line_in_rental_order_keeps_standard_configuration(self):
        """A broken/unreturned item invoiced inside a rental order stays a sale."""
        line = self._make_order_line(is_rental=True)
        sale_line = self.env["sale.order.line"].create({
            "order_id": line.order_id.id,
            "product_id": self.product.id,
            "product_uom_qty": 1.0,
            "price_unit": 100.0,
        })
        self.assertFalse(sale_line.is_rental)
        values = sale_line._prepare_invoice_line()
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

    def test_rental_taxes_are_mapped_by_fiscal_position(self):
        fiscal_position = self.env["account.fiscal.position"].create({
            "name": "Mapeo impuestos alquiler test",
            "tax_ids": [Command.create({
                "tax_src_id": self.tax_sale_b.id,
                "tax_dest_id": self.tax_sale_a.id,
            })],
        })
        line = self._make_order_line(is_rental=True)
        line.order_id.fiscal_position_id = fiscal_position
        line.invalidate_recordset(["tax_ids"])
        line._compute_tax_ids()
        self.assertEqual(line.tax_ids, self.tax_sale_a)
