from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    enteza_portal_pedidos_ok = fields.Boolean(
        string="Puede solicitar pedidos por el portal", default=False, tracking=True,
        help="La puerta del módulo: sin esto marcado, un usuario del portal ve sus "
             "documentos de siempre pero no la pantalla de solicitud de material. Se activa "
             "cliente a cliente.")

    enteza_portal_warehouse_id = fields.Many2one(
        'stock.warehouse', string="Almacén habitual",
        help="Almacén desde el que se sirve por defecto a este cliente al abrir una "
             "solicitud nueva desde el portal. El cliente puede cambiarlo si tiene acceso a "
             "más de uno.")
