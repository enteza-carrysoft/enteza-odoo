# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) Sitaram Solutions (<https://sitaramsolutions.in/>).
#
#    For Module Support : info@sitaramsolutions.in  or Skype : contact.hiren1188
#
##############################################################################

from datetime import date, timedelta
from collections import OrderedDict
from odoo import api, models


class srReportStockInventoryFNS(models.AbstractModel):
    _name = 'report.sr_inventory_fns_analysis_report.fns_template'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['stock.inventory.fns.report'].browse(docids)

        if docs.product_ids and docs.categ_ids:
            products = docs.product_ids.search(
                ['|', ('id', 'in', docs.product_ids.ids), ('categ_id', 'in', docs.categ_ids.ids)])
        elif docs.product_ids and not docs.categ_ids:
            products = docs.product_ids.search([('id', 'in', docs.product_ids.ids)])
        elif docs.categ_ids:
            products = docs.product_ids.search([('categ_id', 'in', docs.categ_ids.ids)])
        else:
            products = docs.product_ids.search([])

        product_dict = {}
        fns_stay_on_dict = {}
        for product in products:
            inv_holding_days = 0
            total_receipt_qty = 0
            total_issue_qty = 0
            dict_day_wise = []
            moves = self.env['stock.move.line'].search([('product_id', '=', product.id), ('state', '=', 'done')])
            purchase_moves = moves.filtered(lambda rec: rec.location_dest_id.usage == 'internal')
            sales_moves = moves.filtered(lambda rec: rec.location_id.usage == 'internal')

            opening_balance = sum(move.qty_done for move in
                                  purchase_moves.filtered(lambda rec: rec.date.date() < docs.start_date)) - sum(
                move.qty_done for move in sales_moves.filtered(lambda rec: rec.date.date() < docs.start_date))
            closing_balance = opening_balance
            total_days = ((docs.end_date - docs.start_date).days)+1
            for day in range(0, total_days):

                today_moves = moves.filtered(lambda x: x.date.date() == docs.start_date + timedelta(days=day))

                receipt_qty = sum(move.qty_done for move in today_moves.filtered(
                    lambda x: x.location_dest_id.usage == 'internal' and x.location_id.usage != 'inventory' and len(x.move_id.origin_returned_move_id) == 0))

                return_qty = sum(move.qty_done for move in today_moves.filtered(
                    lambda x: x.location_dest_id.usage == 'internal' and len(x.move_id.origin_returned_move_id) != 0))

                adjustment_received_qty = sum(move.qty_done for move in today_moves.filtered(
                    lambda x: x.location_id.usage == 'inventory' and x.location_dest_id.usage == 'internal'))
                adjustment_loss_qty = sum(move.qty_done for move in today_moves.filtered(
                    lambda x: x.location_dest_id.usage == 'inventory' and x.location_id.usage == 'internal'))
                adjustment_qty = adjustment_received_qty - adjustment_loss_qty

                issue_qty = sum(move.qty_done for move in today_moves.filtered(
                    lambda x: x.location_id.usage == 'internal' and x.location_dest_id.usage != 'inventory' and len(x.move_id.origin_returned_move_id) == 0))

                closing_balance = closing_balance + receipt_qty + return_qty + adjustment_qty - issue_qty
                inv_holding_days = closing_balance + inv_holding_days

                dict_day_wise.append({'date': docs.start_date + timedelta(days=day),
                                      'receipt_qty': receipt_qty,
                                      'return_qty': return_qty,
                                      'adjustment_qty': adjustment_qty,
                                      'issue_qty': issue_qty,
                                      'closing_balance': closing_balance,
                                      'inv_holding_days': inv_holding_days,
                                      })
                total_receipt_qty = total_receipt_qty + receipt_qty
                total_issue_qty = total_issue_qty + issue_qty
            product_dict.update({product.name: dict_day_wise})

            if docs.fns_base_on == 'average_stay':
                if (total_receipt_qty + opening_balance) > 0:
                    fns_stay_on_dict.update({product.name: inv_holding_days / (total_receipt_qty + opening_balance)}),
            else:
                fns_stay_on_dict.update({product.name: total_issue_qty/total_days})
        print(product_dict)

        sorted_fns_stay_on_dict = dict(sorted(fns_stay_on_dict.items(), key=lambda x:x[1]))

        print(sorted_fns_stay_on_dict)

        fns_list=[]
        average_stay=0
        total_fns = sum(sorted_fns_stay_on_dict.values())
        for product,fns in sorted_fns_stay_on_dict.items():
            average_stay= average_stay + fns
            percentage_rate = 0.0 if total_fns == 0 else (100 * average_stay / total_fns)
            if percentage_rate < 20.0:
                if docs.fns_base_on == 'average_stay':
                    fns_classification = 'N'
                else:
                    fns_classification = 'F'
            elif percentage_rate > 70.0:
                if docs.fns_base_on == 'average_stay':
                    fns_classification = 'F'
                else:
                    fns_classification = 'N'
            else:
                fns_classification = 'S'

            fns_list.append({'prod_name':product,
                             'average_stay': fns,
                             'cum_rate':average_stay,
                             'percentage_rate':percentage_rate,
                             'fns_classification':fns_classification})

        return {
            'doc_ids': docids,
            'doc_model': 'stock.inventory.fns.report',
            'docs': docs,
            'data': data,
            'fns_data':fns_list
        }

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: