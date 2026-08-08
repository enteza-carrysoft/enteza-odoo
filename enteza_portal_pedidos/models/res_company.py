from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    enteza_portal_semaforo = fields.Boolean(
        string="Mostrar semáforo de disponibilidad en el portal", default=False,
        help="Arranca desactivado a propósito: con el inventario a medio cargar, el "
             "semáforo diría «sin disponibilidad» en casi todo y el cliente lo leería como "
             "que no hay material. Activarlo es una decisión de negocio, cuando el almacén "
             "esté cargado de verdad.")

    enteza_portal_dias_minimos = fields.Integer(
        string="Antelación mínima (días)", default=2,
        help="Días de antelación que se piden al cliente entre hoy y la fecha de entrega. "
             "Solo orientativo en el portal: no bloquea el envío.")

    enteza_portal_aviso_email = fields.Boolean(
        string="Avisar al comercial también por correo", default=True,
        help="Además de la actividad y el mensaje en el chatter, envía la plantilla de "
             "correo al comercial asignado cuando el cliente envía una solicitud.")
