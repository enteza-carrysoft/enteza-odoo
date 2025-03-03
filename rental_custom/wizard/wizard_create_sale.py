# Copyright 2019 Tecnativa - Ernesto Tejeda (Adaptado para Odoo 18)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class WizardCreateSale(models.TransientModel):
    _name = "wizards.create.sale"
    _description = "Crear Orden de Venta desde Albarán"

    name = fields.Char(string="Nombre")

    picking_ids = fields.Many2many(
        comodel_name='stock.picking',
        string='Albaranes',
        required=True,
        help="Seleccione albaranes para crear una orden de venta."
    )

    def action_create_sale(self):
        data = []
        for picking in self.picking_ids:
            for line in picking.move_ids:  # En Odoo 18 es move_ids en lugar de move_ids_without_package
                # Obtener información de precio desde la línea de venta original
                price = 0
                if line.sale_line_id and line.sale_line_id.product_id.rented_product_tmpl_id:
                    price = line.sale_line_id.product_id.rented_product_tmpl_id.list_price
                elif line.product_id:
                    price = line.product_id.list_price
                
                # Obtener warehouse_id
                warehouse_id = False
                if line.sale_line_id and hasattr(line.sale_line_id, 'warehouses_id'):
                    warehouse_id = line.sale_line_id.warehouses_id.id
                elif picking.picking_type_id and picking.picking_type_id.warehouse_id:
                    warehouse_id = picking.picking_type_id.warehouse_id.id
                
                line_values = {
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.product_uom_qty,
                    'price_unit': price,
                }
                
                # Agregar display_product_id y warehouses_id solo si existen en el modelo
                if hasattr(self.env['sale.order.line'], 'display_product_id'):
                    line_values['display_product_id'] = line.product_id.id
                    
                if hasattr(self.env['sale.order.line'], 'warehouses_id') and warehouse_id:
                    line_values['warehouses_id'] = warehouse_id
                
                data.append((0, 0, line_values))

        # Obtener el cliente desde el albarán
        partner_id = self.picking_ids[0].partner_id.id
        if hasattr(self.picking_ids[0], 'client_id') and self.picking_ids[0].client_id:
            partner_id = self.picking_ids[0].client_id.id

        values = {
            'partner_id': partner_id,
            'order_line': data
        }
        
        # Agregar type_id solo si existe en el modelo
        if hasattr(self.env['sale.order'], 'type_id'):
            values['type_id'] = 1

        sale_id = self.env['sale.order'].create(values)
        
        # Agregar mensaje con documentos origen
        origins = ", ".join(p.origin for p in self.picking_ids if p.origin)
        if origins:
            sale_id.message_post(body=_("Documentos origen: %s") % origins)

        return {
            'name': _('Orden de Venta'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'sale.order',
            'res_id': sale_id.id,
            'target': 'current',  # Cambio a 'current' para abrir en la misma ventana
        }
