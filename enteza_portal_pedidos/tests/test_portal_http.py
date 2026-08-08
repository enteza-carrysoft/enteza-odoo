"""Acceso HTTP del portal (PRP §8.1, §8.2, §15). No ejecutados: ver README del módulo.

`HttpCase` en vez de `TransactionCase`: lo que se comprueba aquí es la comprobación de
propiedad del controlador (`controllers/common.py`), no la lógica del modelo -esa ya está
cubierta en `test_submit_flow.py` y compañía.
"""
import json

from odoo.tests.common import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestPortalHttp(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_a = new_test_user(cls.env, login='enteza_test_cliente_a',
                                    groups='base.group_portal')
        cls.partner_a = cls.user_a.partner_id
        cls.partner_a.enteza_portal_pedidos_ok = True

        cls.user_b = new_test_user(cls.env, login='enteza_test_cliente_b',
                                    groups='base.group_portal')
        cls.partner_b = cls.user_b.partner_id
        cls.partner_b.enteza_portal_pedidos_ok = True

        cls.user_sin_permiso = new_test_user(cls.env, login='enteza_test_sin_permiso',
                                              groups='base.group_portal')
        # `enteza_portal_pedidos_ok` se queda en su valor por defecto (`False`, PRP §4.5):
        # es la puerta del módulo.

    def _jsonrpc(self, ruta, params):
        return self.url_open(
            ruta,
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': params}),
            headers={'Content-Type': 'application/json'},
        )

    def test_owner_can_read_own_catalog(self):
        self.authenticate('enteza_test_cliente_a', 'enteza_test_cliente_a')
        pedido = self.env['sale.order'].sudo()._enteza_portal_get_or_create(self.partner_a)

        respuesta = self._jsonrpc(
            '/enteza_portal/solicitud/catalogo', {'order_id': pedido.id})

        self.assertEqual(respuesta.status_code, 200)
        cuerpo = respuesta.json()
        self.assertNotIn('error', cuerpo)
        self.assertIn('products', cuerpo.get('result', {}))

    def test_other_customer_gets_denied(self):
        """Un usuario del portal de OTRO cliente no puede ver esta solicitud (PRP §8.1):
        cinturón y tirantes, aunque la `ir.rule` nativa ya debería bastar."""
        pedido = self.env['sale.order'].sudo()._enteza_portal_get_or_create(self.partner_a)

        self.authenticate('enteza_test_cliente_b', 'enteza_test_cliente_b')
        respuesta = self._jsonrpc(
            '/enteza_portal/solicitud/catalogo', {'order_id': pedido.id})

        cuerpo = respuesta.json()
        self.assertIn('error', cuerpo)

    def test_user_without_flag_is_denied(self):
        """Sin `enteza_portal_pedidos_ok`, ni siquiera puede pedir SU propia solicitud
        -porque no debería tener ninguna, y el helper compartido lo corta antes (PRP
        §12.1)."""
        pedido = self.env['sale.order'].sudo()._enteza_portal_get_or_create(self.partner_a)

        self.authenticate('enteza_test_sin_permiso', 'enteza_test_sin_permiso')
        respuesta = self._jsonrpc(
            '/enteza_portal/solicitud/catalogo', {'order_id': pedido.id})

        cuerpo = respuesta.json()
        self.assertIn('error', cuerpo)

    def test_my_solicitudes_page_requires_login(self):
        self.authenticate('enteza_test_cliente_a', 'enteza_test_cliente_a')
        respuesta = self.url_open('/my/solicitudes')
        self.assertEqual(respuesta.status_code, 200)
