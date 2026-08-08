"""Comprobación de propiedad compartida entre `portal.py` y `api.py` (PRP §8.1, §8.2).

Un solo sitio para la regla "de quién es esta solicitud", en vez de dos implementaciones que
puedan divergir. Se apoya en la `ir.rule` nativa del portal (171, «Portal Personal
Quotations/Sales Orders», `partner_id child_of commercial_partner_id`) pero no confía solo en
ella: cinturón y tirantes.
"""
from odoo import _
from odoo.exceptions import AccessError, MissingError
from odoo.http import request


def enteza_partner_portal_ok():
    """El partner logado, si tiene permiso para el portal de pedidos (PRP §4.5).

    Recordset vacío si no lo tiene — nunca `None`, para que el llamador pueda usarlo
    directamente en una condición sin comprobar dos veces.
    """
    partner = request.env.user.partner_id
    return partner if partner.enteza_portal_pedidos_ok else request.env['res.partner']


def enteza_get_solicitud(order_id, requiere_composing=False):
    """Devuelve la solicitud YA `sudo()`-ada si pertenece al usuario logado.

    :param requiere_composing: si es `True`, además exige que siga en `composing`
        (`UserError` si no, vía `sale.order._enteza_portal_check_composing`)
    :raises AccessError: el usuario no tiene activado el portal de pedidos
    :raises MissingError: el pedido no existe o no es suyo (se trata igual a propósito: no
        hay que distinguirle a un cliente "no existe" de "no es tuyo")
    """
    partner = enteza_partner_portal_ok()
    if not partner:
        raise AccessError(_("No tienes acceso al portal de pedidos."))

    order = request.env['sale.order'].sudo().browse(order_id).exists()
    if not order or order.partner_id.commercial_partner_id != partner.commercial_partner_id:
        raise MissingError(_("Esta solicitud no existe o no tienes acceso a ella."))

    if requiere_composing:
        order._enteza_portal_check_composing()

    return order
