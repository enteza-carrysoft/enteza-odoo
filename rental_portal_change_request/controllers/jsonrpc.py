# -*- coding: utf-8 -*-
"""
Simplified JSON-RPC API for rental portal change requests.
"""

from odoo import _
from odoo import http
from odoo.http import request


class RentalPortalJsonRpc(http.Controller):
    """JSON-RPC API endpoints for rental portal"""

    def _check_order_access(self, order):
        """Check if current user can access the order"""
        if not order.exists():
            return False
        user_partner = request.env.user.partner_id.commercial_partner_id
        order_partner = order.partner_id.commercial_partner_id
        return user_partner.id == order_partner.id

    @http.route(
        '/rental_portal/jsonrpc/order/load',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=True
    )
    def load_order(self, order_id, **kwargs):
        """
        Load order data for the change request editor.

        Returns the current order lines that the user can edit.

        Args:
            order_id: int - Sale order ID

        Returns:
            dict: {
                'success': bool,
                'order': {id, name, state},
                'lines': [{product_id, product_name, product_code, qty, price_unit}],
                'error': str
            }
        """
        try:
            order = request.env['sale.order'].sudo().browse(order_id)

            if not self._check_order_access(order):
                return {'success': False, 'error': _('Permission denied')}

            if order.state != 'sale':
                return {'success': False, 'error': _('Order must be confirmed')}

            # Check if there's already a submitted request
            if order.x_active_change_request_id and order.x_active_change_request_id.state == 'submitted':
                return {
                    'success': False,
                    'error': _('This order already has a pending change request')
                }

            # Build lines data
            lines = []
            for line in order.order_line:
                lines.append({
                    'product_id': line.product_id.id,
                    'product_name': line.product_id.display_name,
                    'product_code': line.product_id.default_code or '',
                    'qty': line.product_uom_qty,
                    'price_unit': line.price_unit,
                })

            return {
                'success': True,
                'order': {
                    'id': order.id,
                    'name': order.name,
                    'state': order.state,
                },
                'lines': lines,
            }

        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route(
        '/rental_portal/jsonrpc/change_request/submit',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=True
    )
    def submit_change_request(self, order_id, lines, note='', **kwargs):
        """
        Submit a change request with the desired final state.

        Args:
            order_id: int - Sale order ID
            lines: list - Desired final lines
                [{'product_id': int, 'qty': float}, ...]
            note: str - Customer note

        Returns:
            dict: {'success': bool, 'change_request_id': int, 'error': str}
        """
        try:
            result = request.env['rental.change_request'].submit_changes(
                order_id=order_id,
                requested_lines=lines,
                note=note
            )
            return result

        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route(
        '/rental_portal/jsonrpc/catalog/search',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=True
    )
    def catalog_search(self, search_term='', limit=20, offset=0, **kwargs):
        """
        Search products in catalog.

        Args:
            search_term: str - Search query
            limit: int - Max results
            offset: int - Pagination offset

        Returns:
            dict: {'success': bool, 'products': list, 'total_count': int}
        """
        try:
            Product = request.env['product.product'].sudo()

            domain = [
                ('sale_ok', '=', True),
                '|',
                ('default_code', 'ilike', search_term),
                ('name', 'ilike', search_term),
            ]

            total_count = Product.search_count(domain)
            products = Product.search(domain, limit=limit, offset=offset)

            product_data = []
            for p in products:
                product_data.append({
                    'product_id': p.id,
                    'product_name': p.display_name,
                    'product_code': p.default_code or '',
                    'price_unit': p.lst_price,
                })

            return {
                'success': True,
                'products': product_data,
                'total_count': total_count,
            }

        except Exception as e:
            return {'success': False, 'error': str(e)}
