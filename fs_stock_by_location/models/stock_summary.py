# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) Fidobe Solutions LLC.
#
#    For Module Support : crp@fidobe.com
#
##############################################################################

from odoo import fields, api, models


class StockSummary(models.Model):
    _name = "stock.summary"
    _description = "Stock Summary"

    location_id = fields.Many2one("stock.location", string="Location")
    lot_id = fields.Many2one("stock.production.lot", string="Lot/Serial Number")
    product_id = fields.Many2one("product.product", string="Product")
    product_code = fields.Char(related="product_id.default_code", string="Product Code")
    categ_id = fields.Many2one("product.category", string="Product Category")
    quantity = fields.Float(string="OnHand Qty")
    date = fields.Datetime(string="Date")
    product_uom = fields.Many2one("uom.uom", string="Unit of Measure")
    value = fields.Float(compute="_compute_total_value", string="Value", store=True)

    @api.depends_context("to_date")
    @api.depends("quantity")
    def _compute_total_value(self):
        for inv in self:
            inv.value = inv.product_id.standard_price * inv.quantity
