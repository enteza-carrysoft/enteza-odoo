import base64
import csv
import io
import unicodedata
from decimal import Decimal, InvalidOperation

from odoo import _, fields, models
from odoo.exceptions import UserError, ValidationError


class RentalSaleOrderImportWizard(models.TransientModel):
    _name = "rental.sale.order.import.wizard"
    _description = "Importar ventas por faltas"

    company_id = fields.Many2one(
        "res.company", string="Sociedad", required=True, default=lambda self: self.env.company
    )
    file = fields.Binary(string="Archivo CSV o Excel", required=True)
    filename = fields.Char(string="Nombre del archivo", required=True)

    @staticmethod
    def _header_key(value):
        value = unicodedata.normalize("NFKD", value or "")
        value = "".join(char for char in value if not unicodedata.combining(char))
        return "".join(char for char in value.lower() if char.isalnum())

    @staticmethod
    def _parse_quantity(value, row_number):
        value = (value or "").strip().replace(" ", "")
        if "," in value and "." in value:
            if value.rfind(",") > value.rfind("."):
                value = value.replace(".", "").replace(",", ".")
            else:
                value = value.replace(",", "")
        else:
            value = value.replace(",", ".")
        try:
            quantity = Decimal(value)
        except InvalidOperation:
            raise ValidationError(_("Fila %s: las unidades no son un número válido.") % row_number)
        if not quantity.is_finite() or quantity <= 0:
            raise ValidationError(_("Fila %s: las unidades deben ser mayores que cero.") % row_number)
        return float(quantity)

    def _read_rows(self):
        self.ensure_one()
        try:
            content = base64.b64decode(self.file)
        except ValueError:
            raise UserError(_("No se pudo leer el archivo seleccionado."))

        extension = self.filename.rsplit(".", 1)[-1].lower() if "." in self.filename else ""
        if extension == "csv":
            try:
                content_text = content.decode("utf-8-sig")
            except UnicodeDecodeError:
                raise UserError(_("El CSV debe estar codificado en UTF-8."))
            try:
                dialect = csv.Sniffer().sniff(content_text[:4096], delimiters=";,\t")
            except csv.Error:
                dialect = csv.excel
            rows = list(csv.reader(io.StringIO(content_text), dialect=dialect))
        elif extension == "xlsx":
            try:
                from openpyxl import load_workbook
                workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            except ImportError:
                raise UserError(_("El servidor no tiene disponible el lector de archivos Excel."))
            except Exception:
                raise UserError(_("El archivo Excel no es válido o está dañado."))
            try:
                rows = [
                    ["" if cell is None else str(cell) for cell in row]
                    for row in workbook.active.iter_rows(values_only=True)
                ]
            finally:
                workbook.close()
        else:
            raise UserError(_("Selecciona un archivo CSV o Excel (.xlsx)."))

        if not rows:
            raise ValidationError(_("El archivo está vacío."))

        headers = [self._header_key(value) for value in rows[0]]
        required = {"cif": "CIF", "codigoarticulo": "Codigo articulo", "unidades": "Unidades"}
        missing = [label for key, label in required.items() if key not in headers]
        if missing:
            raise ValidationError(
                _("Faltan las columnas obligatorias: %s.") % ", ".join(missing)
            )
        nonempty_headers = [header for header in headers if header]
        if len(nonempty_headers) != len(set(nonempty_headers)):
            raise ValidationError(_("La cabecera contiene columnas repetidas."))

        indexes = {key: headers.index(key) for key in required}
        parsed_rows = []
        for row_number, row in enumerate(rows[1:], start=2):
            if not any((value or "").strip() for value in row):
                continue
            if len(row) > len(headers):
                raise ValidationError(_("Fila %s: contiene más columnas que la cabecera.") % row_number)

            def value_for(key):
                index = indexes[key]
                return row[index].strip() if index < len(row) else ""

            vat = value_for("cif")
            product_code = value_for("codigoarticulo")
            if not vat:
                raise ValidationError(_("Fila %s: falta el CIF.") % row_number)
            if not product_code:
                raise ValidationError(_("Fila %s: falta el código de artículo.") % row_number)
            parsed_rows.append({
                "row_number": row_number,
                "vat": vat,
                "product_code": product_code,
                "quantity": self._parse_quantity(value_for("unidades"), row_number),
            })
        if not parsed_rows:
            raise ValidationError(_("El archivo no contiene líneas de pedido."))
        return parsed_rows

    def _find_partner(self, vat, row_number):
        partners = self.env["res.partner"].with_company(self.company_id).search([
            ("vat", "=", vat),
            ("active", "=", True),
            ("company_id", "in", [False, self.company_id.id]),
        ])
        commercial_partners = partners.mapped("commercial_partner_id")
        if not commercial_partners:
            raise ValidationError(_("Fila %s: no existe un cliente activo con CIF %s.") % (row_number, vat))
        if len(commercial_partners) > 1:
            raise ValidationError(
                _("Fila %s: el CIF %s corresponde a más de un cliente.") % (row_number, vat)
            )
        return commercial_partners

    def _find_product(self, product_code, row_number):
        products = self.env["product.product"].with_company(self.company_id).search([
            ("default_code", "=", product_code),
            ("active", "=", True),
            ("company_id", "in", [False, self.company_id.id]),
        ])
        if not products:
            raise ValidationError(
                _("Fila %s: no existe un artículo activo con código %s.") % (row_number, product_code)
            )
        if len(products) > 1:
            raise ValidationError(
                _("Fila %s: el código de artículo %s no es único.") % (row_number, product_code)
            )
        return products

    def action_import(self):
        self.ensure_one()
        rows = self._read_rows()
        orders = self.env["sale.order"]
        sale_order_model = self.env["sale.order"].with_company(self.company_id)
        sale_order_line_model = self.env["sale.order.line"].with_company(self.company_id)
        current_order = None
        previous_vat = None

        # Se validan todas las búsquedas antes de crear: un CSV inválido no deja pedidos parciales.
        for row in rows:
            row["partner"] = self._find_partner(row["vat"], row["row_number"])
            row["product"] = self._find_product(row["product_code"], row["row_number"])

        for row in rows:
            if row["vat"] != previous_vat:
                current_order = sale_order_model.create({
                    "partner_id": row["partner"].id,
                    "company_id": self.company_id.id,
                    "is_rental_order": False,
                })
                orders |= current_order
                previous_vat = row["vat"]

            sale_order_line_model.create({
                "order_id": current_order.id,
                "product_id": row["product"].id,
                "product_uom_qty": row["quantity"],
                "product_uom_id": row["product"].uom_id.id,
                "price_unit": row["product"].lst_price,
                "is_rental": False,
            })

        for order in orders:
            order.message_post(body=_(
                "Presupuesto de faltas creado mediante la importación del archivo %s. "
                "No generará albarán de salida al confirmarse.", self.filename
            ))
        return {
            "type": "ir.actions.act_window",
            "name": _("Pedidos de venta creados"),
            "res_model": "sale.order",
            "view_mode": "list,form",
            "domain": [("id", "in", orders.ids)],
            "target": "current",
        }
