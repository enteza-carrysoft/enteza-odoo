# Copyright 2019 Tecnativa - Ernesto Tejeda
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class WizardReportStock(models.TransientModel):
    _name = "wizards.report.stock"
    _description = "Product pack line"


    def export_action(self):
        if self.options=='product' and not self.product_ids:
            raise ValidationError("Indique al menos un articulo")
        if self.options=='category' and not self.categ_id:
            raise ValidationError("Indique al menos una clasificacion")
        if not self.warehouse_id:
            raise ValidationError("Indique un almacen")
        product_ids=self.product_ids.ids
        if self.options=='category' and  self.categ_id:
            product_ids=self.env['product.product'].search([('categ_id','=',self.categ_id.id),('rental', '=', True),('type', '=','product')]).ids
        return {
            'name': 'Reporte Existencias',
            'type': 'ir.actions.client',
            'tag': 'rental_dashboard',
            'context': {'product_ids':product_ids ,'date_start':self.date_start,'date_stop':self.date_stop,'warehouse_id':self.warehouse_id.id}
        }

    options=fields.Selection([('product','Por Articulo'),('category','Clasificacion')],string="Opcion",required=True)
    categ_id=fields.Many2one("product.category",string="Categoria")
    product_ids=fields.Many2many("product.product",string="Productos")
    date_start=fields.Date(string="Fecha Inicio",required=True)
    date_stop=fields.Date(string="Fecha Fin",required=True)
    warehouse_id=fields.Many2one("stock.warehouse",string="Almacen")


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
        # --- NUEVO: obtener el plazo de pago del partner ---
        partner = self.picking_ids[0].client_id.commercial_partner_id
        payment_term = partner.property_payment_term_id  # Many2one a account.payment.term

        values = {
            'partner_id':self.picking_ids[0].client_id.id,
            'type_id':1,
            'order_line':data,
            # --- NUEVO: arrastrar el plazo de pago ---
            'payment_term_id': payment_term.id if payment_term else False,
        }

        sale_id = self.env['sale.order'].create(values)
        origins = ", ".join(p.origin for p in self.picking_ids if p.origin)
        if origins:
            sale_id.message_post(body="Documentos origen: %s" % origins)

        # Opcional, si deseas vincular la orden de venta a los albaranes
#        for picking in self.picking_ids:
#            picking.write({'sale_order_rental_id': sale_id.id})

        return {
            'name': 'Sale Order',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'sale.order',
            'res_id': sale_id.id,
            'target': 'new',
        }

