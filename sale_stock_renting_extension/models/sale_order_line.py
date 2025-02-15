# -*- coding: utf-8 -*-
from odoo import api, fields, models
import logging
_logger = logging.getLogger(__name__)

class RentalOrderLine(models.Model):
    _inherit = "sale.order.line"

    # Nuevo campo para almacenar la cantidad disponible sin filtrar por warehouse
    virtual_available_total_at_date = fields.Float(
        string="Global Virtual Available at Date",
        help="Cantidad disponible en todos los almacenes para este producto en el intervalo de fechas.",
    )

    virtual_available_at_date = fields.Float(
        string="Virtual Available at Date",
        help="Cantidad disponible en un almacen determinado para este producto en el intervalo de fechas.",
    )

    @api.depends('reservation_begin', 'return_date', 'product_id')
    def _compute_qty_at_date(self):
        """
        Esta función ya computa la cantidad disponible de un producto para un intervalo
        en un almacén específico. Se amplía para que también compute la cantidad disponible
        sin tener en cuenta el almacén (todos los almacenes).
        """
        # 1) Filtramos líneas que NO son de alquiler (non_rental)
        non_rental = self.filtered(lambda sol: not sol.is_rental)
        # Llamamos al super para que procese esas líneas no-rental con la lógica estándar
        super(RentalOrderLine, non_rental)._compute_qty_at_date()

        # 2) Filtramos las líneas de alquiler que sean storable
        rented_product_lines = (self - non_rental).filtered(
            lambda l: l.product_id and l.product_id.is_storable
        )

        # 3) Valores por defecto para inicializar campos
        line_default_values = {
            'virtual_available_at_date': 0.0,
            'scheduled_date': False,
            'forecast_expected_date': False,
            'free_qty_today': 0.0,
            'qty_available_today': False,
            # Añadimos también el nuevo campo, para asegurarnos de que queda a 0.0 por defecto
            'virtual_available_total_at_date': 0.0,
        }

        # 4) Particionamos las líneas según su periodo de alquiler y almacén
        #    y procesamos cada bloque
        for (from_date, to_date, warehouse_id), line_ids in rented_product_lines._partition_so_lines_by_rental_period():
            lines = self.env['sale.order.line'].browse(line_ids)
            for line in lines:
                # -------------------------------------------------------------
                # Cálculo original: disponibilidad en el almacén warehouse_id
                # -------------------------------------------------------------
                rentable_qty = line.product_id.with_context(
                    from_date=from_date,
                    to_date=to_date,
                    warehouse_id=warehouse_id
                ).qty_available

                # Si la fecha de inicio aún no ha llegado, sumamos lo que está en alquiler
                if from_date > fields.Datetime.now():
                    rentable_qty += line.product_id.with_context(
                        warehouse_id=line.order_id.warehouse_id.id
                    ).qty_in_rent

                rented_qty_during_period = line.product_id._get_unavailable_qty(
                    from_date,
                    to_date,
                    ignored_soline_id=line and line.id,
                    warehouse_id=line.order_id.warehouse_id.id,
                )
                virtual_available_at_date = max(rentable_qty - rented_qty_during_period, 0)

                # -------------------------------------------------------------
                # NUEVO Cálculo: disponibilidad en TODOS los almacenes
                # -------------------------------------------------------------
                # 1) Obtenemos la cantidad disponible sin filtrar por almacén
                rentable_qty_global = line.product_id.with_context(
                    from_date=from_date,
                    to_date=to_date,
                    warehouse_id=False  # Sin warehouse
                ).qty_available

                # Si aún no ha llegado la fecha de inicio, sumamos también lo que está en alquiler
                # globalmente (sin warehouse). Dependiendo de tu implementación de qty_in_rent,
                # puede que ya sea global, o que necesites un contexto sin warehouse_id.
                if from_date > fields.Datetime.now():
                    rentable_qty_global += line.product_id.with_context(
                        warehouse_id=False
                    ).qty_in_rent

                # 2) Obtenemos la cantidad ya alquilada en ese periodo a nivel global
                rented_qty_during_period_global = line.product_id._get_unavailable_qty(
                    from_date,
                    to_date,
                    ignored_soline_id=line and line.id,
                    warehouse_id=False  # Sin warehouse
                )

                # 3) Calculamos la disponibilidad "global"
                virtual_available_total_at_date = max(
                    rentable_qty_global - rented_qty_during_period_global,
                    0
                )

                # -------------------------------------------------------------
                # 5) Actualizamos los campos en la línea
                # -------------------------------------------------------------
                line.update({
                    **line_default_values,
                    'virtual_available_at_date': virtual_available_at_date,
                    'scheduled_date': from_date,
                    'free_qty_today': virtual_available_at_date,

                    # Guardamos también la disponibilidad global
                    'virtual_available_total_at_date': virtual_available_total_at_date,
                })

        # 6) A las líneas de alquiler que no entren en el caso anterior,
        #    les establecemos los valores por defecto (que incluyan el nuevo campo en 0)
        ((self - non_rental) - rented_product_lines).update(line_default_values)

