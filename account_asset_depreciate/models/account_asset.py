from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountAsset(models.Model):
    _inherit = 'account.asset'

    def decrement_asset_value(self, decrement_amount):
        """Decrement the asset value and recalculate depreciation."""
        self.ensure_one()
        if decrement_amount <= 0:
            raise UserError(_('Decrement amount must be positive.'))

        if decrement_amount >= self.value_residual:
            raise UserError(_('Decrement amount cannot be greater than the residual value.'))

        # Decrease the asset value
        self.value = self.value - decrement_amount
        # Recalculate the residual value
        self.value_residual = self.value_residual - decrement_amount

        # Recalculate the depreciation
        self.compute_depreciation_board()

    def compute_depreciation_board(self):
        """Recompute the depreciation board after asset value change."""
        # Clear existing depreciation lines
        self.depreciation_line_ids.unlink()

        # Create new depreciation lines based on the new value
        # Note: This is a simplified version. You may need to customize it
        # according to your depreciation method and other business logic.
        sequence = 1
        for line in self.depreciation_line_ids:
            line.unlink()

        amount_to_depreciate = self.value_residual
        for period in range(self.method_number):
            amount = amount_to_depreciate / (self.method_number - period)
            self.env['account.asset.depreciation.line'].create({
                'amount': amount,
                'asset_id': self.id,
                'sequence': sequence,
                'remaining_value': amount_to_depreciate - amount,
                'depreciated_value': self.value - amount_to_depreciate,
            })
            amount_to_depreciate -= amount
            sequence += 1

