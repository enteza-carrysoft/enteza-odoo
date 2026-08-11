import base64
import io

from openpyxl import Workbook
from odoo.tests.common import TransactionCase


class TestSaleOrderMissingImport(TransactionCase):

    def test_import_creates_compensation_sales(self):
        partner = self.env["res.partner"].create({
            "name": "Cliente de prueba de faltas",
            "vat": "B12345678",
        })
        product = self.env["product.product"].create({
            "name": "Articulo de prueba de faltas",
            "default_code": "FALTA-PRUEBA",
            "lst_price": 25.0,
        })
        csv_content = (
            "CIF;Codigo articulo;Unidades\n"
            "B12345678;FALTA-PRUEBA;2\n"
        )
        wizard = self.env["rental.sale.order.import.wizard"].create({
            "company_id": self.env.company.id,
            "filename": "faltas.csv",
            "file": base64.b64encode(csv_content.encode()),
        })

        action = wizard.action_import()
        order_ids = action["domain"][0][2]
        order = self.env["sale.order"].browse(order_ids)

        self.assertEqual(order.partner_id, partner)
        self.assertFalse(order.is_rental_order)
        self.assertEqual(len(order.order_line), 1)
        self.assertEqual(order.order_line.product_id, product)
        self.assertEqual(order.order_line.product_uom_qty, 2.0)
        self.assertFalse(order.order_line.is_rental)

    def test_import_accepts_excel_file(self):
        partner = self.env["res.partner"].create({
            "name": "Cliente de prueba Excel",
            "vat": "B87654321",
        })
        product = self.env["product.product"].create({
            "name": "Articulo de prueba Excel",
            "default_code": "FALTA-EXCEL",
        })
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["CIF", "Codigo articulo", "Unidades"])
        sheet.append(["B87654321", "FALTA-EXCEL", 3])
        output = io.BytesIO()
        workbook.save(output)
        wizard = self.env["rental.sale.order.import.wizard"].create({
            "company_id": self.env.company.id,
            "filename": "faltas.xlsx",
            "file": base64.b64encode(output.getvalue()),
        })

        action = wizard.action_import()
        order = self.env["sale.order"].browse(action["domain"][0][2])

        self.assertEqual(order.partner_id, partner)
        self.assertEqual(order.order_line.product_id, product)
        self.assertEqual(order.order_line.product_uom_qty, 3.0)
