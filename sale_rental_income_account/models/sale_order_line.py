from odoo import api, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _is_rental_income_line(self):
        """Whether this line must use the rental income configuration.

        The check is done at *line* level, never at order level: a rental order
        may also contain plain sale lines (broken or unreturned material) and
        those must keep the standard sale accounts and taxes.
        """
        self.ensure_one()
        return bool("is_rental" in self._fields and self.is_rental)

    def _get_income_company(self):
        self.ensure_one()
        return self.company_id or self.order_id.company_id or self.env.company

    def _get_income_taxes(self):
        """Taxes for this line, resolved through the product/category chain."""
        self.ensure_one()
        company = self._get_income_company()
        template = self.product_id.product_tmpl_id
        if self._is_rental_income_line():
            return template._get_rental_income_taxes(company)
        return template._get_sale_income_taxes(company)

    def _get_rental_invoice_account(self):
        """Company-aware and fiscal-position-mapped rental income account."""
        self.ensure_one()
        if not self.product_id or not self._is_rental_income_line():
            return self.env["account.account"]

        company = self._get_income_company()
        account = self.product_id.product_tmpl_id._get_rental_income_account(company)

        # Preserve standard Odoo behavior: first choose the product account,
        # then map it through the order's fiscal position.
        fiscal_position = self.order_id.fiscal_position_id
        if account and fiscal_position:
            account = fiscal_position.map_account(account)

        return account

    # The full depends list must be restated: overriding a compute method
    # replaces the dependencies declared by the parent implementation.
    @api.depends("product_id", "company_id", "is_rental")
    def _compute_tax_ids(self):
        super()._compute_tax_ids()
        for line in self:
            if line.display_type or not line.product_id or line.is_downpayment:
                continue
            if line.product_type == "combo":
                continue
            taxes = line._get_income_taxes()
            if not taxes:
                continue
            line.tax_ids = line.order_id.fiscal_position_id.map_tax(taxes)

    def _prepare_invoice_line(self, **optional_values):
        values = super()._prepare_invoice_line(**optional_values)

        # A section/note or a line without product must keep the standard values.
        if self.display_type or not self.product_id:
            return values

        rental_account = self._get_rental_invoice_account()
        if rental_account:
            values["account_id"] = rental_account.id

        return values
