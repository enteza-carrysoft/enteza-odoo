from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    # `prefetch=False` en los dos: un campo de `res.company` sin él se cuela en cualquier
    # lectura de la compañía, y entre que el servidor carga el código y que la actualización
    # crea las columnas, esas lecturas fallan (patrón completo en
    # enteza_prestamo_intercompania/models/res_company.py).
    enteza_ic_owner_company_id = fields.Many2one(
        'res.company',
        string="Material cedido por",
        prefetch=False,
        help="Compañía dueña del material que esta compañía alquila. Al publicar aquí una "
             "factura de faltas, la dueña factura a esta compañía las mismas unidades a "
             "coste. Vacío: esta compañía no factura material ajeno.",
    )
    enteza_ic_journal_id = fields.Many2one(
        'account.journal',
        string="Diario de la factura intercompañía",
        prefetch=False,
        domain="[('type', '=', 'sale'), ('company_id', '=', enteza_ic_owner_company_id)]",
        help="Diario de ventas de la compañía dueña en el que se crea la factura a esta "
             "compañía por el material perdido.",
    )

    @api.constrains('enteza_ic_owner_company_id', 'enteza_ic_journal_id')
    def _check_enteza_ic_owner_company_id(self):
        for company in self.filtered('enteza_ic_owner_company_id'):
            owner = company.enteza_ic_owner_company_id
            if owner == company:
                raise ValidationError(_("Una compañía no puede cederse material a sí misma."))
            journal = company.sudo().enteza_ic_journal_id
            if journal and (journal.company_id != owner or journal.type != 'sale'):
                raise ValidationError(_(
                    "El diario de la factura intercompañía tiene que ser de ventas y de %s.",
                    owner.name))
