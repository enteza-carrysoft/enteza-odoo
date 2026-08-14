from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    top_bar_color = fields.Integer(
        string="Identification color",
        default=0,
        help=(
            "Color used in the thin strip at the top of the Odoo backend "
            "to identify the active company. It does not change the user's "
            "Light/Dark appearance preference."
        ),
    )
