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
                # Obtener información de precio de forma segura
                price = 0
                
                # Primero intentamos obtener el precio desde la línea de venta original si existe
                if line.sale_line_id and line.sale_line_id.price_unit:
                    price = line.sale_line_id.price_unit
                # Si no hay línea de venta o no tiene precio, usamos el precio del producto
                elif line.product_id:
                    price = line.product_id.list_price
                
                # Obtener warehouse_id
                warehouse_id = False
                if line.sale_line_id and hasattr(line.sale_line_id, 'warehouses_id') and line.sale_line_id.warehouses_id:
                    warehouse_id = line.sale_line_id.warehouses_id.id
                elif picking.picking_type_id and picking.picking_type_id.warehouse_id:
                    warehouse_id = picking.picking_type_id.warehouse_id.id
                
                # Preparamos los valores básicos de la línea
                line_values = {
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.product_uom_qty,
                    'price_unit': price,
                }
                
                # Verificamos si el modelo sale.order.line tiene estos campos antes de usarlos
                SaleOrderLine = self.env['sale.order.line']
                
                if hasattr(SaleOrderLine, 'display_product_id'):
                    line_values['display_product_id'] = line.product_id.id
                    
                if hasattr(SaleOrderLine, 'warehouses_id') and warehouse_id:
                    line_values['warehouses_id'] = warehouse_id
                
                # Si existe un campo product_uom en el modelo, lo usamos
                if hasattr(SaleOrderLine, 'product_uom') and line.product_uom:
                    line_values['product_uom'] = line.product_uom.id
                
                data.append((0, 0, line_values))

        # Obtener el cliente desde el albarán
        partner_id = False
        if hasattr(self.picking_ids[0], 'client_id') and self.picking_ids[0].client_id:
            partner_id = self.picking_ids[0].client_id.id
        else:
            partner_id = self.picking_ids[0].partner_id.id
        
        if not partner_id:
            raise ValidationError(_("No se pudo determinar el cliente para la orden de venta."))

        # Preparamos los valores básicos de la orden de venta
        values = {
            'partner_id': partner_id,
            'order_line': data
        }
        
        # Si el albarán tiene un origin, lo copiamos a la orden de venta
        if self.picking_ids[0].origin:
            values['origin'] = self.picking_ids[0].origin
        
        # Verificamos si existe el campo type_id en el modelo sale.order
        if hasattr(self.env['sale.order'], 'type_id'):
            values['type_id'] = 1

        # Creamos la orden de venta
        sale_id = self.env['sale.order'].create(values)
        
        # Agregamos un mensaje con los documentos origen
        origins = ", ".join(p.name for p in self.picking_ids)
        if origins:
            sale_id.message_post(body=_("Creado desde albaranes: %s") % origins)

        # Devolvemos la acción para mostrar la orden de venta creada
        return {
            'name': _('Orden de Venta'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'sale.order',
            'res_id': sale_id.id,
            'target': 'current',
        }
