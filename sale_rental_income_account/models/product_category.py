from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    sale_taxes_id = fields.Many2many(
        comodel_name="account.tax",
        relation="product_categ_sale_taxes_rel",
        column1="categ_id",
        column2="tax_id",
        string="Impuestos de venta",
        domain=[("type_tax_use", "=", "sale")],
        help=(
            "Impuestos aplicados al facturar una venta de los productos de esta "
            "categoría cuando el producto no tiene impuestos de cliente propios. "
            "Si el producto ya tiene impuestos, prevalecen los del producto."
        ),
    )

    property_account_income_rental_categ_id = fields.Many2one(
        comodel_name="account.account",
        string="Cuenta de ingresos por alquiler",
        company_dependent=True,
        ondelete="restrict",
        domain="[('account_type', 'in', ('income', 'income_other'))]",
        help=(
            "Cuenta de ingresos usada al facturar líneas de alquiler de los "
            "productos de esta categoría cuando el producto no tiene cuenta de "
            "alquiler propia."
        ),
    )

    rental_taxes_id = fields.Many2many(
        comodel_name="account.tax",
        relation="product_categ_rental_taxes_rel",
        column1="categ_id",
        column2="tax_id",
        string="Impuestos de alquiler",
        domain=[("type_tax_use", "=", "sale")],
        help=(
            "Impuestos aplicados al facturar líneas de alquiler de los productos "
            "de esta categoría cuando el producto no tiene impuestos de alquiler "
            "propios."
        ),
    )
