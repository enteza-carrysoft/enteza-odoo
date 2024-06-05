# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) Fidobe Solutions LLC.
#
#    For Module Support : crp@fidobe.com
#
##############################################################################

from odoo import fields, api, models, _
from datetime import datetime


class GenerateStockSummary(models.TransientModel):
    _name = "stock.summary.generate"
    _description = "Generate Stock Summary"

    inventory_datetime = fields.Date(
        string="Inventory at Date",
        default=fields.Date.today(),
    )

    def _create_inv_location(self, move_line):
        quantity = move_line.qty_done * move_line.product_uom_id.factor_inv
        if (
            move_line.product_uom_id.factor_inv
            and move_line.product_id.uom_id.factor_inv
        ):
            quantity = move_line.qty_done * (
                move_line.product_uom_id.factor_inv
                / move_line.product_id.uom_id.factor_inv
            )
        vals = {
            "date": move_line.date,
            "product_id": move_line.product_id.id,
            "categ_id": move_line.product_id.categ_id.id,
            "location_id": move_line.location_dest_id.id,
            "lot_id": move_line.lot_id.id,
            "quantity": quantity,
            "product_uom": move_line.product_id.uom_id.id,
        }
        inv = self.env["stock.summary"].create(vals)

    def get_plus_quantity(self, move_line):
        InventoryByLocation = self.env["stock.summary"]
        inv_loc_id = InventoryByLocation.search(
            [
                ("product_id", "=", move_line.product_id.id),
                ("location_id", "=", move_line.location_dest_id.id),
                ("lot_id", "=", move_line.lot_id.id),
            ],
            limit=1,
        )
        if inv_loc_id:
            quantity = inv_loc_id.quantity
            qty_done = move_line.qty_done * move_line.product_uom_id.factor_inv
            if (
                move_line.product_uom_id.factor_inv
                and move_line.product_id.uom_id.factor_inv
            ):
                qty_done = move_line.qty_done * (
                    move_line.product_uom_id.factor_inv
                    / move_line.product_id.uom_id.factor_inv
                )
            inv_loc_id.quantity = quantity + qty_done
        else:
            self._create_inv_location(move_line)

    def get_minus_quantity(self, move_line):
        InventoryByLocation = self.env["stock.summary"]
        inv_loc_id = InventoryByLocation.search(
            [
                ("product_id", "=", move_line.product_id.id),
                ("location_id", "=", move_line.location_id.id),
                ("lot_id", "=", move_line.lot_id.id),
            ],
            limit=1,
        )
        if inv_loc_id:
            qty_done = move_line.qty_done * move_line.product_uom_id.factor_inv
            if (
                move_line.product_uom_id.factor_inv
                and move_line.product_id.uom_id.factor_inv
            ):
                qty_done = move_line.qty_done * (
                    move_line.product_uom_id.factor_inv
                    / move_line.product_id.uom_id.factor_inv
                )
            if inv_loc_id.quantity <= move_line.qty_done:
                inv_loc_id.quantity = qty_done - inv_loc_id.quantity
            else:
                inv_loc_id.quantity -= qty_done

    def generate_report(self, domain):
        move_lines = self.env["stock.move.line"].search(domain)
        for line in move_lines.filtered(
            lambda l: l.location_dest_id.usage == "internal"
        ):
            self.get_plus_quantity(line)

        for line in move_lines.filtered(lambda l: l.location_id.usage == "internal"):
            self.get_minus_quantity(line)

    def open_at_date(self):
        self.env["stock.summary"].sudo().search([]).unlink()
        inv_date = str(self.inventory_datetime) + " 23:59:59"
        move_line_domain = [
            ("product_id.type", "=", "product"),
            ("product_id.active", "=", True),
            ("date", "<=", inv_date),
            ("state", "=", "done"),
        ]
        self.generate_report(domain=move_line_domain)
        action_domain = [
            ("product_id.type", "=", "product"),
            ("product_id.active", "=", True),
            ("date", "<=", inv_date),
        ]
        tree_view_id = self.env.ref(
            "fs_stock_by_location.fs_stock_summary_list_view"
        ).id
        form_view_id = self.env.ref(
            "fs_stock_by_location.fs_stock_summary_form_view"
        ).id
        action = {
            "type": "ir.actions.act_window",
            "views": [(tree_view_id, "tree"), (form_view_id, "form")],
            "view_mode": "tree,form",
            "name": _("Stock Summary %s" % (self.inventory_datetime)),
            "res_model": "stock.summary",
            "domain": action_domain,
            "context": {"to_date": self.inventory_datetime},
        }
        return action
