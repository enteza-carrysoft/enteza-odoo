"""API JSON del portal de pedidos (PRP §8.2).

🔴 `type='jsonrpc'`: en Odoo 19 es el nuevo nombre de lo que hasta la 18 era `type='json'`.
Con `type='json'` la ruta no se registra.

Todas comprueban propiedad con `enteza_get_solicitud` (PRP §8.1) antes de leer o escribir
nada, y el pedido que devuelve ya viene `sudo()`-ado: sin eso el grupo Portal no puede ni
leer el catálogo de producto (no tiene `ir.model.access` sobre `product.product`).
"""
from odoo import fields
from odoo.exceptions import UserError
from odoo.http import Controller, request, route

from .common import enteza_get_solicitud


class PortalPedidosAPI(Controller):

    def _stale(self, order, expected_write_date):
        """Bloqueo optimista (PRP §8.2): compara el `write_date` que el cliente tenía
        cuando pintó la pantalla con el actual. Si no coincide, alguien más escribió antes
        (otra pestaña, un doble envío) y hay que recargar en vez de pisarlo.
        """
        if not expected_write_date:
            return False
        return fields.Datetime.to_string(order.write_date) != expected_write_date

    # ------------------------------------------------------------------

    @route('/enteza_portal/solicitud/catalogo', type='jsonrpc', auth='user')
    def catalogo(self, order_id, **kw):
        order = enteza_get_solicitud(order_id)
        return order._enteza_portal_payload_catalogo()

    @route('/enteza_portal/solicitud/cabecera', type='jsonrpc', auth='user')
    def cabecera(self, order_id, event_date=None, pickup_date=None, return_date=None,
                 warehouse_id=None, expected_write_date=None, **kw):
        order = enteza_get_solicitud(order_id, requiere_composing=True)
        if self._stale(order, expected_write_date):
            return {'error': 'stale'}

        vals = {}
        if event_date is not None:
            vals['event_date'] = event_date
        if pickup_date is not None:
            vals['pickup_date'] = pickup_date
        if return_date is not None:
            vals['return_date'] = return_date
        if warehouse_id is not None:
            vals['warehouse_id'] = warehouse_id
        try:
            return order._enteza_portal_actualizar_cabecera(vals)
        except UserError as error:
            return {'error': str(error)}

    @route('/enteza_portal/solicitud/lineas', type='jsonrpc', auth='user')
    def lineas(self, order_id, changes=None, expected_write_date=None, **kw):
        order = enteza_get_solicitud(order_id, requiere_composing=True)
        if self._stale(order, expected_write_date):
            return {'error': 'stale'}
        try:
            return order._enteza_portal_actualizar_lineas(changes or [])
        except UserError as error:
            return {'error': str(error)}

    @route('/enteza_portal/solicitud/disponibilidad', type='jsonrpc', auth='user')
    def disponibilidad(self, order_id, product_ids=None, **kw):
        order = enteza_get_solicitud(order_id)
        return order._enteza_portal_disponibilidad(product_ids or [])

    @route('/enteza_portal/solicitud/enviar', type='jsonrpc', auth='user')
    def enviar(self, order_id, customer_note=None, expected_write_date=None, **kw):
        order = enteza_get_solicitud(order_id, requiere_composing=True)
        if self._stale(order, expected_write_date):
            return {'error': 'stale'}
        try:
            payload = order.action_enteza_portal_submit(customer_note=customer_note)
        except UserError as error:
            return {'error': str(error)}
        return {
            'ok': True,
            'ref': payload.get('ref'),
            'redirect': '/my/solicitud/%d/resumen' % order.id,
        }

    @route('/enteza_portal/solicitud/cancelar', type='jsonrpc', auth='user')
    def cancelar(self, order_id, **kw):
        order = enteza_get_solicitud(order_id, requiere_composing=True)
        try:
            return order.action_enteza_portal_cancel()
        except UserError as error:
            return {'error': str(error)}
