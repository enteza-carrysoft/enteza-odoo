"""Comprobación de propiedad y manejo de errores, compartidos entre `portal.py` y `api.py`
(PRP §8.1, §8.2; PRP v2 §5.5, F1).

Un solo sitio para la regla "de quién es esta solicitud", en vez de dos implementaciones que
puedan divergir. Se apoya en la `ir.rule` nativa del portal (171, «Portal Personal
Quotations/Sales Orders», `partner_id child_of commercial_partner_id`) pero no confía solo en
ella: cinturón y tirantes.

🔴 PRP v2 §5.5: en el diseño anterior, `enteza_get_solicitud(..., requiere_composing=True)`
se llamaba FUERA del `try/except` de cada ruta de `api.py`, así que una `UserError` /
`AccessError` / `MissingError` llegaba cruda al transporte JSON-RPC. Y ningún RPC del lado
JS estaba protegido, así que la promesa se rechazaba sin que nadie la atendiera: el usuario
no veía nada, ni siquiera en la consola. `enteza_json_endpoint` envuelve el cuerpo ENTERO de
cada ruta, así ya no hace falta acordarse de poner un `try` en cada una.
"""
import functools
import logging

from odoo import _
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)


def enteza_partner_portal_ok():
    """El partner logado, si tiene permiso para el portal de pedidos (PRP §4.5).

    Recordset vacío si no lo tiene — nunca `None`, para que el llamador pueda usarlo
    directamente en una condición sin comprobar dos veces.
    """
    partner = request.env.user.partner_id
    return partner if partner.enteza_portal_pedidos_ok else request.env['res.partner']


def enteza_get_solicitud(order_id):
    """Devuelve la solicitud YA `sudo()`-ada si pertenece al usuario logado.

    La comprobación de si sigue en `composing` ya no se hace aquí (PRP v2): cada método del
    modelo que la necesita llama a `_enteza_portal_check_composing()` por su cuenta, y el
    error que lanza lo atrapa `enteza_json_endpoint` igual que cualquier otro.

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

    return order


_ENTEZA_ERROR_CODES = (
    (AccessError, 'no_acceso'),
    (MissingError, 'no_encontrado'),
    (ValidationError, 'validacion'),
    (UserError, 'validacion'),
)


def enteza_json_endpoint(func):
    """Envuelve una ruta `type='jsonrpc'` entera: cualquier excepción de negocio se
    convierte en `{'error': texto, 'error_code': codigo}` en vez de llegar cruda al
    transporte. Cualquier OTRA excepción (un bug, no un error de negocio) se registra con el
    traceback completo y se devuelve un mensaje genérico — nunca el traceback al cliente.

    Con esto, ningún endpoint puede "lanzar hacia el transporte": el JS siempre recibe un
    JSON con forma predecible, `{ok: true, ...}` o `{error, error_code}`, y puede decidir
    qué mostrar sin tener que adivinar el formato del error de turno.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except _ENTEZA_ERROR_CODES_TUPLE as error:
            codigo = next(
                (codigo for clase, codigo in _ENTEZA_ERROR_CODES if isinstance(error, clase)),
                'validacion',
            )
            return {'error': str(error), 'error_code': codigo}
        except Exception:
            _logger.exception(
                "Error inesperado en el endpoint del portal de pedidos: %s", func.__name__)
            return {
                'error': str(_(
                    "Ha ocurrido un error inesperado. Inténtalo de nuevo en unos minutos.")),
                'error_code': 'interno',
            }
    return wrapper


_ENTEZA_ERROR_CODES_TUPLE = tuple(clase for clase, _codigo in _ENTEZA_ERROR_CODES)
