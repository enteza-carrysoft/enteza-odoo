from odoo import api, models, fields, _, tools



class AccountMoveLineInvoiceAdd(models.Model):
    _inherit = "account.move.line"
