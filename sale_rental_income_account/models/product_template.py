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
            "Cuenta de ingresos utilizada cuando el producto se factura desde un "
            "pedido de alquiler. Si no se configura, Odoo utiliza la cuenta de "
            "ingresos estándar del producto o de su categoría. La posición fiscal "
            "del pedido puede sustituir posteriormente esta cuenta."
        ),
    )

    def _get_rental_income_account(self, company=None):
        """Return the rental income account for the requested company.

        The field is company-dependent. If no rental-specific account is set,
        return the normal product/category income account so callers always get
        the same fallback as standard Odoo invoicing.
        """
        self.ensure_one()
        company = company or self.env.company
        product = self.with_company(company)
        return (
            product.property_account_rental_income_id
            or product.property_account_income_id
            or product.categ_id.with_company(company).property_account_income_categ_id
        )

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

