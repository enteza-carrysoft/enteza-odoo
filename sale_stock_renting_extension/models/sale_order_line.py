# -*- coding: utf-8 -*-
from odoo import api, fields, models
import logging
_logger = logging.getLogger(__name__)

class RentalOrderLine(models.Model):
    _inherit = 'sale.order.line'

    virtual_available_at_date = fields.Float(
        string="Available Qty (Warehouse)",
        compute="_compute_qty_at_date",
        store=True,
        help="Cantidad disponible en el almacén asignado."
    )
    virtual_available_total_at_date = fields.Float(
        string="Global Available Qty",
        compute="_compute_qty_at_date",
        store=True,
        help="Cantidad global disponible entre todos los almacenes."
    )
    # Aseguramos que también se asignen valores a estos campos:
    qty_available_today = fields.Float(
        string="Qty Available Today",
        compute="_compute_qty_at_date",
        store=True
    )
    free_qty_today = fields.Float(
        string="Free Qty Today",
        compute="_compute_qty_at_date",
        store=True
    )
    scheduled_date = fields.Datetime(
        string="Scheduled Date",
        compute="_compute_qty_at_date",
        store=True
    )
    forecast_expected_date = fields.Datetime(
        string="Forecast Expected Date",
        compute="_compute_qty_at_date",
        store=True
    )

    @api.depends(
        'reservation_begin', 'return_date', 'product_id',
        'product_id.qty_available', 'product_id.qty_in_rent'
    )
    def _compute_qty_at_date(self):
        now = fields.Datetime.now()
        for line in self:
            # Si faltan datos críticos o no es línea de alquiler, asignamos valores por defecto.
            if (not line.is_rental or
                not line.product_id or
                not line.product_id.is_storable or
                not line.reservation_begin or
                not line.return_date):
                line.virtual_available_at_date = 0.0
                line.virtual_available_total_at_date = 0.0
                line.qty_available_today = 0.0
                line.free_qty_today = 0.0
                line.scheduled_date = False
                line.forecast_expected_date = False
            else:
                from_date = line.reservation_begin
                to_date = line.return_date

                # --- Cálculo para el almacén asignado ---
                rentable_qty_wh = (line.product_id.with_context(
                    from_date=from_date,
                    to_date=to_date,
                    warehouse_id=line.order_id.warehouse_id.id
                ).qty_available or 0.0)
                if from_date > now:
                    rentable_qty_wh += (line.product_id.with_context(
                        warehouse_id=line.order_id.warehouse_id.id
                    ).qty_in_rent or 0.0)
                rented_qty_wh = (line.product_id._get_unavailable_qty(
                    from_date, to_date,
                    ignored_soline_id=line.id,
                    warehouse_id=line.order_id.warehouse_id.id,
                ) or 0.0)
                virtual_available_wh = max(rentable_qty_wh - rented_qty_wh, 0)
                line.virtual_available_at_date = virtual_available_wh

                # --- Cálculo global (sin filtrar por almacén) ---
                rentable_qty_total = (line.product_id.with_context(
                    from_date=from_date,
                    to_date=to_date
                ).qty_available or 0.0)
                if from_date > now:
                    rentable_qty_total += (line.product_id.with_context().qty_in_rent or 0.0)
                rented_qty_total = (line.product_id._get_unavailable_qty(
                    from_date, to_date,
                    ignored_soline_id=line.id,
                ) or 0.0)
                virtual_available_total = max(rentable_qty_total - rented_qty_total, 0)
                line.virtual_available_total_at_date = virtual_available_total

                # --- Asignación de los demás campos computados ---
                # Para este ejemplo, asignamos:
                # - scheduled_date: la fecha de inicio (from_date)
                # - free_qty_today y qty_available_today: se asumen iguales a la cantidad disponible en el almacén
                # - forecast_expected_date: se deja sin valor (False)
                line.scheduled_date = from_date
                line.free_qty_today = virtual_available_wh
                line.qty_available_today = virtual_available_wh
                line.forecast_expected_date = False

                _logger.info("Line %s: Warehouse=%s, Global=%s, Qty_today=%s",
                             line.id, virtual_available_wh, virtual_available_total, line.qty_available_today)


