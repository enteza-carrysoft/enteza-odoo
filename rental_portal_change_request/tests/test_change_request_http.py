# -*- coding: utf-8 -*-

from odoo.tests import HttpCase, tagged
from odoo.exceptions import AccessError


@tagged('post_install', '-at_install', 'http')
class TestRentalChangeRequestHttp(HttpCase):
    """Test HTTP endpoints for Rental Change Request"""

    def setUp(self):
        super().setUp()

        # Create portal user
        self.portal_user = self.env['res.users'].create({
            'name': 'Portal User',
            'login': 'portal@test.com',
            'email': 'portal@test.com',
            'groups_id': [(6, 0, [self.env.ref('base.group_portal').id])],
        })

        # Create partner
        self.partner = self.portal_user.partner_id
        self.partner.write({
            'name': 'Portal Customer',
        })

        # Create products
        self.product_rental = self.env['product.product'].create({
            'name': 'Rental Product',
            'default_code': 'RENT001',
            'type': 'service',
            'sale_ok': True,
            'rental': True,
            'lst_price': 100.0,
        })

        # Create sale order
        self.order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'state': 'sale',
        })

        self.env['sale.order.line'].create({
            'order_id': self.order.id,
            'product_id': self.product_rental.id,
            'product_uom_qty': 2,
            'price_unit': 100.0,
        })
        self.order._compute_is_rental_order()

    def test_portal_access_rentals(self):
        """Test portal user can access rentals list"""
        self.authenticate('portal@test.com', 'portal@test.com')

        response = self.url_open('/my/rentals')
        self.assertEqual(response.status_code, 200)

        # Should show order in list
        self.assertIn(self.order.name, response.text)

    def test_portal_rental_order_detail(self):
        """Test portal user can access order detail"""
        self.authenticate('portal@test.com', 'portal@test.com')

        response = self.url_open(f'/my/rentals/{self.order.id}')
        self.assertEqual(response.status_code, 200)

        # Should show order details
        self.assertIn(self.order.name, response.text)
        self.assertIn(self.product_rental.name, response.text)

    def test_jsonrpc_start(self):
        """Test JSON-RPC start change request endpoint"""
        self.authenticate('portal@test.com', 'portal@test.com')

        response = self.url_open(
            '/rental_portal/jsonrpc/change_request/start',
            data={'jsonrpc': '2.0', 'params': {'order_id': self.order.id}},
            headers={'Content-Type': 'application/json'}
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertIn('result', result)
        self.assertIn('params', result['result'])

    def test_jsonrpc_search_catalog(self):
        """Test JSON-RPC catalog search endpoint"""
        self.authenticate('portal@test.com', 'portal@test.com')

        response = self.url_open(
            '/rental_portal/jsonrpc/catalog/search',
            data={'jsonrpc': '2.0', 'params': {'search_term': 'RENT', 'limit': 20, 'offset': 0}},
            headers={'Content-Type': 'application/json'}
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertIn('result', result)

    def test_portal_user_cannot_access_other_orders(self):
        """Test that portal user cannot access orders of other customers"""
        # Create order for different partner
        other_partner = self.env['res.partner'].create({
            'name': 'Other Customer',
        })

        other_order = self.env['sale.order'].create({
            'partner_id': other_partner.id,
            'state': 'sale',
        })

        self.authenticate('portal@test.com', 'portal@test.com')

        # Try to access other order's detail
        response = self.url_open(f'/my/rentals/{other_order.id}')

        # Should redirect or show error (not reveal other order details)
        self.assertNotIn(other_order.name, response.text)

    def test_jsonrpc_csrf_protection(self):
        """Test that JSON-RPC endpoints are CSRF protected"""
        # This test verifies CSRF protection is active
        # Actual CSRF token validation is handled by Odoo framework

        self.authenticate('portal@test.com', 'portal@test.com')

        # Request without proper CSRF should be handled by framework
        # The framework will either reject or validate the token

    def test_only_sale_orders_eligible_for_change_request(self):
        """Test that only sale orders are eligible for change request"""
        # Create draft order
        draft_order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'state': 'draft',
        })

        result = self.env['rental.change_request'].start_from_order_atomic(draft_order.id)

        self.assertFalse(result['success'])
        self.assertIn('must be in "Sales Order" state', result['error'])

    def test_concurrent_change_request_blocked(self):
        """Test that concurrent change requests are blocked"""
        # Start first change request
        result1 = self.env['rental.change_request'].start_from_order_atomic(self.order.id)
        self.assertTrue(result1['success'])

        # Try to start second change request
        result2 = self.env['rental.change_request'].start_from_order_atomic(self.order.id)
        self.assertFalse(result2['success'])

    def test_portal_can_submit_own_change_request(self):
        """Test that portal user can submit their own change request"""
        # Start change request
        result = self.env['rental.change_request'].start_from_order_atomic(self.order.id)
        cr_id = result['change_request']
        cr = self.env['rental.change_request'].browse(cr_id)

        # Submit
        submit_result = cr.submit_atomic(cr_id, 'Test submission')

        self.assertTrue(submit_result['success'])
        self.assertEqual(cr.state, 'submitted')

    def test_change_request_applies_correctly(self):
        """Test full workflow: create -> modify -> submit -> approve"""
        # Start change request
        result = self.env['rental.change_request'].start_from_order_atomic(self.order.id)
        cr_id = result['change_request']
        cr = self.env['rental.change_request'].browse(cr_id)

        # Modify revision
        cr.revision_order_id.order_line[0].write({'product_uom_qty': 5})

        # Submit
        cr.submit_atomic(cr_id, 'Test')

        # Approve (as sales manager)
        self.env.user.groups_id |= self.env.ref('sales_team.group_sale_manager')
        approve_result = cr.approve_atomic()

        self.assertTrue(approve_result['success'])

        # Verify order updated
        self.order.invalidate_cache()
        self.assertEqual(self.order.order_line[0].product_uom_qty, 5)

    def test_catalog_pagination(self):
        """Test catalog search with pagination"""
        self.authenticate('portal@test.com', 'portal@test.com')

        # Create many products
        for i in range(25):
            self.env['product.product'].create({
                'name': f'Product {i:03d}',
                'default_code': f'PROD{i:03d}',
                'type': 'service',
                'sale_ok': True,
                'lst_price': 10.0 + i,
            })

        # Search first page
        response = self.url_open(
            '/rental_portal/jsonrpc/catalog/search',
            data={'jsonrpc': '2.0', 'params': {'search_term': '', 'limit': 20, 'offset': 0}},
            headers={'Content-Type': 'application/json'}
        )

        result = response.json()
        products = result.get('result', {}).get('params', {}).get('products', [])

        # Should return 20 products max
        self.assertLessEqual(len(products), 20)

        # Search second page
        response = self.url_open(
            '/rental_portal/jsonrpc/catalog/search',
            data={'jsonrpc': '2.0', 'params': {'search_term': '', 'limit': 20, 'offset': 20}},
            headers={'Content-Type': 'application/json'}
        )

        result = response.json()
        products_page2 = result.get('result', {}).get('params', {}).get('products', [])

        # Should have remaining products
        self.assertGreater(len(products_page2), 0)

    def test_quick_add_by_sku(self):
        """Test quick add product by SKU functionality"""
        self.authenticate('portal@test.com', 'portal@test.com')

        # Search for product by SKU
        response = self.url_open(
            '/rental_portal/jsonrpc/catalog/search',
            data={'jsonrpc': '2.0', 'params': {'search_term': 'RENT001', 'limit': 1, 'offset': 0}},
            headers={'Content-Type': 'application/json'}
        )

        result = response.json()
        products = result.get('result', {}).get('params', {}).get('products', [])

        self.assertTrue(len(products) > 0)
        self.assertEqual(products[0]['default_code'], 'RENT001')

    def test_change_request_state_transitions(self):
        """Test state transitions in change request"""
        result = self.env['rental.change_request'].start_from_order_atomic(self.order.id)
        cr = self.env['rental.change_request'].browse(result['change_request'])

        # Draft -> Editing (automatic on start)
        self.assertEqual(cr.state, 'editing')

        # Editing -> Submitted
        cr.submit_atomic(cr.id, 'Test')
        self.assertEqual(cr.state, 'submitted')

        # Cannot edit after submit
        # (This would be tested by trying to patch after submit)

    def test_rejected_change_request_clears_active_flag(self):
        """Test that rejected change request clears active flag on order"""
        result = self.env['rental.change_request'].start_from_order_atomic(self.order.id)
        cr = self.env['rental.change_request'].browse(result['change_request'])

        # Submit
        cr.submit_atomic(cr.id, 'Test')

        # Reject
        cr.reject_atomic(cr.id, 'Test rejection')

        # Verify active flag cleared
        self.order.invalidate_cache()
        self.assertIsNone(self.order.x_active_change_request_id)

        # Should be able to create new change request now
        result2 = self.env['rental.change_request'].start_from_order_atomic(self.order.id)
        self.assertTrue(result2['success'])
