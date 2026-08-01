import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Comprueba que el ajuste «Direcciones de cliente» esté activado.

    Sin el grupo `account.group_delivery_invoice_address`, el campo `partner_shipping_id`
    (lugar de entrega) no se muestra a los usuarios y la ventana flotante del calendario
    sale incompleta. El módulo NO lo activa por su cuenta: es un ajuste de compañía que
    afecta a todos los usuarios y la decisión es del responsable (ver PRP §10.2).

    Ojo con el identificador técnico: en Odoo 19 este grupo vive en el módulo `account`,
    no en `sale`.
    """
    grupo = env.ref('account.group_delivery_invoice_address', raise_if_not_found=False)
    if not grupo:
        _logger.warning(
            'No se encuentra el grupo account.group_delivery_invoice_address. '
            'El lugar de entrega no aparecerá en el calendario de eventos.'
        )
        return

    grupo_usuario = env.ref('base.group_user', raise_if_not_found=False)
    if grupo_usuario and grupo not in grupo_usuario.implied_ids:
        _logger.warning(
            'El ajuste «Direcciones de cliente» está DESACTIVADO. El lugar de entrega no '
            'aparecerá en la ventana flotante del calendario de eventos. Actívalo en '
            'Ventas → Configuración → Ajustes → Presupuestos y pedidos → Direcciones de cliente.'
        )
