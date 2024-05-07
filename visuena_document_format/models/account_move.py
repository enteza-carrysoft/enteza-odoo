# -*- coding: utf-8 -*-
# Copyright 2021 - Daniel Domínguez https://xtendoo.es/

from odoo import api, fields, models, _


class AccountMove(models.Model):
    _inherit = 'account.move'

#    @api.onchange('invoice_line_ids')
#    def _onchange_invoice_line_ids(self):
#        categories = []
#        for line in self.invoice_line_ids:
#            categories.append(line.product_id.categ_id.id)
#        used_categories = self.env["product.category"].search([('id', 'in', categories)])
#        self.used_categories = used_categories
#        super(AccountMove, self)._onchange_invoice_line_ids()

    @api.depends('invoice_line_ids.product_id.categ_id')
    def _compute_used_categories(self):
        for accountmove in self:
            categories = accountmove.invoice_line_ids.mapped('product_id.categ_id')
            accountmove.used_categories = [(6, 0, categories.ids)]

    event_date = fields.Date(
        string="Fecha Evento",
    )

    used_categories = fields.Many2many(
        'product.category',
        string='Categoria',
        compute=_compute_used_categories,
    )
