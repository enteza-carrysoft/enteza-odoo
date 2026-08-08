"""Diálogo cliente ↔ comercial (PRP v2 §8, §11). No ejecutados: ver README del módulo.

🔴 `test_mensajes_portal_no_filtran_notas_internas` es CRÍTICO: sin el filtro por
`subtype_id.internal`, el cliente vería las notas internas que el comercial escribe en el
chatter para uso interno. Es el fallo de seguridad más fácil de cometer en este módulo.
"""
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDialogo(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1)
        cls.partner = cls.env['res.partner'].create({
            'name': 'Cliente diálogo (test)',
            'enteza_portal_pedidos_ok': True,
            'enteza_portal_warehouse_id': cls.warehouse.id,
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Silla diálogo (test)', 'type': 'consu', 'rent_ok': True,
        })
        cls.comercial = cls.env['res.users'].create({
            'name': 'Comercial diálogo (test)',
            'login': 'enteza_test_comercial_dialogo',
            'email': 'comercial.dialogo.test@example.com',
        })

    def _solicitud_enviada(self):
        pedido = self.env['sale.order']._enteza_portal_get_or_create(self.partner)
        pedido.user_id = self.comercial
        pedido.write({
            'event_date': '2026-09-12',
            'rental_start_date': '2026-09-11 08:00:00',
            'rental_return_date': '2026-09-13 18:00:00',
        })
        pedido.action_enteza_portal_submit(
            lines=[{'product_id': self.product.id, 'qty': 5}])
        return pedido

    # ------------------------------------------------------------------

    def test_mensajes_portal_no_filtran_notas_internas(self):
        """🔴 CRÍTICO: una nota interna del comercial NO puede llegar al portal."""
        pedido = self._solicitud_enviada()
        pedido.message_post(
            body='Nota interna: revisar el crédito antes de confirmar.',
            subtype_xmlid='mail.mt_note')
        pedido.message_post(
            body='Hola, ya estamos revisando tu solicitud.',
            subtype_xmlid='mail.mt_comment')

        mensajes = pedido._enteza_portal_mensajes()
        cuerpos = [m['body'] for m in mensajes]
        self.assertTrue(any('ya estamos revisando' in c for c in cuerpos))
        self.assertFalse(any('revisar el crédito' in c for c in cuerpos))

    def test_cliente_puede_escribir_mensaje(self):
        pedido = self._solicitud_enviada()
        pedido.action_enteza_portal_mensaje('¿Cuándo tendréis respuesta?')
        mensajes = pedido._enteza_portal_mensajes()
        self.assertTrue(any('¿Cuándo tendréis respuesta?' in m['body'] for m in mensajes))

    def test_mensaje_vacio_raises(self):
        pedido = self._solicitud_enviada()
        with self.assertRaises(UserError):
            pedido.action_enteza_portal_mensaje('   ')

    # ------------------------------------------------------------------

    def test_devolver_al_cliente(self):
        """`counter` → `composing`: la solicitud vuelve a ser editable (PRP v2 §8.1)."""
        pedido = self._solicitud_enviada()
        pedido.action_enteza_portal_tomar()
        pedido.action_enteza_portal_marcar_contrapropuesta()
        self.assertEqual(pedido.enteza_portal_state, 'counter')

        pedido.action_enteza_portal_devolver()
        self.assertEqual(pedido.enteza_portal_state, 'composing')

    def test_devolver_desde_composing_raises(self):
        pedido = self.env['sale.order']._enteza_portal_get_or_create(self.partner)
        with self.assertRaises(UserError):
            pedido.action_enteza_portal_devolver()

    # ------------------------------------------------------------------

    def test_pedir_cambios_vuelve_a_reviewing(self):
        pedido = self._solicitud_enviada()
        pedido.action_enteza_portal_tomar()
        pedido.action_enteza_portal_marcar_contrapropuesta()

        pedido.action_enteza_portal_pedir_cambios('Necesito 10 sillas más.')
        self.assertEqual(pedido.enteza_portal_state, 'reviewing')

    def test_pedir_cambios_fuera_de_counter_raises(self):
        pedido = self._solicitud_enviada()
        with self.assertRaises(UserError):
            pedido.action_enteza_portal_pedir_cambios('Algo')

    def test_pedir_cambios_sin_texto_raises(self):
        pedido = self._solicitud_enviada()
        pedido.action_enteza_portal_tomar()
        pedido.action_enteza_portal_marcar_contrapropuesta()
        with self.assertRaises(UserError):
            pedido.action_enteza_portal_pedir_cambios('')

    # ------------------------------------------------------------------

    def test_aceptar_fuera_de_counter_raises(self):
        pedido = self._solicitud_enviada()
        with self.assertRaises(UserError):
            pedido.action_enteza_portal_aceptar()

    def test_aceptar_no_confirma_el_pedido(self):
        """«Acepto» solo avisa al comercial de que puede preparar la firma; NO confirma
        el pedido -la firma sigue siendo la nativa del presupuesto (PRP v2 §8.1)."""
        pedido = self._solicitud_enviada()
        pedido.action_enteza_portal_tomar()
        pedido.action_enteza_portal_marcar_contrapropuesta()

        pedido.action_enteza_portal_aceptar()
        self.assertEqual(pedido.enteza_portal_state, 'counter')
        self.assertEqual(pedido.state, 'draft')
