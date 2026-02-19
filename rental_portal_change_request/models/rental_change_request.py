# -*- coding: utf-8 -*-

import json
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError, AccessError
from odoo.tools import float_compare
from odoo.addons.base.models.res_partner import Partner


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
        result = self.env['rental.change_request'].reject_atomic(
            self.change_request_id.id,
            self.reason
        )
        if not result.get('success'):
            raise UserError(result.get('error', _('Rejection failed')))
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
    revision_order_id = fields.Many2one(
        'sale.order',
        string='Revision Order',
        readonly=True,
        ondelete='set null',
        index=True,
        help='Draft order containing the proposed changes'
    )

    # Concurrency control tokens
    expected_order_write_date = fields.Datetime(
        string='Expected Order Write Date',
        readonly=True,
        help='Token for optimistic locking of original order'
    )
    expected_revision_write_date = fields.Datetime(
        string='Expected Revision Write Date',
        readonly=True,
        help='Token for optimistic locking of revision order'
    )

    # State management
    state = fields.Selection([
        ('draft', 'Draft'),
        ('editing', 'Editing'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
        ('applied', 'Applied'),
    ], string='State', default='draft', tracking=True, index=True)

    # Change details
    change_request_line_ids = fields.One2many(
        'rental.change_request.line',
        'change_request_id',
        string='Changes',
        readonly=True
    )
    diff_json = fields.Text(
        string='Change Diff',
        readonly=True,
        help='JSON representation of changes made'
    )

    # Submission info
    submitted_date = fields.Datetime(
        string='Submitted Date',
        readonly=True
    )
    submitted_by = fields.Many2one(
        'res.users',
        string='Submitted By',
        readonly=True
    )
    submission_note = fields.Text(
        string='Submission Note',
        readonly=True
    )

    # Approval info
    approved_date = fields.Datetime(
        string='Approved Date',
        readonly=True
    )
    approved_by = fields.Many2one(
        'res.users',
        string='Approved By',
        readonly=True
    )
    rejection_reason = fields.Text(
        string='Rejection Reason',
        readonly=True
    )

    # Computed fields
    line_count = fields.Integer(
        string='Number of Changes',
        compute='_compute_line_count',
        store=True
    )
    can_edit = fields.Boolean(
        string='Can Edit',
        compute='_compute_can_edit'
    )
    can_submit = fields.Boolean(
        string='Can Submit',
        compute='_compute_can_submit'
    )
    can_approve = fields.Boolean(
        string='Can Approve',
        compute='_compute_can_approve'
    )

    @api.depends('change_request_line_ids')
    def _compute_line_count(self):
        for request in self:
            request.line_count = len(request.change_request_line_ids)

    def _compute_can_edit(self):
        for request in self:
            request.can_edit = (
                request.state in ['draft', 'editing'] and
                request.order_id.partner_id.id == self.env.user.partner_id.id
            )

    def _compute_can_submit(self):
        for request in self:
            request.can_submit = (
                request.state in ['draft', 'editing'] and
                request.order_id.partner_id.id == self.env.user.partner_id.id and
                request.line_count > 0
            )

    def _compute_can_approve(self):
        for request in self:
            is_commercial = self.user_has_groups('sales_team.group_sale_manager')
            request.can_approve = (
                request.state == 'submitted' and is_commercial
            )

    @api.model
    def _get_sequence(self):
        """Get sequence code for change request"""
        return 'rental.change.request'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    self._get_sequence()
                ) or _('New')
        return super().create(vals_list)

    @api.constrains('order_id', 'state')
    def _check_only_one_active_per_order(self):
        """Ensure only one active change request per order"""
        for request in self:
            if request.state in ['draft', 'editing', 'submitted']:
                active_requests = self.search([
                    ('order_id', '=', request.order_id.id),
                    ('state', 'in', ['draft', 'editing', 'submitted']),
                    ('id', '!=', request.id)
                ])
                if active_requests:
                    raise ValidationError(_(
                        'Only one active change request is allowed per order. '
                        'Please complete or cancel the existing request first.'
                    ))

    @api.constrains('order_id')
    def _check_order_state(self):
        """Ensure change request can only be created for sale orders"""
        for request in self:
            if request.order_id.state != 'sale':
                raise ValidationError(_(
                    'Change requests can only be created for confirmed sales orders.'
                ))

    # -------------------------------------------------------------------------
    # ATOMIC METHODS - These must be called via JSON-RPC or internally
    # -------------------------------------------------------------------------

    @api.model
    def start_from_order_atomic(self, order_id):
        """
        Atomically create a change request and revision order.

        Returns:
            dict: {
                'success': bool,
                'change_request': int (id),
                'revision_order': int (id),
                'error': str (if failed)
            }
        """
        try:
            order = self.env['sale.order'].browse(order_id)
            order.sudo().check_access_rules('read')

            # Verify order is eligible
            if order.state != 'sale':
                return {
                    'success': False,
                    'error': _('Order must be in "Sales Order" state')
                }

            if not order.is_rental_order:
                return {
                    'success': False,
                    'error': _('Only rental orders can have change requests')
                }

            if order.x_active_change_request_id:
                return {
                    'success': False,
                    'error': _('Order already has an active change request')
                }

            # Store write date for concurrency control
            order_write_date = order.write_date

            # Create change request
            change_request = self.create({
                'name': self.env['ir.sequence'].next_by_code('rental.change.request'),
                'order_id': order.id,
                'state': 'editing',
                'expected_order_write_date': order_write_date,
            })

            # Create revision order (draft copy of original)
            revision_order = order.copy({
                'x_parent_order_id': order.id,
                'state': 'draft',
                'date_order': fields.Datetime.now(),
            })

            # Update change request with revision
            change_request.write({
                'revision_order_id': revision_order.id,
                'expected_revision_write_date': revision_order.write_date,
            })

            # Update original order to link to active change request
            order.write({'x_active_change_request_id': change_request.id})

            # Post message
            change_request.message_post(
                body=_(
                    'Change request created from order %s. Revision order %s created.'
                ) % (order.name, revision_order.name)
            )

            return {
                'success': True,
                'change_request': change_request.id,
                'revision_order': revision_order.id,
                'name': change_request.name,
                'order_write_date': order_write_date,
                'revision_write_date': revision_order.write_date,
            }

        except AccessError:
            return {
                'success': False,
                'error': _('You do not have permission to access this order')
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    @api.model
    def patch_revision_atomic(self, change_request_id, patch_operations, token_order, token_revision):
        """
        Atomically apply incremental changes to revision order.

        Args:
            change_request_id: int - Change request ID
            patch_operations: list - List of operations to apply
                [{'operation': 'add|update|remove', 'product_id': int, 'qty': float, 'line_id': int}]
            token_order: str - Order write date for concurrency check
            token_revision: str - Revision write date for concurrency check

        Returns:
            dict: {
                'success': bool,
                'change_request_lines': list,
                'error': str (if failed)
            }
        """
        try:
            request = self.browse(change_request_id)
            request.sudo().check_access_rules('write')

            # Validate state
            if request.state not in ['draft', 'editing']:
                return {
                    'success': False,
                    'error': _('Change request is not in editable state')
                }

            # Verify concurrency tokens
            if request.expected_order_write_date != token_order:
                return {
                    'success': False,
                    'error': _('Order has been modified by another user. Please refresh.')
                }

            if request.expected_revision_write_date != token_revision:
                return {
                    'success': False,
                    'error': _('Revision has been modified by another user. Please refresh.')
                }

            # Get revision order
            revision = request.revision_order_id
            if not revision:
                return {
                    'success': False,
                    'error': _('Revision order not found')
                }

            # Apply operations
            created_lines = []
            for op in patch_operations:
                operation = op.get('operation')
                product_id = op.get('product_id')
                qty = op.get('qty', 1.0)
                line_id = op.get('line_id')

                if operation == 'add':
                    # Add new line to revision
                    product = self.env['product.product'].browse(product_id)
                    line = revision._create_product_line(
                        product,
                        qty=qty
                    )
                    created_lines.append({
                        'id': line.id,
                        'product_id': product_id,
                        'operation': 'add',
                        'new_qty': qty,
                    })

                elif operation == 'update':
                    # Update existing line
                    line = self.env['sale.order.line'].browse(line_id)
                    if line.order_id.id != revision.id:
                        continue
                    line.write({
                        'product_uom_qty': qty,
                    })
                    created_lines.append({
                        'id': line.id,
                        'product_id': product_id,
                        'operation': 'update',
                        'new_qty': qty,
                    })

                elif operation == 'remove':
                    # Remove line
                    line = self.env['sale.order.line'].browse(line_id)
                    if line.order_id.id == revision.id:
                        line.unlink()
                    created_lines.append({
                        'id': line_id,
                        'product_id': product_id,
                        'operation': 'remove',
                    })

            # Update concurrency token
            request.write({
                'expected_revision_write_date': revision.write_date,
            })

            return {
                'success': True,
                'lines': created_lines,
                'new_revision_token': revision.write_date,
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def action_submit(self):
        """Submit change request for approval (called from view)"""
        self.ensure_one()
        result = self.submit_atomic(self.submission_note or '')
        if not result.get('success'):
            raise UserError(result.get('error', _('Submission failed')))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _('Change request submitted for approval'),
                'type': 'success',
            }
        }

    @api.model
    def submit_atomic(self, change_request_id, note):
        """
        Atomically submit change request for approval.

        Args:
            change_request_id: int - Change request ID
            note: str - Submission note

        Returns:
            dict: {'success': bool, 'error': str}
        """
        try:
            request = self.browse(change_request_id)
            request.sudo().check_access_rules('write')

            if request.state not in ['draft', 'editing']:
                return {
                    'success': False,
                    'error': _('Change request is not in submittable state')
                }

            # Calculate diff
            diff = self._calculate_diff(request)

            # Create change request lines
            self._create_change_lines_from_diff(request, diff)

            # Update state
            request.write({
                'state': 'submitted',
                'submitted_date': fields.Datetime.now(),
                'submitted_by': self.env.user.id,
                'submission_note': note,
                'diff_json': json.dumps(diff, default=str),
            })

            # Post message to order
            request.order_id.message_post(
                body=_(
                    'Change request %s has been submitted for review.'
                ) % request.name,
                subtype_xmlid='mail.mt_comment',
            )

            # Create activity for sales manager
            request.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=request.order_id.user_id.id or self.env.ref('base.user_admin').id,
                summary=_('Review change request %s') % request.name,
                note=_('A customer has submitted a change request for review.'),
            )

            return {'success': True}

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    @api.model
    def _calculate_diff(self, request):
        """Calculate differences between original and revision order"""
        original_lines = {line.product_id.id: line for line in request.order_id.order_line}
        revision_lines = {line.product_id.id: line for line in request.revision_order_id.order_line}

        diff = {
            'added': [],
            'removed': [],
            'updated': [],
        }

        # Check for added and updated products
        for product_id, rev_line in revision_lines.items():
            if product_id not in original_lines:
                diff['added'].append({
                    'product_id': product_id,
                    'qty': rev_line.product_uom_qty,
                    'price_unit': rev_line.price_unit,
                })
            else:
                orig_line = original_lines[product_id]
                if (float_compare(
                    rev_line.product_uom_qty,
                    orig_line.product_uom_qty,
                    precision_rounding=rev_line.product_uom.rounding
                ) != 0 or
                    float_compare(
                    rev_line.price_unit,
                    orig_line.price_unit,
                    precision_rounding=0.01
                ) != 0):
                    diff['updated'].append({
                        'product_id': product_id,
                        'original_qty': orig_line.product_uom_qty,
                        'new_qty': rev_line.product_uom_qty,
                        'original_price': orig_line.price_unit,
                        'new_price': rev_line.price_unit,
                    })

        # Check for removed products
        for product_id, orig_line in original_lines.items():
            if product_id not in revision_lines:
                diff['removed'].append({
                    'product_id': product_id,
                    'qty': orig_line.product_uom_qty,
                    'price_unit': orig_line.price_unit,
                })

        return diff

    @api.model
    def _create_change_lines_from_diff(self, request, diff):
        """Create rental.change_request.line records from diff"""
        self.env['rental.change_request.line'].search([
            ('change_request_id', '=', request.id)
        ]).unlink()

        lines_vals = []

        # Added products
        for item in diff.get('added', []):
            lines_vals.append({
                'change_request_id': request.id,
                'product_id': item['product_id'],
                'operation': 'add',
                'new_qty': item['qty'],
                'new_price_unit': item['price_unit'],
            })

        # Removed products
        for item in diff.get('removed', []):
            orig_line = self.env['sale.order.line'].search([
                ('order_id', '=', request.order_id.id),
                ('product_id', '=', item['product_id']),
            ], limit=1)
            lines_vals.append({
                'change_request_id': request.id,
                'product_id': item['product_id'],
                'operation': 'remove',
                'original_line_id': orig_line.id if orig_line else False,
                'original_qty': item['qty'],
                'original_price_unit': item['price_unit'],
            })

        # Updated products
        for item in diff.get('updated', []):
            orig_line = self.env['sale.order.line'].search([
                ('order_id', '=', request.order_id.id),
                ('product_id', '=', item['product_id']),
            ], limit=1)
            lines_vals.append({
                'change_request_id': request.id,
                'product_id': item['product_id'],
                'operation': 'update',
                'original_line_id': orig_line.id if orig_line else False,
                'original_qty': item['original_qty'],
                'new_qty': item['new_qty'],
                'original_price_unit': item['original_price'],
                'new_price_unit': item['new_price'],
            })

        if lines_vals:
            self.env['rental.change_request.line'].create(lines_vals)

    def action_approve(self):
        """Approve change request (called from view)"""
        self.ensure_one()
        result = self.approve_atomic()
        if not result.get('success'):
            raise UserError(result.get('error', _('Approval failed')))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _('Change request approved and applied'),
                'type': 'success',
            }
        }

    def approve_atomic(self):
        """
        Atomically approve and apply change request.

        Returns:
            dict: {'success': bool, 'error': str}
        """
        self.ensure_one()
        try:
            self.sudo().check_access_rules('write')

            if self.state != 'submitted':
                return {
                    'success': False,
                    'error': _('Only submitted change requests can be approved')
                }

            # Apply revision
            result = self.apply_revision_atomic()
            if not result.get('success'):
                return result

            # Update state
            self.write({
                'state': 'approved',
                'approved_date': fields.Datetime.now(),
                'approved_by': self.env.user.id,
            })

            # Clear active change request from original order
            self.order_id.write({'x_active_change_request_id': False})

            # Post message
            self.message_post(
                body=_('Change request approved by %s') % self.env.user.name
            )
            self.order_id.message_post(
                body=_('Approved change request %s has been applied') % self.name
            )

            return {'success': True}

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

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

    @api.model
    def reject_atomic(self, change_request_id, reason):
        """
        Atomically reject change request.

        Returns:
            dict: {'success': bool, 'error': str}
        """
        try:
            request = self.browse(change_request_id)
            request.sudo().check_access_rules('write')

            if request.state != 'submitted':
                return {
                    'success': False,
                    'error': _('Only submitted change requests can be rejected')
                }

            request.write({
                'state': 'rejected',
                'rejection_reason': reason,
            })

            # Clear active change request from original order
            request.order_id.write({'x_active_change_request_id': False})

            # Post message
            request.message_post(
                body=_('Change request rejected: %s') % reason
            )
            request.order_id.message_post(
                body=_('Change request %s has been rejected') % request.name
            )

            return {'success': True}

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    @api.model
    def apply_revision_atomic(self):
        """
        Atomically apply revision order changes to original order.

        Uses row-level locking to prevent concurrent modifications.

        Returns:
            dict: {'success': bool, 'error': str}
        """
        self.ensure_one()
        try:
            # Lock original order row
            self.env.cr.execute(
                "SELECT id FROM sale_order WHERE id = %s FOR UPDATE NOWAIT",
                (self.order_id.id,)
            )

            # Cancel existing pickings
            pickings = self.order_id.picking_ids.filtered(
                lambda p: p.state not in ['done', 'cancel']
            )
            pickings.action_cancel()

            # Store original lines
            original_lines = self.order_id.order_line

            # Remove all original lines
            original_lines.unlink()

            # Copy lines from revision
            for rev_line in self.revision_order_id.order_line:
                rev_line.copy({
                    'order_id': self.order_id.id,
                    'state': 'sale',
                })

            # Recalculate prices and rental dates
            self.order_id.recompute_records(['order_line'])

            # Create new pickings
            self.order_id._action_confirm()

            # Update state
            self.write({'state': 'applied'})

            return {'success': True}

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def action_cancel(self):
        """Cancel change request"""
        for request in self:
            if request.state in ['approved', 'applied']:
                raise UserError(_(
                    'Cannot cancel an approved or applied change request.'
                ))

            request.write({'state': 'cancelled'})
            request.order_id.write({'x_active_change_request_id': False})

            request.message_post(
                body=_('Change request cancelled by %s') % self.env.user.name
            )

        return True

    def action_draft(self):
        """Reset to draft state"""
        self.write({'state': 'draft'})
        return True

    def action_edit(self):
        """Enable editing mode"""
        for request in self:
            if request.state == 'draft':
                request.write({'state': 'editing'})
        return True

    def get_change_request_data(self):
        """Get change request data for portal display"""
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name,
            'order_id': self.order_id.id,
            'order_name': self.order_id.name,
            'revision_order_id': self.revision_order_id.id if self.revision_order_id else None,
            'state': self.state,
            'can_edit': self.can_edit,
            'can_submit': self.can_submit,
            'can_approve': self.can_approve,
            'line_count': self.line_count,
            'diff_json': self.diff_json,
            'expected_order_write_date': self.expected_order_write_date,
            'expected_revision_write_date': self.expected_revision_write_date,
        }

    def get_revision_order_lines(self):
        """Get revision order lines for portal display"""
        self.ensure_one()
        if not self.revision_order_id:
            return []

        lines = []
        for line in self.revision_order_id.order_line:
            lines.append({
                'id': line.id,
                'product_id': line.product_id.id,
                'product_name': line.product_id.name,
                'product_code': line.product_id.default_code,
                'qty': line.product_uom_qty,
                'price_unit': line.price_unit,
                'price_subtotal': line.price_subtotal,
                'is_rental': line.is_rental if hasattr(line, 'is_rental') else False,
            })
        return lines
