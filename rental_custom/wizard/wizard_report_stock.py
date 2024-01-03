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

    def action_create_sale(self):
        picking_id=self.env['stock.picking'].browse(self.env.context.get('active_id') )
        
        data=[]
        for line in picking_id.move_ids_without_package:
            data.append((0,0,{
                'product_id':line.product_id.id,
                'display_product_id':line.product_id.id,
                'price_unit':line.sale_line_id.price_unit,
                'warehouses_id':line.sale_line_id.warehouses_id.id or False,
                'product_uom_qty':line.product_uom_qty
                }))
        values={
            'partner_id':picking_id.partner_id.id,
            'type_id':1,
            'order_line':data
        }
        sale_id=self.env['sale.order'].create(values)
        #picking_id.write({'sale_order_rental_id':sale_id.id})
        return True

