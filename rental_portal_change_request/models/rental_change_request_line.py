# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class RentalChangeRequestLine(models.Model):
    _name = 'rental.change_request.line'
    _description = 'Rental Change Request Line'
    _order = 'change_request_id, sequence, id'
    # Odoo 19: use _rec_name + _compute_display_name instead of name_get()
    _rec_name = 'product_id'

    change_request_id = fields.Many2one(
        'rental.change_request',
        string='Change Request',
        required=True,
        ondelete='cascade',
        index=True
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        index=True
    )
    uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        related='product_id.uom_id',
        store=True,
        readonly=True,
    )
    operation = fields.Selection([
        ('add', 'Add'),
        ('update', 'Update'),
        ('remove', 'Remove'),
    ], string='Operation', required=True, default='add')

    # Original order line reference
    original_line_id = fields.Many2one(
        'sale.order.line',
        string='Original Line',
        ondelete='set null',
        help='Original order line being modified'
    )

    # Revision order line reference
    revision_line_id = fields.Many2one(
        'sale.order.line',
        string='Revision Line',
        ondelete='set null',
        help='Line in the revision order'
    )

    # Original values for comparison
    original_qty = fields.Float(
        string='Original Quantity',
        digits='Product Unit of Measure',
        help='Original quantity in the order'
    )
    original_price_unit = fields.Float(
        string='Original Price',
        digits='Product Price',
        help='Original unit price'
    )

    # New/updated values
    new_qty = fields.Float(
        string='New Quantity',
        digits='Product Unit of Measure',
        help='New quantity in the revision'
    )
    new_price_unit = fields.Float(
        string='New Price',
        digits='Product Price',
        help='New unit price'
    )

    # Additional info
    note = fields.Text(
        string='Note',
        help='Additional notes about this change'
    )
    availability_status = fields.Selection([
        ('available', 'Available'),
        ('partial', 'Partially Available'),
        ('unavailable', 'Unavailable'),
        ('unknown', 'Unknown'),
    ], string='Availability Status', default='unknown')

    available_qty = fields.Float(
        string='Available Quantity',
        digits='Product Unit of Measure',
        help='Quantity available for rental'
    )

    @api.constrains('operation', 'original_line_id', 'new_qty')
    def _check_operation_consistency(self):
        """Validate operation consistency"""
        for line in self:
            if line.operation == 'update' and not line.original_line_id:
                raise ValidationError(_(
                    'Update operation requires an original line reference.'
                ))
            if line.operation == 'remove' and not line.original_line_id:
                raise ValidationError(_(
                    'Remove operation requires an original line reference.'
                ))
            if line.operation == 'add' and line.original_line_id:
                raise ValidationError(_(
                    'Add operation should not have an original line reference.'
                ))
            if line.operation in ['update', 'add'] and line.new_qty <= 0:
                raise ValidationError(_(
                    'Quantity must be greater than zero for add/update operations.'
                ))

    def _compute_display_name(self):
        """Odoo 19 replacement for deprecated name_get()"""
        for line in self:
            name = f"{line.product_id.display_name} ({line.operation})"
            if line.original_line_id:
                name += f" - Original: {line.original_qty}"
            if line.new_qty:
                name += f" - New: {line.new_qty}"
            line.display_name = name
