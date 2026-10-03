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
        help="Alquiler con el que esta compañía cede material a otra del grupo: sus líneas de "
             "material van a 0 € y, al validar sus albaranes, se preparan los de la receptora. "
             "La factura de faltas a la receptora no depende de esto: ver la ficha de la "
             "compañía receptora.",
    )
    enteza_cesion_company_dest_id = fields.Many2one(
        'res.company',
        string="Compañía receptora",
        compute='_compute_enteza_cesion_company_dest_id',
        store=True,
        index=True,
        prefetch=False,
    )

    enteza_cesion_warehouse_dest_id = fields.Many2one(
        'stock.warehouse',
        string="Almacén receptor",
        compute='_compute_enteza_cesion_warehouse_dest_id',
        store=True,
        readonly=False,
        copy=False,
        prefetch=False,
        domain="[('company_id', '=', enteza_cesion_company_dest_id)]",
        help="Almacén de la compañía receptora donde entra el material cedido. Al validar la "
             "entrega de la cesión se le prepara ahí la recepción, y al validar una "
             "devolución, la salida.",
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

    @api.depends('enteza_cesion_company_dest_id')
    def _compute_enteza_cesion_warehouse_dest_id(self):
        for order in self:
            dest = order.enteza_cesion_company_dest_id
            if dest and order.enteza_cesion_warehouse_dest_id.sudo().company_id == dest:
                continue
            # sudo(): el almacén es de la otra compañía. Se propone el primero; si tiene
            # varios, se elige a mano (habrá más almacenes, confirmado por el cliente).
            order.enteza_cesion_warehouse_dest_id = dest and self.env['stock.warehouse'].sudo().search(
                [('company_id', '=', dest.id)], limit=1).id or False

    @api.constrains('enteza_cesion_intercompania', 'partner_id', 'company_id', 'is_rental_order',
                    'enteza_cesion_warehouse_dest_id', 'state')
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
            warehouse = order.enteza_cesion_warehouse_dest_id.sudo()
            if warehouse and warehouse.company_id != dest:
                raise ValidationError(_(
                    "El almacén receptor %(warehouse)s no es de %(company)s.",
                    warehouse=warehouse.name, company=dest.name))
            if order.state == 'sale' and not warehouse:
                raise ValidationError(_(
                    "Falta el almacén receptor de la cesión %s.", order.name))
