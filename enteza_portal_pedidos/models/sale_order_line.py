from odoo import fields, models


class SaleOrderLine(models.Model):
    """Semáforo guardado (PRP §4.2). No es la fuente de verdad: solo lo que vio el cliente
    al enviar, para que el comercial lo tenga a la vista en el formulario sin recalcular.
    El comercial trabaja con el widget nativo `qty_at_date`.
    """
    _inherit = 'sale.order.line'

    enteza_portal_availability = fields.Selection(
        [('green', "Disponible"), ('amber', "Ajustado"), ('red', "Sin disponibilidad"),
         ('grey', "Sin datos")],
        string="Semáforo (portal)", copy=False, readonly=True)

    enteza_portal_availability_date = fields.Datetime(
        string="Semáforo calculado el", copy=False, readonly=True)
