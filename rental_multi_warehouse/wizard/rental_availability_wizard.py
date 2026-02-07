# -*- coding: utf-8 -*-
import json
from datetime import timedelta

from odoo import api, fields, models, _


class RentalAvailabilityWizard(models.TransientModel):
    """
    Wizard para consultar la disponibilidad de un producto en todos
    los almacenes para un rango de fechas de alquiler.
    Accesible desde Alquiler > Informes > Consultar disponibilidad.
    """
    _name = 'rental.availability.wizard'
    _description = 'Consulta de disponibilidad de alquiler'

    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        required=True,
        domain="[('rent_ok', '=', True)]",
    )
    start_date = fields.Datetime(
        string='Fecha de entrega',
        required=True,
        default=fields.Datetime.now,
    )
    return_date = fields.Datetime(
        string='Fecha de devolución',
        required=True,
    )
    quantity_needed = fields.Float(
        string='Cantidad necesaria',
        default=1.0,
        required=True,
    )
    result_html = fields.Html(
        string='Resultado',
        readonly=True,
        sanitize=False,
    )

    @api.onchange('start_date')
    def _onchange_start_date(self):
        """Proponer devolución 2 días después por defecto."""
        if self.start_date and not self.return_date:
            self.return_date = self.start_date + timedelta(days=2)

    def action_check_availability(self):
        """Calcula y muestra la disponibilidad multi-almacén."""
        self.ensure_one()

        # Reutilizar el motor de cálculo de sale.order.line
        SOLine = self.env['sale.order.line']
        primary_wh = self.env['stock.warehouse'].search([], limit=1)
        secondary_whs = self.env['rental.warehouse.priority']\
            .get_ordered_warehouses()
        all_whs = primary_wh | secondary_whs

        product = self.product_id
        start = self.start_date
        end = self.return_date
        qty_needed = self.quantity_needed

        rows = []
        remaining = qty_needed
        total_available = 0.0

        for wh in all_whs:
            on_hand = product.with_context(
                warehouse=wh.id
            ).qty_available

            # Comprometidos en alquileres solapados
            committed_lines = SOLine.search([
                ('product_id', '=', product.id),
                ('is_rental', '=', True),
                ('order_id.warehouse_id', '=', wh.id),
                ('order_id.state', 'in', ['sale', 'done']),
                ('start_date', '<', end),
                ('return_date', '>', start),
            ])
            committed = sum(committed_lines.mapped('product_uom_qty'))
            available = max(on_hand - committed, 0.0)
            total_available += available

            assigned = min(available, max(remaining, 0.0))
            remaining -= assigned

            # Color de fila
            if assigned > 0 and wh == primary_wh:
                row_class = 'table-success'
            elif assigned > 0:
                row_class = 'table-info'
            elif available > 0:
                row_class = ''
            else:
                row_class = 'table-light text-muted'

            rows.append({
                'wh_name': wh.name,
                'on_hand': on_hand,
                'committed': committed,
                'available': available,
                'assigned': assigned,
                'row_class': row_class,
                'is_primary': wh == primary_wh,
            })

        # Construir HTML del resultado
        deficit = max(remaining, 0.0)
        if deficit > 0:
            status_html = (
                '<div class="alert alert-danger">'
                '<i class="fa fa-times-circle"/> '
                '<strong>Stock insuficiente.</strong> '
                'Necesitas %s, disponibles %s (faltan %s).'
                '</div>'
            ) % (qty_needed, total_available, deficit)
        elif total_available > qty_needed and any(
            r['assigned'] > 0 and not r['is_primary'] for r in rows
        ):
            transfer_date = SOLine._get_transfer_date(
                fields.Date.to_date(self.start_date)
            )
            status_html = (
                '<div class="alert alert-info">'
                '<i class="fa fa-truck"/> '
                '<strong>Disponible con traslado inter-almacén.</strong> '
                'Traslado programado para el %s.'
                '</div>'
            ) % transfer_date.strftime('%A %d/%m/%Y')
        else:
            status_html = (
                '<div class="alert alert-success">'
                '<i class="fa fa-check-circle"/> '
                '<strong>Disponible.</strong> '
                'Stock suficiente en el almacén principal.'
                '</div>'
            )

        table_rows = ''
        for r in rows:
            primary_badge = (
                ' <span class="badge text-bg-warning">Pref.</span>'
                if r['is_primary'] else ''
            )
            table_rows += (
                '<tr class="%s">'
                '<td>%s%s</td>'
                '<td class="text-end">%g</td>'
                '<td class="text-end text-danger">%g</td>'
                '<td class="text-end fw-bold">%g</td>'
                '<td class="text-end fw-bold">%g</td>'
                '</tr>'
            ) % (
                r['row_class'],
                r['wh_name'], primary_badge,
                r['on_hand'], r['committed'],
                r['available'], r['assigned'],
            )

        self.result_html = (
            '%s'
            '<table class="table table-sm table-bordered">'
            '<thead class="table-dark">'
            '<tr>'
            '<th>Almacén</th>'
            '<th class="text-end">Stock</th>'
            '<th class="text-end">Comprometido</th>'
            '<th class="text-end">Disponible</th>'
            '<th class="text-end">Asignado</th>'
            '</tr>'
            '</thead>'
            '<tbody>%s</tbody>'
            '<tfoot class="table-secondary fw-bold">'
            '<tr>'
            '<td>TOTAL</td>'
            '<td class="text-end">%g</td>'
            '<td class="text-end">%g</td>'
            '<td class="text-end">%g</td>'
            '<td class="text-end">%g</td>'
            '</tr>'
            '</tfoot>'
            '</table>'
        ) % (
            status_html,
            table_rows,
            sum(r['on_hand'] for r in rows),
            sum(r['committed'] for r in rows),
            total_available,
            qty_needed - max(remaining, 0.0),
        )

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
