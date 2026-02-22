# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import _
from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal


class PortalRentalOrders(CustomerPortal):
    """Portal controller for rental orders"""

    def _prepare_home_portal_values(self, counters):
        """Add rental count to portal home"""
        values = super()._prepare_home_portal_values(counters)
        if 'rental_count' in counters:
            values['rental_count'] = request.env['sale.order'].search_count([
                ('partner_id', '=', request.env.user.partner_id.id),
                ('is_rental_order', '=', True),
                ('state', 'in', ['sale', 'done', 'cancel']),
            ])
        return values

    @http.route(['/my/rentals'], type='http', auth='user', website=True)
    def portal_my_rentals(self, **kw):
        """Display list of user's rental orders"""
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id

        orders = request.env['sale.order'].search([
            ('partner_id', '=', partner.id),
            ('is_rental_order', '=', True),
            ('state', 'in', ['sale', 'done', 'cancel']),
        ], order='date_order desc')

        values.update({
            'orders': orders,
            'default_url': '/my/rentals',
        })

        return request.render('rental_portal_change_request.portal_my_rentals_page', values)

    @http.route(['/my/rentals/<int:order_id>'], type='http', auth='user', website=True)
    def portal_rental_order_page(self, order_id, **kw):
        """Display rental order details"""
        order = request.env['sale.order'].browse(order_id)

        # Security check: order must belong to current user
        if not order.exists() or order.partner_id.id != request.env.user.partner_id.id:
            return request.redirect('/my')

        values = self._prepare_portal_layout_values()
        active_change_request = order.x_active_change_request_id or None

        # Build pending changes info for display
        pending_changes = {}
        pending_additions = []
        if active_change_request and active_change_request.state == 'submitted':
            for cr_line in active_change_request.change_request_line_ids:
                if cr_line.operation == 'add':
                    pending_additions.append(cr_line)
                else:
                    pending_changes[cr_line.product_id.id] = {
                        'operation': cr_line.operation,
                        'original_qty': cr_line.original_qty,
                        'new_qty': cr_line.new_qty,
                    }

        # Group order lines by product family (category), sorted alphabetically
        lines_by_categ = defaultdict(list)
        for line in order.order_line:
            categ = line.product_id.categ_id
            categ_name = categ.display_name if categ else _('Uncategorized')
            lines_by_categ[categ_name].append(line)

        # Sort products alphabetically within each family
        for lines in lines_by_categ.values():
            lines.sort(key=lambda l: (l.product_id.display_name or '').lower())

        # Sort families alphabetically
        grouped_lines = sorted(lines_by_categ.items(), key=lambda x: x[0].lower())

        # Full history of change requests for this order (newest first)
        cr_history = request.env['rental.change_request'].sudo().search([
            ('order_id', '=', order.id),
        ], order='create_date desc')

        values.update({
            'order': order,
            'active_change_request': active_change_request,
            'pending_changes': pending_changes,
            'pending_additions': pending_additions,
            'grouped_lines': grouped_lines,
            'cr_history': cr_history,
        })

        return request.render('rental_portal_change_request.portal_rental_order_page', values)

    @http.route(['/my/rentals/<int:order_id>/change-request'], type='http', auth='user', website=True)
    def portal_change_request_editor(self, order_id, **kw):
        """Display change request editor (OWL app)"""
        order = request.env['sale.order'].browse(order_id)

        # Security check
        if not order.exists() or order.partner_id.id != request.env.user.partner_id.id:
            return request.redirect('/my')

        # Check order is eligible
        if order.state != 'sale':
            return request.redirect('/my/rentals/%d' % order_id)

        # Check no pending request
        if order.x_active_change_request_id and order.x_active_change_request_id.state == 'submitted':
            return request.redirect('/my/rentals/%d' % order_id)

        values = self._prepare_portal_layout_values()
        values.update({
            'order': order,
        })

        return request.render('rental_portal_change_request.portal_change_request_editor', values)
