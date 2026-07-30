from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    property_account_rental_income_id = fields.Many2one(
        comodel_name="account.account",
        string="Cuenta de ingresos por alquiler",
        company_dependent=True,
        check_company=True,
        domain="[('account_type', 'in', ('income', 'income_other'))]",
        help=(
            "Cuenta de ingresos utilizada cuando el producto se factura desde una "
            "línea de alquiler. Si se deja vacía se usa la cuenta de alquiler de la "
            "categoría y, en su defecto, la cuenta de ingresos estándar. La posición "
            "fiscal del pedido puede sustituir posteriormente esta cuenta."
        ),
    )

    rental_taxes_id = fields.Many2many(
        comodel_name="account.tax",
        relation="product_template_rental_taxes_rel",
        column1="product_tmpl_id",
        column2="tax_id",
        string="Impuestos de alquiler",
        domain=[("type_tax_use", "=", "sale")],
        help=(
            "Impuestos aplicados al facturar una línea de alquiler de este producto. "
            "Si se deja vacío se usan los impuestos de alquiler de la categoría y, en "
            "su defecto, los impuestos de cliente estándar."
        ),
    )

    def _get_rental_income_account(self, company=None):
        """Rental income account: product -> category -> standard income account.

        Both product and category fields are company-dependent, so the whole
        chain is read with the requested company activated.
        """
        self.ensure_one()
        company = company or self.env.company
        product = self.with_company(company)
        category = product.categ_id.with_company(company)
        return (
            product.property_account_rental_income_id
            or category.property_account_income_rental_categ_id
            or product.property_account_income_id
            or category.property_account_income_categ_id
        )

    def _get_sale_income_taxes(self, company=None):
        """Sale taxes: product ``taxes_id`` -> category ``sale_taxes_id``.

        Mirrors what ``sale.order.line._compute_tax_ids`` does natively and only
        adds the category level, which Odoo does not provide out of the box.
        """
        self.ensure_one()
        company = company or self.env.company
        product = self.with_company(company)
        taxes = product.taxes_id._filter_taxes_by_company(company)
        if not taxes:
            taxes = product.categ_id.sale_taxes_id._filter_taxes_by_company(company)
        return taxes

    def _get_rental_income_taxes(self, company=None):
        """Rental taxes: product -> category -> standard sale taxes."""
        self.ensure_one()
        company = company or self.env.company
        product = self.with_company(company)
        taxes = product.rental_taxes_id._filter_taxes_by_company(company)
        if not taxes:
            taxes = product.categ_id.rental_taxes_id._filter_taxes_by_company(company)
        if not taxes:
            taxes = product._get_sale_income_taxes(company)
        return taxes

    @api.constrains("property_account_rental_income_id")
    def _validate_rental_income_account(self):
        for product in self:
            account = product.property_account_rental_income_id
            if account and account.account_type not in ("income", "income_other"):
                raise ValidationError(
                    _(
                        "La cuenta de ingresos por alquiler del producto «%(product)s» "
                        "debe ser una cuenta de ingresos.",
                        product=product.display_name,
                    )
                )
