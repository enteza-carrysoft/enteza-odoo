# -*- coding: utf-8 -*-

import json
from odoo import _
from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError, ValidationError


class RentalPortalJsonRpc(http.Controller):
    """JSON-RPC API endpoints for rental portal"""

    def _validate_jsonrpc_request(self, params):
        """Validate JSON-RPC request structure"""
        required = ['jsonrpc', 'method', 'id', 'params']
        for field in required:
            if field not in params:
                return False, _('Missing required field: %s') % field
        return True, None

    def _jsonrpc_response(self, request_id, result=None, error=None):
        """Format JSON-RPC response"""
        response = {
            'jsonrpc': '2.0',
            'id': request_id,
        }
        if result is not None:
            response['result'] = result
        if error is not None:
            response['error'] = {'message': error}
        return request.make_json_response(response)

    @http.route(
        '/rental_portal/jsonrpc/change_request/start',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=True
    )
    def change_request_start(self, order_id, **kwargs):
        """
        Start a new change request for an order.

        JSON-RPC params:
            order_id: int - ID of the sale order

        Returns:
            dict: {
                'success': bool,
                'change_request': int (id),
                'revision_order': int (id),
                'name': str,
                'error': str (if failed)
            }
        """
        try:
            # Verify order belongs to user or company
            order = request.env['sale.order'].sudo().browse(order_id)
            if not order.exists() or order.partner_id.commercial_partner_id.id != request.env.user.partner_id.commercial_partner_id.id:
                return {
                    'success': False,
                    'error': _('You do not have permission to access this order')
                }

            result = request.env['rental.change_request'].sudo().start_from_order_atomic(order_id)
            return result

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    @http.route(
        '/rental_portal/jsonrpc/change_request/patch',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=True
    )
    def change_request_patch(self, change_request_id, patch_operations, token_order, token_revision, **kwargs):
        """
        Apply incremental changes to revision order.

        JSON-RPC params:
            change_request_id: int - ID of change request
            patch_operations: list - List of operations
                [{operation: str, product_id: int, qty: float, line_id: int}]
            token_order: str - Order write date for concurrency check
            token_revision: str - Revision write date for concurrency check

        Returns:
            dict: {
                'success': bool,
                'lines': list,
                'new_revision_token': str,
                'error': str (if failed)
            }
        """
        try:
            # Verify change request belongs to user/company
            cr = request.env['rental.change_request'].sudo().browse(change_request_id)
            if not cr.exists() or cr.order_id.partner_id.commercial_partner_id.id != request.env.user.partner_id.commercial_partner_id.id:
                return {
                    'success': False,
                    'error': _('You do not have permission to access this change request')
                }

            result = request.env['rental.change_request'].sudo().patch_revision_atomic(
                change_request_id,
                patch_operations,
                token_order,
                token_revision
            )
            return result

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    @http.route(
        '/rental_portal/jsonrpc/change_request/submit',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=True
    )
    def change_request_submit(self, change_request_id, note='', **kwargs):
        """
        Submit change request for approval.

        JSON-RPC params:
            change_request_id: int - ID of change request
            note: str - Submission note (optional)

        Returns:
            dict: {
                'success': bool,
                'error': str (if failed)
            }
        """
        try:
            # Verify change request belongs to user/company
            cr = request.env['rental.change_request'].sudo().browse(change_request_id)
            if not cr.exists() or cr.order_id.partner_id.commercial_partner_id.id != request.env.user.partner_id.commercial_partner_id.id:
                return {
                    'success': False,
                    'error': _('You do not have permission to access this change request')
                }

            result = request.env['rental.change_request'].sudo().submit_atomic(
                change_request_id,
                note
            )
            return result

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    @http.route(
        '/rental_portal/jsonrpc/change_request/cancel',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=True
    )
    def change_request_cancel(self, change_request_id, **kwargs):
        """
        Cancel change request.

        JSON-RPC params:
            change_request_id: int - ID of change request

        Returns:
            dict: {
                'success': bool,
                'error': str (if failed)
            }
        """
        try:
            # Verify change request belongs to user/company
            cr = request.env['rental.change_request'].sudo().browse(change_request_id)
            if not cr.exists() or cr.order_id.partner_id.commercial_partner_id.id != request.env.user.partner_id.commercial_partner_id.id:
                return {
                    'success': False,
                    'error': _('You do not have permission to access this change request')
                }

            cr.action_cancel()
            return {'success': True}

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    @http.route(
        '/rental_portal/jsonrpc/change_request/load',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=True
    )
    def change_request_load(self, change_request_id, **kwargs):
        """
        Load change request data for editing.

        JSON-RPC params:
            change_request_id: int - ID of change request (0 for new)

        Returns:
            dict: {
                'success': bool,
                'change_request': dict,
                'order': dict,
                'lines': list,
                'error': str (if failed)
            }
        """
        try:
            if change_request_id:
                # Load existing change request
                cr = request.env['rental.change_request'].sudo().browse(change_request_id)
                if not cr.exists() or cr.order_id.partner_id.commercial_partner_id.id != request.env.user.partner_id.commercial_partner_id.id:
                    return {
                        'success': False,
                        'error': _('You do not have permission to access this change request')
                    }

                return {
                    'success': True,
                    'change_request': cr.get_change_request_data(),
                    'order': {
                        'id': cr.order_id.id,
                        'name': cr.order_id.name,
                        'state': cr.order_id.state,
                        'date_order': cr.order_id.date_order,
                    },
                    'lines': cr.get_revision_order_lines(),
                }
            else:
                # New change request - return order data only
                order_id = kwargs.get('order_id')
                if not order_id:
                    return {
                        'success': False,
                        'error': _('Order ID is required')
                    }

                order = request.env['sale.order'].sudo().browse(order_id)
                if not order.exists() or order.partner_id.commercial_partner_id.id != request.env.user.partner_id.commercial_partner_id.id:
                    return {
                        'success': False,
                        'error': _('You do not have permission to access this order')
                    }

                lines = []
                for line in order.order_line:
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

                return {
                    'success': True,
                    'change_request': None,
                    'order': {
                        'id': order.id,
                        'name': order.name,
                        'state': order.state,
                        'date_order': order.date_order,
                    },
                    'lines': lines,
                }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    @http.route(
        '/rental_portal/jsonrpc/catalog/search',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=True
    )
    def catalog_search(self, search_term='', limit=20, offset=0, **kwargs):
        """
        Search rental products in catalog.

        JSON-RPC params:
            search_term: str - Search query (SKU or name)
            limit: int - Max results (default 20)
            offset: int - Offset for pagination (default 0)

        Returns:
            dict: {
                'success': bool,
                'products': list,
                'total_count': int,
                'error': str (if failed)
            }
        """
        try:
            Product = request.env['product.product']
            domain = [
                ('sale_ok', '=', True),
                '|',
                ('default_code', 'ilike', search_term),
                ('name', 'ilike', search_term),
            ]

            # Get total count
            total_count = Product.search_count(domain)

            # Search with limit and offset
            products = Product.search(domain, limit=limit, offset=offset)

            product_data = []
            for product in products:
                product_data.append({
                    'product_id': product.id,
                    'product_name': product.name,
                    'product_code': product.default_code,
                    'price_unit': product.lst_price,
                    'description_sale': product.description_sale,
                    'image_url': f'/web/image/product.product/{product.id}/image_128' if product.image_128 else None,
                })

            return {
                'success': True,
                'products': product_data,
                'total_count': total_count,
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    @http.route(
        '/rental_portal/jsonrpc/catalog/check_availability',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=True
    )
    def catalog_check_availability(self, product_ids, **kwargs):
        """
        Check rental availability for products.

        JSON-RPC params:
            product_ids: list[int] - Product IDs to check

        Returns:
            dict: {
                'success': bool,
                'availability': {product_id: {available_qty, status}},
                'error': str (if failed)
            }
        """
        try:
            availability = {}
            # For now, return basic availability
            # In production, integrate with rental availability module
            for product_id in product_ids:
                product = request.env['product.product'].browse(product_id)
                virtual_available = product.virtual_available
                availability[str(product_id)] = {
                    'available_qty': virtual_available if virtual_available > 0 else 0,
                    'status': 'available' if virtual_available > 0 else 'unavailable',
                }

            return {
                'success': True,
                'availability': availability,
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
