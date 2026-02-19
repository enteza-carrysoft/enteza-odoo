# -*- coding: utf-8 -*-
"""
Diff utilities for calculating changes between orders.

This module provides utilities for comparing original and revision orders
and generating structured diff representations.
"""

from odoo import models, api


class DiffUtils(models.AbstractModel):
    _name = 'rental.diff.utils'
    _description = 'Diff Utilities for Change Requests'

    @api.model
    def calculate_order_lines_diff(self, original_lines, revision_lines):
        """
        Calculate differences between original and revision order lines.

        Args:
            original_lines: sale.order.line recordset from original order
            revision_lines: sale.order.line recordset from revision order

        Returns:
            dict: {
                'added': [{product_id, qty, price_unit}],
                'removed': [{product_id, qty, price_unit, line_id}],
                'updated': [{product_id, original_qty, new_qty, original_price, new_price}]
            }
        """
        from odoo.tools import float_compare

        # Create lookup dictionaries
        original_dict = {line.product_id.id: line for line in original_lines}
        revision_dict = {line.product_id.id: line for line in revision_lines}

        diff = {
            'added': [],
            'removed': [],
            'updated': [],
        }

        # Check for added and updated products
        for product_id, rev_line in revision_dict.items():
            if product_id not in original_dict:
                # Product added
                diff['added'].append({
                    'product_id': product_id,
                    'product_name': rev_line.product_id.display_name,
                    'product_code': rev_line.product_id.default_code or '',
                    'qty': float(rev_line.product_uom_qty),
                    'price_unit': float(rev_line.price_unit),
                    'price_subtotal': float(rev_line.price_subtotal),
                })
            else:
                # Check if product was updated
                orig_line = original_dict[product_id]
                # Use product's UoM rounding for quantity comparison
                uom_rounding = rev_line.product_id.uom_id.rounding if rev_line.product_id.uom_id else 0.01
                qty_changed = float_compare(
                    rev_line.product_uom_qty,
                    orig_line.product_uom_qty,
                    precision_rounding=uom_rounding
                ) != 0
                price_changed = float_compare(
                    rev_line.price_unit,
                    orig_line.price_unit,
                    precision_rounding=0.01
                ) != 0

                if qty_changed or price_changed:
                    diff['updated'].append({
                        'product_id': product_id,
                        'product_name': rev_line.product_id.display_name,
                        'product_code': rev_line.product_id.default_code or '',
                        'original_qty': float(orig_line.product_uom_qty),
                        'new_qty': float(rev_line.product_uom_qty),
                        'original_price': float(orig_line.price_unit),
                        'new_price': float(rev_line.price_unit),
                        'original_subtotal': float(orig_line.price_subtotal),
                        'new_subtotal': float(rev_line.price_subtotal),
                    })

        # Check for removed products
        for product_id, orig_line in original_dict.items():
            if product_id not in revision_dict:
                diff['removed'].append({
                    'product_id': product_id,
                    'product_name': orig_line.product_id.display_name,
                    'product_code': orig_line.product_id.default_code or '',
                    'qty': float(orig_line.product_uom_qty),
                    'price_unit': float(orig_line.price_unit),
                    'price_subtotal': float(orig_line.price_subtotal),
                    'line_id': orig_line.id,
                })

        return diff

    @api.model
    def format_diff_summary(self, diff):
        """
        Create a human-readable summary of the diff.

        Args:
            diff: dict returned by calculate_order_lines_diff

        Returns:
            str: Formatted summary
        """
        lines = []

        if diff['added']:
            lines.append(f"<strong>Added {len(diff['added'])} product(s):</strong>")
            for item in diff['added']:
                lines.append(
                    f"  + {item['product_name']} (x{item['qty']})"
                )

        if diff['removed']:
            lines.append(f"<strong>Removed {len(diff['removed'])} product(s):</strong>")
            for item in diff['removed']:
                lines.append(
                    f"  - {item['product_name']} (x{item['qty']})"
                )

        if diff['updated']:
            lines.append(f"<strong>Updated {len(diff['updated'])} product(s):</strong>")
            for item in diff['updated']:
                lines.append(
                    f"  ~ {item['product_name']}: {item['original_qty']} -> {item['new_qty']}"
                )

        return '\n'.join(lines) if lines else _('No changes')

    @api.model
    def calculate_total_impact(self, diff):
        """
        Calculate the total financial impact of changes.

        Args:
            diff: dict returned by calculate_order_lines_diff

        Returns:
            dict: {
                'added_amount': float,
                'removed_amount': float,
                'updated_amount': float,
                'net_change': float
            }
        """
        added_amount = sum(
            item.get('price_subtotal', 0) for item in diff['added']
        )
        removed_amount = sum(
            item.get('price_subtotal', 0) for item in diff['removed']
        )
        updated_new_amount = sum(
            item.get('new_subtotal', 0) for item in diff['updated']
        )
        updated_original_amount = sum(
            item.get('original_subtotal', 0) for item in diff['updated']
        )

        return {
            'added_amount': added_amount,
            'removed_amount': removed_amount,
            'updated_original_amount': updated_original_amount,
            'updated_new_amount': updated_new_amount,
            'net_change': added_amount - removed_amount + (updated_new_amount - updated_original_amount),
        }
