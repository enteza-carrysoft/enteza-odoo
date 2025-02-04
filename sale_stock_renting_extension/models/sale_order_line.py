# -*- coding: utf-8 -*-
from odoo import api, fields, models
from datetime import timedelta

class RentalOrderLine(models.Model):
    _inherit = 'sale.order.line'

    virtual_available_total_at_date = fields.Float(
        string="Global Available Qty", compute="_compute_qty_at_date", store=True,
        help="Cantidad global disponible entre todos los almacenes.")

    @api.depends('reservation_begin', 'return_date', 'product_id')
    def _compute_qty_at_date(self):
        # Primero, delegamos el cálculo de las líneas que no son de alquiler
        non_rental = self.filtered(lambda sol: not sol.is_rental)
        super(RentalOrderLine, non_rental)._compute_qty_at_date()
        rented_product_lines = (self - non_rental).filtered(
            lambda l: l.product_id and l.product_id.is_storable
        )
        
        line_default_values = {
            'virtual_available_at_date': 0.0,
            'virtual_available_total_at_date': 0.0,
            'scheduled_date': False,
            'forecast_expected_date': False,
            'free_qty_today': 0.0,
            'qty_available_today': False,
        }
        
        # Se agrupan las líneas por período (y almacén, para el cálculo específico)
        for (from_date, to_date, warehouse_id), line_ids in rented_product_lines._partition_so_lines_by_rental_period():
            lines = self.env['sale.order.line'].browse(line_ids)
            for line in lines:
                # -----------------------------------------------
                # Cálculo de la cantidad disponible para el almacén asignado
                # -----------------------------------------------
                rentable_qty_wh = line.product_id.with_context(
                    from_date=from_date,
                    to_date=to_date,
                    warehouse_id=warehouse_id
                ).qty_available
                if from_date > fields.Datetime.now():
                    rentable_qty_wh += line.product_id.with_context(
                        warehouse_id=line.order_id.warehouse_id.id
                    ).qty_in_rent
                rented_qty_wh = line.product_id._get_unavailable_qty(
                    from_date, to_date,
                    ignored_soline_id=line.id,
                    warehouse_id=line.order_id.warehouse_id.id,
                )
                virtual_available_wh = max(rentable_qty_wh - rented_qty_wh, 0)
                
                # -----------------------------------------------
                # Cálculo de la cantidad global disponible (entre todos los almacenes)
                # -----------------------------------------------
                rentable_qty_total = line.product_id.with_context(
                    from_date=from_date,
                    to_date=to_date
                ).qty_available
                if from_date > fields.Datetime.now():
                    rentable_qty_total += line.product_id.with_context().qty_in_rent
                rented_qty_total = line.product_id._get_unavailable_qty(
                    from_date, to_date,
                    ignored_soline_id=line.id,
                )
                virtual_available_total = max(rentable_qty_total - rented_qty_total, 0)
                
                # (Opcional) Puedes descomentar el print para depuración
                # print("Línea de pedido %s - Cantidad global disponible: %s" % (line.id, virtual_available_total))
                
                line.update(dict(line_default_values,
                    virtual_available_at_date=virtual_available_wh,
                    virtual_available_total_at_date=virtual_available_total,
                    scheduled_date=from_date,
                    free_qty_today=virtual_available_wh)
                )
        
        # Actualiza las líneas que no son de alquiler o que no se han procesado
        ((self - non_rental) - rented_product_lines).update(line_default_values)

