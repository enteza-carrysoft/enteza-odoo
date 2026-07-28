from odoo import models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _is_rental_income_line(self):
        """Return whether this sale line belongs to the Rental workflow.

        Odoo's Rental application marks rental quotations/orders with
        ``sale.order.is_rental``. The defensive fallback to a line-level flag
        makes the addon tolerant of minor changes/customizations in sale_renting.
        """
        self.ensure_one()
        order_is_rental = bool(
            "is_rental" in self.order_id._fields and self.order_id.is_rental
        )
        line_is_rental = bool(
            "is_rental" in self._fields and self.is_rental
        )
        return order_is_rental or line_is_rental

    def _get_rental_invoice_account(self):
        """Get the company-aware and fiscal-position-mapped rental account."""
        self.ensure_one()
        if not self.product_id or not self._is_rental_income_line():
            return self.env["account.account"]

        company = self.company_id or self.order_id.company_id or self.env.company
        account = self.product_id.product_tmpl_id._get_rental_income_account(company)

        # Preserve standard Odoo fiscal-position behavior: first choose the
        # product account, then map it through the order's fiscal position.
        fiscal_position = self.order_id.fiscal_position_id
        if account and fiscal_position:
            account = fiscal_position.map_account(account)

        return account

    def _prepare_invoice_line(self, **optional_values):
        values = super()._prepare_invoice_line(**optional_values)

        # A section/note or a line without product must keep the standard values.
        if self.display_type or not self.product_id:
            return values

        rental_account = self._get_rental_invoice_account()
        if rental_account:
            values["account_id"] = rental_account.id

        return values
