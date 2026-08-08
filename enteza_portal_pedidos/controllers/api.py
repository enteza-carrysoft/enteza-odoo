"""API JSON del portal de pedidos (PRP §8.2; PRP v2 F1).

🔴 `type='jsonrpc'`: en Odoo 19 es el nuevo nombre de lo que hasta la 18 era `type='json'`.
Con `type='json'` la ruta no se registra.

Todas comprueban propiedad con `enteza_get_solicitud` (PRP §8.1) antes de leer o escribir
nada, y el pedido que devuelve ya viene `sudo()`-ado: sin eso el grupo Portal no puede ni
leer el catálogo de producto (no tiene `ir.model.access` sobre `product.product`).

🔴 PRP v2: se eliminan `/cabecera` y `/lineas` (escritura incremental) y con ellas
`expected_write_date` (el bloqueo optimista que la propia maquinaria de alquiler invalidaba
sola). Las sustituye `/guardar`, que reconcilia el cesto completo en una transacción, y
`/enviar`, que guarda y envía en la misma transacción — así desaparece la carrera entre
"guardar" y "enviar" del diseño anterior.

Ninguna ruta añade `ok: true` a su respuesta: ese envoltorio lo pone
`RequestService._rpcSeguro` en el lado JS, de forma uniforme para las cinco (ok si no hay
`error`, ok:false si lo hay) — así no hace falta acordarse de ponerlo aquí ruta por ruta.
"""
from odoo.http import Controller, route

from .common import enteza_get_solicitud, enteza_json_endpoint


class PortalPedidosAPI(Controller):

    @route('/enteza_portal/solicitud/catalogo', type='jsonrpc', auth='user')
    @enteza_json_endpoint
    def catalogo(self, order_id, **kw):
        order = enteza_get_solicitud(order_id)
        return order._enteza_portal_payload_catalogo()

    @route('/enteza_portal/solicitud/guardar', type='jsonrpc', auth='user')
    @enteza_json_endpoint
    def guardar(self, order_id, header=None, lines=None, customer_note=None, **kw):
        order = enteza_get_solicitud(order_id)
        return order._enteza_portal_guardar(
            header=header, lines=lines, customer_note=customer_note)

    @route('/enteza_portal/solicitud/disponibilidad', type='jsonrpc', auth='user')
    @enteza_json_endpoint
    def disponibilidad(self, order_id, items=None, **kw):
        order = enteza_get_solicitud(order_id)
        return {'colors': order._enteza_portal_disponibilidad(items or [])}

    @route('/enteza_portal/solicitud/enviar', type='jsonrpc', auth='user')
    @enteza_json_endpoint
    def enviar(self, order_id, header=None, lines=None, customer_note=None, **kw):
        order = enteza_get_solicitud(order_id)
        payload = order.action_enteza_portal_submit(
            header=header, lines=lines, customer_note=customer_note)
        return {
            'ref': payload.get('ref'),
            'redirect': '/my/solicitud/%d/resumen' % order.id,
        }

    @route('/enteza_portal/solicitud/cancelar', type='jsonrpc', auth='user')
    @enteza_json_endpoint
    def cancelar(self, order_id, **kw):
        order = enteza_get_solicitud(order_id)
        return order.action_enteza_portal_cancel()
