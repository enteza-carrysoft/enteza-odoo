# -*- coding: utf-8 -*-

import json
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError, AccessError
from odoo.tools import float_compare


class RentalChangeRequestRejectWizard(models.TransientModel):
    _name = 'rental.change.request.reject.wizard'
    _description = 'Reject Change Request Wizard'

    change_request_id = fields.Many2one(
        'rental.change_request',
        string='Change Request',
        required=True,
        readonly=True
    )
    reason = fields.Text(
        string='Rejection Reason',
        required=True
    )

    def action_reject(self):
        """Reject the change request"""
        self.ensure_one()
        self.change_request_id._do_reject(self.reason)
        return {'type': 'ir.actions.act_window_close'}


class RentalChangeRequest(models.Model):
    _name = 'rental.change_request'
    _description = 'Rental Change Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    # Basic fields
    name = fields.Char(
        string='Reference',
        readonly=True,
        copy=False,
        index=True
    )
    order_id = fields.Many2one(
        'sale.order',
        string='Order',
        required=True,
        readonly=True,
        ondelete='cascade',
        index=True,
        tracking=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        related='order_id.partner_id',
        store=True,
        readonly=True,
        index=True,
    )

    # State management
    state = fields.Selection([
        ('draft', 'Draft'),
        ('editing', 'Editing'),  # Kept for backwards compatibility
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
        ('applied', 'Applied'),  # Kept for backwards compatibility
    ], string='State', default='draft', tracking=True, index=True)

    # Change details
    change_request_line_ids = fields.One2many(
        'rental.change_request.line',
        'change_request_id',
        string='Changes',
    )

    # Submission info
    submitted_date = fields.Datetime(string='Submitted Date', readonly=True)
    submitted_by = fields.Many2one('res.users', string='Submitted By', readonly=True)
    submission_note = fields.Text(string='Customer Message')
    internal_note = fields.Text(string='Internal Note', help='Only visible to staff')

    # Approval info
    approved_date = fields.Datetime(string='Approved Date', readonly=True)
    approved_by = fields.Many2one('res.users', string='Approved By', readonly=True)
    rejection_reason = fields.Text(string='Rejection Reason', readonly=True)

    # Computed fields
    line_count = fields.Integer(string='Number of Changes', compute='_compute_line_count', store=True)

    @api.depends('change_request_line_ids')
    def _compute_line_count(self):
        for request in self:
            request.line_count = len(request.change_request_line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name'):
                vals['name'] = self.env['ir.sequence'].next_by_code('rental.change.request') or _('New')
        return super().create(vals_list)

    @api.constrains('order_id', 'state')
    def _check_only_one_active_per_order(self):
        """Ensure only one active change request per order"""
        for request in self:
            if request.state in ['draft', 'editing', 'submitted']:
                existing = self.search([
                    ('order_id', '=', request.order_id.id),
                    ('state', 'in', ['draft', 'editing', 'submitted']),
                    ('id', '!=', request.id)
                ], limit=1)
                if existing:
                    raise ValidationError(_(
                        'Only one active change request is allowed per order. '
                        'Please complete or cancel the existing request first.'
                    ))

    # -------------------------------------------------------------------------
    # MAIN API METHOD - Called from portal to submit changes
    # -------------------------------------------------------------------------

    @api.model
    def submit_changes(self, order_id, requested_lines, note=''):
        """
        Submit a change request with the desired final state of order lines.

        This is the MAIN entry point from the portal. It:
        1. Creates the change request
        2. Calculates the diff between original and requested
        3. Creates the change request lines

        Args:
            order_id: int - Sale order ID
            requested_lines: list - List of desired lines
                [{'product_id': int, 'qty': float}, ...]
            note: str - Customer note

        Returns:
            dict: {'success': bool, 'change_request_id': int, 'error': str}
        """
        try:
            # Get and validate order
            order = self.env['sale.order'].sudo().browse(order_id)
            if not order.exists():
                return {'success': False, 'error': _('Order not found')}

            # Check permission
            user_partner = self.env.user.partner_id.commercial_partner_id
            order_partner = order.partner_id.commercial_partner_id
            if user_partner.id != order_partner.id:
                return {'success': False, 'error': _('Permission denied')}

            # Validate order state
            if order.state != 'sale':
                return {'success': False, 'error': _('Order must be confirmed')}

            if not order.is_rental_order:
                return {'success': False, 'error': _('Only rental orders allowed')}

            # Check for existing active request
            if order.x_active_change_request_id and order.x_active_change_request_id.state in ['draft', 'submitted']:
                return {'success': False, 'error': _('Order already has an active change request')}

            # Build original lines map
            original_lines = {}
            for line in order.order_line:
                original_lines[line.product_id.id] = {
                    'qty': line.product_uom_qty,
                    'price_unit': line.price_unit,
                    'line_id': line.id,
                }

            # Build requested lines map
            requested_map = {}
            for item in requested_lines:
                product_id = item.get('product_id')
                qty = item.get('qty', 0)
                if product_id and qty > 0:
                    requested_map[product_id] = qty

            # Calculate diff
            change_lines = []

            # Check for updates and removals
            for product_id, orig_data in original_lines.items():
                if product_id in requested_map:
                    new_qty = requested_map[product_id]
                    if float_compare(new_qty, orig_data['qty'], precision_digits=2) != 0:
                        # Updated
                        change_lines.append({
                            'product_id': product_id,
                            'operation': 'update',
                            'original_qty': orig_data['qty'],
                            'new_qty': new_qty,
                            'original_price_unit': orig_data['price_unit'],
                            'original_line_id': orig_data['line_id'],
                        })
                else:
                    # Removed
                    change_lines.append({
                        'product_id': product_id,
                        'operation': 'remove',
                        'original_qty': orig_data['qty'],
                        'original_price_unit': orig_data['price_unit'],
                        'original_line_id': orig_data['line_id'],
                    })

            # Check for additions
            for product_id, qty in requested_map.items():
                if product_id not in original_lines:
                    product = self.env['product.product'].sudo().browse(product_id)
                    if product.exists():
                        change_lines.append({
                            'product_id': product_id,
                            'operation': 'add',
                            'new_qty': qty,
                            'new_price_unit': product.lst_price,
                        })

            # Must have at least one change
            if not change_lines:
                return {'success': False, 'error': _('No changes detected')}

            # Create change request
            cr = self.sudo().create({
                'order_id': order.id,
                'state': 'submitted',
                'submission_note': note,
                'submitted_date': fields.Datetime.now(),
                'submitted_by': self.env.user.id,
            })

            # Create change lines
            for cl in change_lines:
                cl['change_request_id'] = cr.id
            self.env['rental.change_request.line'].sudo().create(change_lines)

            # Link to order
            order.sudo().write({'x_active_change_request_id': cr.id})

            # Post message
            cr.message_post(body=_('Change request submitted by customer.'))
            order.message_post(
                body=_('Change request %s has been submitted for review.') % cr.name,
                subtype_xmlid='mail.mt_comment',
            )

            # Create activity for salesperson
            if order.user_id:
                cr.activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=order.user_id.id,
                    summary=_('Review change request %s') % cr.name,
                )

            return {'success': True, 'change_request_id': cr.id, 'name': cr.name}

        except Exception as e:
            return {'success': False, 'error': str(e)}

    # -------------------------------------------------------------------------
    # APPROVAL / REJECTION
    # -------------------------------------------------------------------------

    def action_approve(self):
        """Approve and apply change request"""
        self.ensure_one()
        if self.state != 'submitted':
            raise UserError(_('Only submitted requests can be approved'))

        self._apply_changes()

        self.write({
            'state': 'approved',
            'approved_date': fields.Datetime.now(),
            'approved_by': self.env.user.id,
        })

        self.order_id.write({'x_active_change_request_id': False})

        self.message_post(body=_('Approved by %s') % self.env.user.name)
        self.order_id.message_post(body=_('Change request %s has been approved and applied.') % self.name)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _('Change request approved'),
                'type': 'success',
            }
        }

    def _apply_changes(self):
        """Apply the requested changes to the order"""
        self.ensure_one()
        order = self.order_id

        for line in self.change_request_line_ids:
            if line.operation == 'add':
                # Add new line
                self.env['sale.order.line'].create({
                    'order_id': order.id,
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.new_qty,
                })
            elif line.operation == 'update':
                # Update existing line
                if line.original_line_id:
                    line.original_line_id.write({'product_uom_qty': line.new_qty})
            elif line.operation == 'remove':
                # Remove line
                if line.original_line_id:
                    line.original_line_id.unlink()

    def action_reject(self):
        """Open reject wizard"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reject Change Request'),
            'res_model': 'rental.change.request.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_change_request_id': self.id}
        }

    def _do_reject(self, reason):
        """Reject the change request"""
        self.ensure_one()
        if self.state != 'submitted':
            raise UserError(_('Only submitted requests can be rejected'))

        self.write({
            'state': 'rejected',
            'rejection_reason': reason,
        })

        self.order_id.write({'x_active_change_request_id': False})

        self.message_post(body=_('Rejected: %s') % reason)
        self.order_id.message_post(body=_('Change request %s has been rejected.') % self.name)

    def action_cancel(self):
        """Cancel change request"""
        self.ensure_one()
        if self.state in ['approved']:
            raise UserError(_('Cannot cancel an approved change request.'))

        self.write({'state': 'cancelled'})
        self.order_id.write({'x_active_change_request_id': False})
        self.message_post(body=_('Cancelled by %s') % self.env.user.name)
        return True
