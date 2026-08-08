from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    enteza_portal_semaforo = fields.Boolean(
        related='company_id.enteza_portal_semaforo', readonly=False,
        string="Mostrar semáforo de disponibilidad en el portal")

    enteza_portal_dias_minimos = fields.Integer(
        related='company_id.enteza_portal_dias_minimos', readonly=False,
        string="Antelación mínima (días)")

    enteza_portal_aviso_email = fields.Boolean(
        related='company_id.enteza_portal_aviso_email', readonly=False,
        string="Avisar al comercial también por correo")

    enteza_portal_user_id = fields.Many2one(
        related='company_id.enteza_portal_user_id', readonly=False,
        string="Comercial por defecto del portal")
