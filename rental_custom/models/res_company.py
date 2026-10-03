from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # `prefetch=False`: un campo de `res.company` sin él se cuela en cualquier lectura de la
    # compañía, y entre que el servidor carga el código y que la actualización crea la columna,
    # esas lecturas fallan (patrón completo en enteza_prestamo_intercompania/models/res_company.py).
    rental_missing_journal_id = fields.Many2one(
        'account.journal',
        string="Diario de facturas de faltas",
        prefetch=False,
        domain="[('type', '=', 'sale'), ('company_id', '=', id)]",
        help="Diario en el que se facturan los pedidos de faltas («Facturar las Faltas» e "
             "importación de faltas). Vacío: el diario de ventas por defecto.",
    )
