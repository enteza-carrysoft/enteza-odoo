# Copyright 2019 Tecnativa - Ernesto Tejeda (Adaptado para Odoo 18)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class WizardCreateSale(models.TransientModel):
    _name = "wizards.create.sale"
    _description = "Crear Orden de Venta desde Albarán"

    @api.model
    def default_get(self, fields_list):
        """
        Método sobreescrito para obtener automáticamente el albarán activo
        """
        res = super(WizardCreateSale, self).default_get(fields_list)
        
        # Obtener el albarán activo desde el contexto
        active_model = self._context.get('active_model')
        active_ids = self._context.get('active_ids', [])
        
        if active_model == 'stock.picking' and active_ids:
            res['picking_ids'] = [(6, 0, active_ids)]
        
        return res

    name = fields.Char(string="Nombre")
    picking_ids = fields.Many2many(
        comodel_name='stock.picking',
        string='Albaranes',
        required=True,
        help="Albaranes para crear una orden de venta."
    )

    def action_create_sale(self):
        # Verificar que hay albaranes seleccionados
        if not self.picking_ids:
            raise ValidationError(_("No se ha seleccionado ningún albarán para crear la orden de venta."))
            
        data = []
        for picking in self.picking_ids:
            for line in picking.move_ids:
                # Obtener precio
                price = 0
#                if line.sale_line_id and line.sale_line_id.price_unit:
#                    price = line.sale_line_id.price_unit
#                elif line.product_id:
                price = line.product_id.list_price
                
                # Preparamos los valores para una línea de venta normal
                line_values = {
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.product_uom_qty,
                    'price_unit': price,
                    'name': line.product_id.name,
                }
                
                # Asegurar que se use la unidad de medida correcta
#                if line.product_uom:
#                    line_values['product_uom'] = line.product_uom.id
                
                data.append((0, 0, line_values))

        # Obtener el cliente desde el albarán
        partner_id = False
        if hasattr(self.picking_ids[0], 'client_id') and self.picking_ids[0].client_id:
            partner_id = self.picking_ids[0].client_id.id
        else:
            partner_id = self.picking_ids[0].partner_id.id
        
        if not partner_id:
            raise ValidationError(_("No se pudo determinar el cliente para la orden de venta."))

        # Valores básicos para una orden de venta normal
        values = {
            'partner_id': partner_id,
            'order_line': data
        }
        
        # Si el albarán tiene un origin, lo copiamos a la orden de venta
        if self.picking_ids[0].origin:
            values['origin'] = self.picking_ids[0].origin
        
        # Creamos la orden de venta estándar
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
