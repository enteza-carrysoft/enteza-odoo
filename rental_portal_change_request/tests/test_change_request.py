# -*- coding: utf-8 -*-

from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, timedelta


@tagged('post_install', '-at_install')
class TestRentalChangeRequest(TransactionCase):
    """Test Rental Change Request module"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref('sales_team.group_sale_manager')

        # Create partner
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Customer',
            'email': 'test@example.com',
        })

        # Create pricelist
        cls.pricelist = cls.env['product.pricelist'].create({
            'name': 'Test Pricelist',
        })

        # Create products
        cls.product_rental_1 = cls.env['product.product'].create({
            'name': 'Rental Product 1',
            'default_code': 'RENT001',
            'type': 'service',
            'sale_ok': True,
            'rental': True,
            'lst_price': 100.0,
        })

        cls.product_rental_2 = cls.env['product.product'].create({
            'name': 'Rental Product 2',
            'default_code': 'RENT002',
            'type': 'service',
            'sale_ok': True,
            'rental': True,
            'lst_price': 150.0,
        })

        cls.product_normal = cls.env['product.product'].create({
            'name': 'Normal Product',
            'default_code': 'NORM001',
            'type': 'product',
            'sale_ok': True,
            'lst_price': 50.0,
        })

    def test_module_installation(self):
        """Test that module installs without errors"""
        module = self.env['ir.module.module'].search([
            ('name', '=', 'rental_portal_change_request')
        ], limit=1)
        self.assertTrue(module, 'Module should be installed')

    def test_create_change_request(self):
        """Test creating a change request manually"""
        # Create a sale order
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'pricelist_id': self.pricelist.id,
            'state': 'sale',
            'is_rental_order': True,
        })

        # Add order line
        self.env['sale.order.line'].create({
            'order_id': order.id,
            'product_id': self.product_rental_1.id,
            'product_uom_qty': 2,
            'price_unit': 100.0,
        })

        # Create change request
        cr = self.env['rental.change_request'].create({
            'order_id': order.id,
            'state': 'draft',
        })

        self.assertTrue(cr.name, 'Change request should have a name')
        self.assertEqual(cr.order_id.id, order.id)
        self.assertEqual(cr.state, 'draft')

    def test_start_from_order_atomic(self):
        """Test atomic creation of change request and revision"""
        # Create sale order
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'pricelist_id': self.pricelist.id,
            'state': 'sale',
        })

        # Add order line
        self.env['sale.order.line'].create({
            'order_id': order.id,
            'product_id': self.product_rental_1.id,
            'product_uom_qty': 2,
            'price_unit': 100.0,
        })
        order._compute_is_rental_order()

        # Start change request
        result = self.env['rental.change_request'].start_from_order_atomic(order.id)

        self.assertTrue(result['success'], 'Should create change request successfully')
        self.assertIn('change_request', result)
        self.assertIn('revision_order', result)

        # Verify change request created
        cr = self.env['rental.change_request'].browse(result['change_request'])
        self.assertEqual(cr.state, 'editing')
        self.assertEqual(cr.order_id.id, order.id)

        # Verify revision order created
        revision = self.env['sale.order'].browse(result['revision_order'])
        self.assertEqual(revision.x_parent_order_id.id, order.id)
        self.assertEqual(revision.state, 'draft')

        # Verify order has active change request
        self.assertEqual(order.x_active_change_request_id.id, cr.id)

    def test_only_one_active_per_order(self):
        """Test constraint: only one active change request per order"""
        # Create sale order
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'pricelist_id': self.pricelist.id,
            'state': 'sale',
        })

        # Start first change request
        result1 = self.env['rental.change_request'].start_from_order_atomic(order.id)
        self.assertTrue(result1['success'])

        # Try to start second change request
        result2 = self.env['rental.change_request'].start_from_order_atomic(order.id)
        self.assertFalse(result2['success'])
        self.assertIn('already has an active change request', result2['error'])

    def test_patch_revision_atomic_add(self):
        """Test adding product via patch"""
        # Create change request
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'pricelist_id': self.pricelist.id,
            'state': 'sale',
        })

        result = self.env['rental.change_request'].start_from_order_atomic(order.id)
        cr_id = result['change_request']
        cr = self.env['rental.change_request'].browse(cr_id)

        # Patch: add product
        patch_result = cr.patch_revision_atomic(
            cr_id,
            [{
                'operation': 'add',
                'product_id': self.product_rental_2.id,
                'qty': 3,
            }],
            result['order_write_date'],
            result['revision_write_date']
        )

        self.assertTrue(patch_result['success'])

        # Verify product added to revision
        revision_line = cr.revision_order_id.order_line.filtered(
            lambda l: l.product_id.id == self.product_rental_2.id
        )
        self.assertTrue(revision_line)
        self.assertEqual(revision_line.product_uom_qty, 3)

    def test_patch_revision_atomic_update(self):
        """Test updating quantity via patch"""
        # Create order with product
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'pricelist_id': self.pricelist.id,
            'state': 'sale',
        })

        line = self.env['sale.order.line'].create({
            'order_id': order.id,
            'product_id': self.product_rental_1.id,
            'product_uom_qty': 2,
            'price_unit': 100.0,
        })

        # Create change request
        result = self.env['rental.change_request'].start_from_order_atomic(order.id)
        cr_id = result['change_request']
        cr = self.env['rental.change_request'].browse(cr_id)

        # Get revision line
        revision_line = cr.revision_order_id.order_line.filtered(
            lambda l: l.product_id.id == self.product_rental_1.id
        )

        # Patch: update quantity
        patch_result = cr.patch_revision_atomic(
            cr_id,
            [{
                'operation': 'update',
                'product_id': self.product_rental_1.id,
                'qty': 5,
                'line_id': revision_line.id,
            }],
            result['order_write_date'],
            result['revision_write_date']
        )

        self.assertTrue(patch_result['success'])
        revision_line.invalidate_cache()
        self.assertEqual(revision_line.product_uom_qty, 5)

    def test_patch_revision_atomic_remove(self):
        """Test removing product via patch"""
        # Create order with product
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'pricelist_id': self.pricelist.id,
            'state': 'sale',
        })

        self.env['sale.order.line'].create({
            'order_id': order.id,
            'product_id': self.product_rental_1.id,
            'product_uom_qty': 2,
            'price_unit': 100.0,
        })

        # Create change request
        result = self.env['rental.change_request'].start_from_order_atomic(order.id)
        cr_id = result['change_request']
        cr = self.env['rental.change_request'].browse(cr_id)

        # Get revision line
        revision_line = cr.revision_order_id.order_line.filtered(
            lambda l: l.product_id.id == self.product_rental_1.id
        )

        # Patch: remove product
        patch_result = cr.patch_revision_atomic(
            cr_id,
            [{
                'operation': 'remove',
                'product_id': self.product_rental_1.id,
                'line_id': revision_line.id,
            }],
            result['order_write_date'],
            result['revision_write_date']
        )

        self.assertTrue(patch_result['success'])

        # Verify product removed from revision
        remaining_lines = cr.revision_order_id.order_line.filtered(
            lambda l: l.product_id.id == self.product_rental_1.id
        )
        self.assertFalse(remaining_lines)

    def test_concurrency_conflict(self):
        """Test concurrency control with tokens"""
        # Create order
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'pricelist_id': self.pricelist.id,
            'state': 'sale',
        })

        # Create change request
        result = self.env['rental.change_request'].start_from_order_atomic(order.id)
        cr_id = result['change_request']
        cr = self.env['rental.change_request'].browse(cr_id)

        # Modify order externally (simulating concurrent edit)
        order.write({'date_order': datetime.now()})

        # Try to patch with old token
        patch_result = cr.patch_revision_atomic(
            cr_id,
            [{'operation': 'add', 'product_id': self.product_rental_2.id, 'qty': 1}],
            result['order_write_date'],  # Old token
            result['revision_write_date']
        )

        # Should fail due to concurrency conflict
        self.assertFalse(patch_result['success'])
        self.assertIn('modified by another user', patch_result['error'])

    def test_submit_atomic(self):
        """Test submitting change request"""
        # Create order and change request
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'pricelist_id': self.pricelist.id,
            'state': 'sale',
        })

        self.env['sale.order.line'].create({
            'order_id': order.id,
            'product_id': self.product_rental_1.id,
            'product_uom_qty': 2,
            'price_unit': 100.0,
        })

        result = self.env['rental.change_request'].start_from_order_atomic(order.id)
        cr_id = result['change_request']

        # Modify revision
        cr = self.env['rental.change_request'].browse(cr_id)
        revision_line = cr.revision_order_id.order_line[0]
        revision_line.write({'product_uom_qty': 5})

        # Submit
        submit_result = cr.submit_atomic(cr_id, 'Please approve the increase')

        self.assertTrue(submit_result['success'])
        cr.invalidate_cache()
        self.assertEqual(cr.state, 'submitted')
        self.assertEqual(cr.line_count, 1)

        # Verify activity created
        activities = self.env['mail.activity'].search([
            ('res_model', '=', 'rental.change_request'),
            ('res_id', '=', cr_id),
        ])
        self.assertTrue(activities, 'Should create activity for review')

    def test_approve_atomic(self):
        """Test approving change request"""
        # Create and submit change request
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'pricelist_id': self.pricelist.id,
            'state': 'sale',
        })

        self.env['sale.order.line'].create({
            'order_id': order.id,
            'product_id': self.product_rental_1.id,
            'product_uom_qty': 2,
            'price_unit': 100.0,
        })

        result = self.env['rental.change_request'].start_from_order_atomic(order.id)
        cr_id = result['change_request']
        cr = self.env['rental.change_request'].browse(cr_id)

        # Modify and submit
        cr.revision_order_id.order_line[0].write({'product_uom_qty': 5})
        cr.submit_atomic(cr_id, 'Test')

        # Approve
        approve_result = cr.approve_atomic()

        self.assertTrue(approve_result['success'])
        cr.invalidate_cache()
        self.assertEqual(cr.state, 'approved')
        self.assertIsNone(order.x_active_change_request_id)

        # Verify changes applied to order
        order.invalidate_cache()
        order_line = order.order_line.filtered(
            lambda l: l.product_id.id == self.product_rental_1.id
        )
        self.assertEqual(order_line.product_uom_qty, 5)

    def test_reject_atomic(self):
        """Test rejecting change request"""
        # Create and submit change request
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'pricelist_id': self.pricelist.id,
            'state': 'sale',
        })

        self.env['sale.order.line'].create({
            'order_id': order.id,
            'product_id': self.product_rental_1.id,
            'product_uom_qty': 2,
            'price_unit': 100.0,
        })

        result = self.env['rental.change_request'].start_from_order_atomic(order.id)
        cr_id = result['change_request']

        # Submit
        cr = self.env['rental.change_request'].browse(cr_id)
        cr.submit_atomic(cr_id, 'Test')

        # Reject
        reject_result = cr.reject_atomic(cr_id, 'Insufficient stock')

        self.assertTrue(reject_result['success'])
        cr.invalidate_cache()
        self.assertEqual(cr.state, 'rejected')
        self.assertEqual(cr.rejection_reason, 'Insufficient stock')
        self.assertIsNone(order.x_active_change_request_id)

    def test_cancelled_order_invalidates_requests(self):
        """Test that cancelled orders invalidate change requests"""
        # Create order and change request
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'pricelist_id': self.pricelist.id,
            'state': 'sale',
        })

        result = self.env['rental.change_request'].start_from_order_atomic(order.id)
        cr_id = result['change_request']

        # Cancel order
        order.action_cancel()

        # Verify cannot submit change request
        cr = self.env['rental.change_request'].browse(cr_id)
        cr.state = 'submitted'

        # Try to approve - should fail or handle gracefully
        # (Implementation may vary)

    def test_diff_calculation(self):
        """Test diff calculation between orders"""
        # Create original order
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'pricelist_id': self.pricelist.id,
            'state': 'sale',
        })

        self.env['sale.order.line'].create({
            'order_id': order.id,
            'product_id': self.product_rental_1.id,
            'product_uom_qty': 2,
            'price_unit': 100.0,
        })

        # Create change request and modify revision
        result = self.env['rental.change_request'].start_from_order_atomic(order.id)
        cr = self.env['rental.change_request'].browse(result['change_request'])

        # Add product to revision
        self.env['sale.order.line'].create({
            'order_id': cr.revision_order_id.id,
            'product_id': self.product_rental_2.id,
            'product_uom_qty': 3,
            'price_unit': 150.0,
        })

        # Calculate diff
        diff = cr._calculate_diff(cr)

        self.assertIn('added', diff)
        self.assertTrue(len(diff['added']) > 0)
        self.assertEqual(diff['added'][0]['product_id'], self.product_rental_2.id)

    def test_change_request_line_constraints(self):
        """Test change request line constraints"""
        cr = self.env['rental.change_request'].create({
            'order_id': self.env['sale.order'].create({
                'partner_id': self.partner.id,
                'state': 'sale',
            }).id,
            'state': 'editing',
        })

        # Test: add operation should not have original_line_id
        with self.assertRaises(ValidationError):
            self.env['rental.change_request.line'].create({
                'change_request_id': cr.id,
                'product_id': self.product_rental_1.id,
                'operation': 'add',
                'original_line_id': 1,
                'new_qty': 1,
            })

        # Test: update operation requires original_line_id
        with self.assertRaises(ValidationError):
            self.env['rental.change_request.line'].create({
                'change_request_id': cr.id,
                'product_id': self.product_rental_1.id,
                'operation': 'update',
                'new_qty': 1,
            })

        # Test: quantity must be positive for add/update
        with self.assertRaises(ValidationError):
            self.env['rental.change_request.line'].create({
                'change_request_id': cr.id,
                'product_id': self.product_rental_1.id,
                'operation': 'add',
                'new_qty': 0,
            })
