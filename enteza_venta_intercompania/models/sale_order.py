from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # `prefetch=False` en los dos: entre que el servidor carga el código y que la instalación
    # crea las columnas, cualquier lectura de pedidos las pediría y fallaría.
    enteza_cesion_intercompania = fields.Boolean(
        string="Cesión intercompañía",
        copy=False,
        tracking=True,
        prefetch=False,
        help="Alquiler con el que esta compañía cede material a otra del grupo. Cuando la "
             "receptora factura faltas de ese material a su cliente, se prepara aquí un "
             "presupuesto de venta a la receptora por las mismas unidades.",
    )
    enteza_cesion_company_dest_id = fields.Many2one(
        'res.company',
        string="Compañía receptora",
        compute='_compute_enteza_cesion_company_dest_id',
        store=True,
        index=True,
        prefetch=False,
    )

    @api.depends('enteza_cesion_intercompania', 'partner_id')
    def _compute_enteza_cesion_company_dest_id(self):
        # sudo(): se busca la compañía cuyo contacto es el cliente del pedido, y el usuario
        # puede no tener acceso a ella. Sólo se lee su id.
        companies = self.env['res.company'].sudo().search([])
        company_by_partner = {company.partner_id.id: company.id for company in companies}
        for order in self:
            partner = order.partner_id.commercial_partner_id
            order.enteza_cesion_company_dest_id = (
                order.enteza_cesion_intercompania and company_by_partner.get(partner.id) or False
            )

    @api.constrains('enteza_cesion_intercompania', 'partner_id', 'company_id', 'is_rental_order')
    def _check_enteza_cesion_intercompania(self):
        for order in self.filtered('enteza_cesion_intercompania'):
            if not order.is_rental_order:
                raise ValidationError(_(
                    "%s no es un pedido de alquiler: sólo un alquiler puede ser una cesión "
                    "intercompañía.", order.name))
            dest = order.enteza_cesion_company_dest_id
            if not dest or dest == order.company_id:
                raise ValidationError(_(
                    "En una cesión intercompañía el cliente tiene que ser otra compañía del "
                    "grupo (%s no lo es).", order.partner_id.display_name))
