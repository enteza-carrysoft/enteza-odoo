# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # Rental related fields
    x_parent_order_id = fields.Many2one(
        'sale.order',
        string='Parent Order',
        ondelete='set null',
        index=True,
        help='Original order if this is a revision'
    )
    x_revision_ids = fields.One2many(
        'sale.order',
        'x_parent_order_id',
        string='Revisions',
        help='Change request revisions created from this order'
    )
    x_active_change_request_id = fields.Many2one(
        'rental.change_request',
        string='Active Change Request',
        readonly=True,
        index=True,
        help='Currently active change request for this order'
    )
    x_rental_pickup_date = fields.Datetime(
        string='Rental Pickup Date',
        compute='_compute_rental_pickup_date',
        store=True,
        index=True,
        help='Expected pickup/end date for rental orders'
    )
    is_rental_order = fields.Boolean(
        string='Is Rental Order',
        compute='_compute_is_rental_order',
        store=True,
        help='True if this order contains rental products'
    )

    @api.depends('order_line')
    def _compute_rental_pickup_date(self):
        """Compute rental pickup date from rental_end_date"""
        for order in self:
            if order.is_rental_order and order.order_line:
                # Get rental end date from first rental line
                rental_line = next(
                    (line for line in order.order_line if getattr(line, 'is_rental', False)),
                    None
                )
                if rental_line and hasattr(rental_line, 'rental_end_date'):
                    order.x_rental_pickup_date = rental_line.rental_end_date
                else:
                    order.x_rental_pickup_date = False
            else:
                order.x_rental_pickup_date = False

    @api.depends('order_line')
    def _compute_is_rental_order(self):
        """Compute if order contains rental products"""
        for order in self:
            order.is_rental_order = any(
                getattr(line, 'is_rental', False) for line in order.order_line
            )

    @api.constrains('x_parent_order_id')
    def _check_parent_order(self):
        """Prevent circular references in parent order"""
        for order in self:
            if order.x_parent_order_id:
                current = order.x_parent_order_id
                while current:
                    if current.id == order.id:
                        raise ValidationError(_(
                            'Circular reference detected in parent order hierarchy.'
                        ))
                    current = current.x_parent_order_id

    def action_view_change_requests(self):
        """Action to view change requests for this order"""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'rental_portal_change_request.rental_change_request_action'
        )
        action['domain'] = [('order_id', '=', self.id)]
        action['context'] = {'default_order_id': self.id}
        return action

    def has_active_change_request(self):
        """Check if order has an active change request"""
        self.ensure_one()
        return bool(self.x_active_change_request_id and
                   self.x_active_change_request_id.state in ['draft', 'editing', 'submitted'])

    def get_portal_rental_orders(self, partner_id):
        """Get rental orders for portal display"""
        return self.search([
            ('partner_id', '=', partner_id),
            ('is_rental_order', '=', True),
            ('state', 'in', ['sale', 'done', 'cancel']),
        ], order='date_order desc')

    def get_change_request_eligible_orders(self, partner_id):
        """Get orders eligible for change request"""
        return self.search([
            ('partner_id', '=', partner_id),
            ('is_rental_order', '=', True),
            ('state', '=', 'sale'),
            ('x_active_change_request_id', '=', False),
        ], order='date_order desc')
