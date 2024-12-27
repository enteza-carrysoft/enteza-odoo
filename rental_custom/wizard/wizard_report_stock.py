# Copyright 2019 Tecnativa - Ernesto Tejeda
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

class WizardCreateSale(models.TransientModel):
    _name = "wizards.create.sale"
    _description = "Product pack line"

    name=fields.Char(string="Nombre")

    picking_ids = fields.Many2many(
        comodel_name='stock.picking',
        string='Pickings',
        required=True,
        help="Select pickings to create a sale order."
    )

    def action_create_sale(self):
        data = []
        for picking in self.picking_ids:
            for line in picking.move_ids_without_package:
                data.append((0, 0, {
                    'product_id': line.product_id.id,
                    'display_product_id': line.product_id.id,
                    'price_unit': line.sale_line_id.product_id.rented_product_tmpl_id.list_price,
                    'warehouses_id': line.sale_line_id.warehouses_id.id or False,
                    'product_uom_qty': line.product_uom_qty
                }))

        values = {
            'partner_id':self.picking_ids[0].client_id.id,
            'type_id':1,
            'order_line':data
        }

        sale_id = self.env['sale.order'].create(values)
        origins = ", ".join(p.origin for p in self.picking_ids if p.origin)
        if origins:
            sale_id.message_post(body="Documentos origen: %s" % origins)

        return {
            'name': 'Sale Order',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'sale.order',
            'res_id': sale_id.id,
            'target': 'new',
        }

