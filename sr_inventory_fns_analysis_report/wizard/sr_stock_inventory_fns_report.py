# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) Sitaram Solutions (<https://sitaramsolutions.in/>).
#
#    For Module Support : info@sitaramsolutions.in  or Skype : contact.hiren1188
#
##############################################################################

from odoo import fields, models
import base64
import xlwt

try:
    from odoo.tools.misc import xlsxwriter
except ImportError:
    import xlsxwriter


class srStockInventoryFNSReport(models.TransientModel):
    _name = 'stock.inventory.fns.report'
    _description = "Inventory FNS Analyse Report"

    start_date = fields.Date(required=True)
    end_date = fields.Date(required=True)
    product_ids = fields.Many2many('product.product')
    categ_ids = fields.Many2many('product.category', string="Product Category")
    fns_base_on = fields.Selection([("average_stay", "Average Stay"), ("consumption_rate", "Consumption Rate")],
                                   default="average_stay")

    def report_generate_pdf(self):
        data = {}
        return self.env.ref(
            'sr_inventory_fns_analysis_report.sr_stock_inventory_fns_report_template').report_action(None, data=data)

    def report_generate_excel(self):
        datas = self.env['report.sr_inventory_fns_analysis_report.fns_template']._get_report_values(docids=self.ids)[
            'fns_data']
        workbook = xlsxwriter.Workbook('stock_inventory_fns_report.xlsx')
        worksheet = workbook.add_worksheet()
        header_merge_format = workbook.add_format({
            'bold': 1,
            'align': 'center',
            'valign': 'vcenter',
        })
        merge_value_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
        })
        worksheet.merge_range('A2:J3', 'Stock Inventory FNS Analysis Report', header_merge_format)
        if self.start_date:
            worksheet.merge_range('A5:B5', 'Start Date', header_merge_format)
            worksheet.merge_range('A6:B6', str(self.start_date), merge_value_format)
        if self.end_date:
            worksheet.merge_range('C5:D5', 'End Date', header_merge_format)
            worksheet.merge_range('C6:D6', str(self.end_date), merge_value_format)
        if self.categ_ids:
            worksheet.merge_range('E5:F5', 'Categories', header_merge_format)
            worksheet.merge_range('E6:F6', ','.join(self.categ_ids.mapped('name')), merge_value_format)
        if self.product_ids:
            worksheet.merge_range('G5:H5', 'Products', header_merge_format)
            worksheet.merge_range('G6:H6', ','.join(self.product_ids.mapped('name')), merge_value_format)
        if self.fns_base_on:
            worksheet.merge_range('I5:J5', 'FNS based on', header_merge_format)
            worksheet.merge_range('I6:J6', self.fns_base_on, merge_value_format)
        row = 8

        if self.fns_base_on == 'average_stay':
            worksheet.write(7, 0, 'Product',header_merge_format)
            worksheet.write(7, 1, 'Average Stay',header_merge_format)
            worksheet.write(7, 2, 'Cum. Average Stay',header_merge_format)
            worksheet.write(7, 3, '% Average Stay',header_merge_format)
            worksheet.write(7, 4, 'FNS Classification',header_merge_format)
        else:
            worksheet.write(7, 0, 'Product',header_merge_format)
            worksheet.write(7, 1, 'Consumption Rate',header_merge_format)
            worksheet.write(7, 2, 'Cum. Consumption Rate',header_merge_format)
            worksheet.write(7, 3, '% Consumption Rate',header_merge_format)
            worksheet.write(7, 4, 'FNS Classification',header_merge_format)
        for item in datas:
            worksheet.write(row, 0, item.get('prod_name',),merge_value_format)
            worksheet.write(row, 1, float("{:.2f}".format(item.get('average_stay'))),merge_value_format)
            worksheet.write(row, 2, float("{:.2f}".format(item.get('cum_rate'))),merge_value_format)
            worksheet.write(row, 3, float("{:.2f}".format(item.get('percentage_rate'))),merge_value_format)
            worksheet.write(row, 4, item.get('fns_classification'),merge_value_format)
            row += 1
        workbook.close()

        file = open('stock_inventory_fns_report.xlsx', 'rb').read()

        attachment = self.env['ir.attachment'].create({
            'name': 'stock_inventory_fns_report.xlsx',
            'datas': base64.encodebytes(file),
            'res_id': self.id,
            'res_model': 'stock.inventory.fns.report',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/binary/export/%s' % attachment.id,
            'target': 'new',
        }

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: