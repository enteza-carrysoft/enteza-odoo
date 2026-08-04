from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    enteza_dia_traslado_semana = fields.Selection(
        related='company_id.enteza_dia_traslado_semana', readonly=False,
        string='Día de traslado entre compañías',
    )
