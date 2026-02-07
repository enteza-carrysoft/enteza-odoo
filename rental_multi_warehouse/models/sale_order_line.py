# -*- coding: utf-8 -*-
import json
import logging
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)


class RentalWarehouseAssignment(models.Model):
    """
    Registra la asignación concreta de stock de un almacén a una línea
    de pedido de alquiler. Se crea al confirmar el pedido.
    """
    _name = 'rental.warehouse.assignment'
    _description = 'Asignación de almacén en alquiler'
    _order = 'is_primary desc, sequence'

    sale_line_id = fields.Many2one(
        'sale.order.line', string='Línea de pedido',
        required=True, ondelete='cascade', index=True,
    )
    order_id = fields.Many2one(
        related='sale_line_id.order_id', store=True, string='Pedido',
    )
    product_id = fields.Many2one(
        related='sale_line_id.product_id', store=True, string='Producto',
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse', string='Almacén',
        required=True, ondelete='restrict',
    )
    quantity = fields.Float(
        string='Cantidad asignada',
        digits='Product Unit of Measure',
        required=True,
    )
    is_primary = fields.Boolean(string='Almacén preferente', default=False)
    sequence = fields.Integer(string='Orden', default=10)

    picking_id = fields.Many2one(
        'stock.picking', string='Traslado hacia preferente',
        copy=False,
        help='Traslado inter-almacén generado para mover stock '
             'de este almacén al preferente antes de la entrega.',
    )
    return_picking_id = fields.Many2one(
        'stock.picking', string='Traslado de retorno',
        copy=False,
        help='Traslado para devolver el material a este almacén '
             'después de la devolución del cliente.',
    )
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('confirmed', 'Confirmado'),
        ('transferred', 'Trasladado al preferente'),
        ('delivered', 'Entregado al cliente'),
        ('returned', 'Devuelto a origen'),
    ], string='Estado', default='draft', copy=False)

    @api.model
    def _cron_check_pending_transfers(self):
        """
        Cron diario: verifica traslados pendientes para las próximas
        2 semanas y registra alertas en el log.
        """
        today = fields.Date.today()
        limit_date = today + timedelta(days=14)

        pending = self.search([
            ('state', '=', 'confirmed'),
            ('picking_id', '!=', False),
            ('picking_id.state', 'not in', ['done', 'cancel']),
            ('picking_id.scheduled_date', '<=', limit_date),
        ])

        if not pending:
            return

        overdue = pending.filtered(
            lambda a: a.picking_id.scheduled_date.date() <= today
        )
        upcoming = pending - overdue

        if overdue:
            _logger.warning(
                'TRASLADOS VENCIDOS (%d): %s',
                len(overdue),
                ', '.join(overdue.mapped(
                    lambda a: '%s (%s uds %s, %s→%s)' % (
                        a.picking_id.name,
                        a.quantity,
                        a.product_id.display_name,
                        a.warehouse_id.name,
                        a.sale_line_id.order_id.warehouse_id.name,
                    )
                )),
            )

        if upcoming:
            _logger.info(
                'Traslados pendientes próximas 2 semanas (%d): %s',
                len(upcoming),
                ', '.join(upcoming.mapped(
                    lambda a: '%s (%s, %s)' % (
                        a.picking_id.name,
                        a.picking_id.scheduled_date.strftime('%d/%m'),
                        a.product_id.display_name,
                    )
                )),
            )


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # ── Campos de asignación multi-almacén ─────────────────────────────
    rental_assignment_ids = fields.One2many(
        'rental.warehouse.assignment', 'sale_line_id',
        string='Asignaciones por almacén', copy=False,
    )
    rental_picking_ids = fields.Many2many(
        'stock.picking', 'rental_line_picking_rel',
        'sale_line_id', 'picking_id',
        string='Traslados inter-almacén', copy=False,
    )
    rental_needs_transfer = fields.Boolean(
        string='Necesita traslado',
        compute='_compute_rental_multi_wh_availability',
    )

    # ── Campos computados para el widget ───────────────────────────────
    rental_availability_status = fields.Selection([
        ('ok', 'Disponible'),
        ('transfer_needed', 'Necesita traslado'),
        ('deficit', 'Sin stock suficiente'),
    ], string='Estado disponibilidad',
        compute='_compute_rental_multi_wh_availability',
    )
    rental_total_available = fields.Float(
        string='Total disponible',
        digits='Product Unit of Measure',
        compute='_compute_rental_multi_wh_availability',
    )
    rental_availability_json = fields.Text(
        string='Disponibilidad (JSON)',
        compute='_compute_rental_multi_wh_availability',
    )

    # ══════════════════════════════════════════════════════════════════
    #  MOTOR DE DISPONIBILIDAD
    # ══════════════════════════════════════════════════════════════════

    @api.depends(
        'product_id', 'start_date', 'return_date',
        'product_uom_qty', 'order_id.warehouse_id', 'is_rental',
    )
    def _compute_rental_multi_wh_availability(self):
        for line in self:
            if not (line.is_rental and line.product_id
                    and line.start_date and line.return_date
                    and line.order_id.warehouse_id):
                line.rental_availability_status = False
                line.rental_total_available = 0.0
                line.rental_availability_json = '{}'
                line.rental_needs_transfer = False
                continue

            data = line._get_multi_wh_availability()
            line.rental_availability_status = data['status']
            line.rental_total_available = data['total_available']
            line.rental_needs_transfer = data['status'] == 'transfer_needed'
            line.rental_availability_json = json.dumps(
                data, default=str,
            )

    def _get_multi_wh_availability(self):
        """
        Motor principal. Calcula disponibilidad a través de N almacenes
        y asigna stock en cascada por orden de prioridad.

        Returns: dict {
            total_available, qty_needed, deficit, status,
            assignments: [{warehouse_id, warehouse_name, stock_on_hand,
                           committed, available, assigned, is_primary,
                           transfer_date}]
        }
        """
        self.ensure_one()

        product = self.product_id
        start = self.start_date
        end = self.return_date
        qty_needed = self.product_uom_qty
        primary_wh = self.order_id.warehouse_id

        # Lista ordenada: preferente + secundarios por prioridad
        secondary_whs = self.env['rental.warehouse.priority']\
            .get_ordered_warehouses(exclude_warehouse=primary_wh)
        all_whs = primary_wh | secondary_whs

        assignments = []
        remaining = qty_needed

        for wh in all_whs:
            is_primary = (wh.id == primary_wh.id)
            on_hand = self._wh_qty_on_hand(product, wh)
            committed = self._wh_committed_rental_qty(product, wh, start, end)
            returning = self._wh_returning_before(product, wh, start)
            incoming = self._wh_incoming_transfers(product, wh, start)
            available = max(on_hand + returning + incoming - committed, 0.0)

            if float_compare(remaining, 0.0, precision_digits=2) > 0:
                assigned = min(available, remaining)
                remaining -= assigned
            else:
                assigned = 0.0

            assignments.append({
                'warehouse_id': wh.id,
                'warehouse_name': wh.name,
                'stock_on_hand': on_hand,
                'committed': committed,
                'returning': returning,
                'incoming_transfers': incoming,
                'available': available,
                'assigned': assigned,
                'is_primary': is_primary,
                'transfer_date': '',
            })

        # Estado global
        total_available = sum(a['available'] for a in assignments)
        deficit = max(remaining, 0.0)
        needs_transfer = any(
            a['assigned'] > 0 and not a['is_primary'] for a in assignments
        )

        if float_compare(deficit, 0.0, precision_digits=2) > 0:
            status = 'deficit'
        elif needs_transfer:
            status = 'transfer_needed'
        else:
            status = 'ok'

        # Fecha de traslado para asignaciones secundarias
        if needs_transfer:
            transfer_date = self._get_transfer_date(
                fields.Date.to_date(self.start_date)
            )
            for a in assignments:
                if not a['is_primary'] and a['assigned'] > 0:
                    a['transfer_date'] = str(transfer_date)

        return {
            'total_available': total_available,
            'qty_needed': qty_needed,
            'assignments': assignments,
            'deficit': deficit,
            'status': status,
        }

    # ── Consultas de stock por almacén ─────────────────────────────────

    def _wh_qty_on_hand(self, product, warehouse):
        """Stock físico actual en el almacén."""
        return product.with_context(warehouse_id=warehouse.id).qty_available

    def _wh_committed_rental_qty(self, product, warehouse, start, end):
        """
        Unidades comprometidas en alquileres solapados:
        solapa si rental.start < nuestro end AND rental.return > nuestro start

        Incluye:
        1. Pedidos cuyo almacén primario es este almacén (qty completa)
        2. Asignaciones multi-almacén desde este almacén como secundario
        """
        # 1. Comprometidos como almacén primario del pedido
        domain = [
            ('product_id', '=', product.id),
            ('is_rental', '=', True),
            ('order_id.warehouse_id', '=', warehouse.id),
            ('order_id.state', 'in', ['sale', 'done']),
            ('start_date', '<', end),
            ('return_date', '>', start),
        ]
        if self._origin.id:
            domain.append(('id', '!=', self._origin.id))
        lines = self.env['sale.order.line'].search(domain)
        committed_primary = sum(lines.mapped('product_uom_qty'))

        # 2. Comprometidos como almacén secundario (asignaciones inter-almacén)
        assign_domain = [
            ('product_id', '=', product.id),
            ('warehouse_id', '=', warehouse.id),
            ('state', 'not in', ['draft', 'returned']),
            ('sale_line_id.start_date', '<', end),
            ('sale_line_id.return_date', '>', start),
            ('sale_line_id.order_id.warehouse_id', '!=', warehouse.id),
        ]
        if self._origin.id:
            assign_domain.append(('sale_line_id', '!=', self._origin.id))
        assignments = self.env['rental.warehouse.assignment'].search(assign_domain)
        committed_secondary = sum(assignments.mapped('quantity'))

        return committed_primary + committed_secondary

    def _wh_returning_before(self, product, warehouse, start):
        """
        Unidades en alquiler activo (pickup) que se devuelven antes de start.
        Estas estarán disponibles para nuestro alquiler.
        """
        domain = [
            ('product_id', '=', product.id),
            ('is_rental', '=', True),
            ('order_id.warehouse_id', '=', warehouse.id),
            ('order_id.state', 'in', ['sale', 'done']),
            ('return_date', '<=', start),
        ]
        # Solo contar las que están con el cliente (recogidas, no devueltas)
        # En sale_renting: rental_status = 'return' → recogido por el cliente
        domain.append(('rental_status', '=', 'return'))

        lines = self.env['sale.order.line'].search(domain)
        return sum(lines.mapped('product_uom_qty'))

    def _wh_incoming_transfers(self, product, warehouse, before_date):
        """
        Traslados internos entrantes al almacén programados antes de la fecha.
        Solo pendientes (no finalizados ni cancelados).
        Excluye traslados vinculados a asignaciones de alquiler, ya que
        esos están gestionados por el cálculo de committed/returning.
        """
        # Obtener todos los pickings vinculados a asignaciones de alquiler
        rental_pickings = self.env['rental.warehouse.assignment'].search([
            ('picking_id', '!=', False),
        ]).mapped('picking_id')

        domain = [
            ('product_id', '=', product.id),
            ('picking_id.picking_type_id.code', '=', 'internal'),
            ('location_dest_id', 'child_of', warehouse.lot_stock_id.id),
            ('date', '<=', before_date),
            ('state', 'not in', ['done', 'cancel']),
        ]
        # Excluir traslados de alquiler (gestionados por committed)
        if rental_pickings:
            domain.append(('picking_id', 'not in', rental_pickings.ids))
        moves = self.env['stock.move'].search(domain)
        return sum(moves.mapped('product_uom_qty'))

    # ── Utilidades de fecha ────────────────────────────────────────────

    @api.model
    def _get_transfer_date(self, delivery_date):
        """
        Calcula la fecha de traslado: el día configurado de la semana
        ANTERIOR a delivery_date. Si delivery_date cae en ese día,
        va a la semana anterior.

        Ejemplo con martes (weekday=1):
          - delivery=sábado 15/03 → martes 11/03
          - delivery=martes 11/03 → martes 04/03
        """
        transfer_day = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'rental_multi_wh.transfer_day', '1'
            )
        )
        weekday = delivery_date.weekday()
        days_back = (weekday - transfer_day) % 7
        if days_back == 0:
            days_back = 7
        transfer_date = delivery_date - timedelta(days=days_back)

        today = fields.Date.today()
        if transfer_date < today:
            _logger.warning(
                'Fecha de traslado calculada (%s) anterior a hoy. '
                'Se usa hoy como fecha mínima.', transfer_date
            )
            transfer_date = today

        return transfer_date

    @api.model
    def _get_transfer_lead_days(self):
        """Días mínimos de antelación para traslados."""
        return int(
            self.env['ir.config_parameter'].sudo().get_param(
                'rental_multi_wh.transfer_lead_days', '2'
            )
        )

    # ── Endpoint para widget OWL ───────────────────────────────────────

    def get_multi_wh_availability_data(self):
        """Llamado desde frontend vía RPC para el widget."""
        self.ensure_one()
        return self._get_multi_wh_availability()
