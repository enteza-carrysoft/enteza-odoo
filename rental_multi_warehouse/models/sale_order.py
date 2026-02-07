# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    rental_transfer_count = fields.Integer(
        string='Traslados inter-almacén',
        compute='_compute_rental_transfer_count',
    )

    def _compute_rental_transfer_count(self):
        for order in self:
            order.rental_transfer_count = len(
                order.order_line.mapped('rental_picking_ids')
            )

    # ══════════════════════════════════════════════════════════════════
    #  CONFIRMACIÓN CON ASIGNACIÓN MULTI-ALMACÉN
    # ══════════════════════════════════════════════════════════════════

    def action_confirm(self):
        """
        Override de confirmación. Antes de llamar al super():
        1. Para cada línea de alquiler, calcula disponibilidad multi-almacén
        2. Si el almacén preferente no cubre, asigna desde secundarios
        3. Crea traslados inter-almacén programados
        4. Si aún hay déficit, lanza error con detalle
        """
        for order in self:
            rental_lines = order.order_line.filtered(
                lambda l: l.is_rental and l.product_id and l.start_date
            )
            if not rental_lines:
                continue

            primary_wh = order.warehouse_id
            deficit_details = []

            for line in rental_lines:
                result = line._get_multi_wh_availability()

                if result['status'] == 'deficit':
                    deficit_details.append(
                        _('• %s: necesitas %s, disponibles %s '
                          '(faltan %s unidades)') % (
                            line.product_id.display_name,
                            line.product_uom_qty,
                            result['total_available'],
                            result['deficit'],
                        )
                    )
                    continue

                # Crear asignaciones y traslados
                order._create_rental_assignments(line, result, primary_wh)

            if deficit_details:
                raise UserError(
                    _('Stock insuficiente para el periodo %s - %s '
                      'incluso sumando todos los almacenes:\n\n%s') % (
                        order.order_line[0].start_date.strftime('%d/%m/%Y'),
                        order.order_line[0].return_date.strftime('%d/%m/%Y'),
                        '\n'.join(deficit_details),
                    )
                )

        return super().action_confirm()

    def _create_rental_assignments(self, line, availability_data, primary_wh):
        """
        Crea los registros de asignación y los traslados inter-almacén.

        :param line: sale.order.line record
        :param availability_data: dict de _get_multi_wh_availability()
        :param primary_wh: stock.warehouse preferente del pedido
        """
        Assignment = self.env['rental.warehouse.assignment']
        pickings = self.env['stock.picking']

        for idx, a in enumerate(availability_data['assignments']):
            if float_compare(a['assigned'], 0.0, precision_digits=2) <= 0:
                continue

            wh = self.env['stock.warehouse'].browse(a['warehouse_id'])
            is_primary = a['is_primary']

            # Crear registro de asignación
            assignment_vals = {
                'sale_line_id': line.id,
                'warehouse_id': wh.id,
                'quantity': a['assigned'],
                'is_primary': is_primary,
                'sequence': 0 if is_primary else (idx + 1) * 10,
                'state': 'confirmed',
            }

            # Si es almacén secundario, crear traslado inter-almacén
            picking = False
            if not is_primary:
                picking = self._create_inter_wh_transfer(
                    line, wh, primary_wh, a['assigned'],
                )
                assignment_vals['picking_id'] = picking.id
                pickings |= picking

            Assignment.create(assignment_vals)

        # Vincular traslados a la línea
        if pickings:
            line.rental_picking_ids = [(4, p.id) for p in pickings]

        _logger.info(
            'Pedido %s, línea %s (%s): asignación multi-almacén completada. '
            '%d traslados creados.',
            line.order_id.name, line.id, line.product_id.display_name,
            len(pickings),
        )

    def _create_inter_wh_transfer(self, line, source_wh, dest_wh, qty):
        """
        Crea un traslado interno desde source_wh hacia dest_wh.
        Programado para el día configurado anterior a la fecha de entrega.

        :param line: sale.order.line
        :param source_wh: stock.warehouse origen
        :param dest_wh: stock.warehouse destino (preferente)
        :param qty: float cantidad a trasladar
        :return: stock.picking record
        """
        transfer_date = line._get_transfer_date(
            fields.Date.to_date(line.start_date)
        )

        # Buscar tipo de operación: traslado interno del almacén origen
        picking_type = self._get_internal_picking_type(source_wh, dest_wh)

        picking_vals = {
            'picking_type_id': picking_type.id,
            'location_id': source_wh.lot_stock_id.id,
            'location_dest_id': dest_wh.lot_stock_id.id,
            'scheduled_date': transfer_date,
            'origin': _('Alquiler: %s [%s]') % (
                line.order_id.name, line.product_id.display_name
            ),
            'move_ids': [(0, 0, {
                'product_id': line.product_id.id,
                'product_uom_qty': qty,
                'location_id': source_wh.lot_stock_id.id,
                'location_dest_id': dest_wh.lot_stock_id.id,
                'date': transfer_date,
            })],
        }

        picking = self.env['stock.picking'].create(picking_vals)
        picking.action_confirm()

        _logger.info(
            'Traslado %s creado: %s uds de %s, %s → %s, '
            'programado para %s',
            picking.name, qty, line.product_id.display_name,
            source_wh.name, dest_wh.name, transfer_date,
        )

        return picking

    def _get_internal_picking_type(self, source_wh, dest_wh):
        """
        Busca o crea el tipo de operación de traslado interno.
        Primero busca en el almacén origen, luego un tipo genérico.
        """
        # Buscar tipo de traslado interno del almacén origen
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id', '=', source_wh.id),
        ], limit=1)

        if not picking_type:
            # Buscar cualquier tipo interno de la misma compañía
            picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'internal'),
                ('warehouse_id.company_id', '=', source_wh.company_id.id),
            ], limit=1)

        if not picking_type:
            raise UserError(
                _('No se encontró un tipo de operación de traslado interno '
                  'para el almacén "%s". Configure uno en '
                  'Inventario → Configuración → Tipos de operación.') %
                source_wh.name
            )

        return picking_type

    # ══════════════════════════════════════════════════════════════════
    #  GESTIÓN DE DEVOLUCIONES MULTI-ALMACÉN
    # ══════════════════════════════════════════════════════════════════

    def _create_return_transfers(self):
        """
        Al completarse la devolución del cliente, crea traslados de
        retorno para devolver el material a sus almacenes de origen.
        Se llama desde el workflow de devolución de alquiler.
        """
        for order in self:
            for line in order.order_line.filtered('is_rental'):
                secondary_assignments = line.rental_assignment_ids.filtered(
                    lambda a: not a.is_primary
                              and a.quantity > 0
                              and a.state == 'delivered'
                )
                for assignment in secondary_assignments:
                    return_picking = self._create_inter_wh_transfer(
                        line,
                        source_wh=order.warehouse_id,       # desde preferente
                        dest_wh=assignment.warehouse_id,     # hacia origen
                        qty=assignment.quantity,
                    )
                    assignment.return_picking_id = return_picking.id
                    assignment.state = 'returned'

                    _logger.info(
                        'Retorno creado: %s uds de %s, %s → %s',
                        assignment.quantity,
                        line.product_id.display_name,
                        order.warehouse_id.name,
                        assignment.warehouse_id.name,
                    )

    # ══════════════════════════════════════════════════════════════════
    #  CANCELACIÓN
    # ══════════════════════════════════════════════════════════════════

    def action_cancel(self):
        """Al cancelar, cancelar también los traslados inter-almacén."""
        for order in self:
            for line in order.order_line.filtered('is_rental'):
                # Cancelar traslados pendientes
                for picking in line.rental_picking_ids.filtered(
                    lambda p: p.state not in ('done', 'cancel')
                ):
                    picking.action_cancel()
                    _logger.info(
                        'Traslado %s cancelado por cancelación de %s',
                        picking.name, order.name,
                    )
                # Limpiar asignaciones
                line.rental_assignment_ids.write({'state': 'draft'})

        return super().action_cancel()

    # ══════════════════════════════════════════════════════════════════
    #  ACCIONES DE INTERFAZ
    # ══════════════════════════════════════════════════════════════════

    def action_view_rental_transfers(self):
        """Botón para ver los traslados inter-almacén del pedido."""
        self.ensure_one()
        pickings = self.order_line.mapped('rental_picking_ids')
        # Incluir también los traslados de retorno
        return_pickings = self.order_line.mapped(
            'rental_assignment_ids.return_picking_id'
        )
        all_pickings = pickings | return_pickings

        action = self.env['ir.actions.actions']._for_xml_id(
            'stock.action_picking_tree_all'
        )
        if len(all_pickings) == 1:
            action['views'] = [
                (self.env.ref('stock.view_picking_form').id, 'form')
            ]
            action['res_id'] = all_pickings.id
        else:
            action['domain'] = [('id', 'in', all_pickings.ids)]
        action['context'] = dict(
            self.env.context,
            create=False,
        )
        return action
