"""Flujo de envío de la solicitud (PRP §4.1, §15).

⚠️ No ejecutados: este hosting no da acceso a `odoo-bin --test-enable` (ver README del
módulo). Documentan el comportamiento esperado y están validados por sintaxis, no por
ejecución.
"""
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSubmitFlow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({
            'name': 'Cliente de prueba portal',
            'enteza_portal_pedidos_ok': True,
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Silla de prueba',
            'type': 'consu',
            'rent_ok': True,
            'is_storable': True,
            'list_price': 2.5,
        })

    def _pedido_composing(self):
        return self.env['sale.order']._enteza_portal_get_or_create(self.partner)

    def test_get_or_create_returns_the_same_solicitud(self):
        """Una sola solicitud en composición por cliente a la vez (PRP §5)."""
        primero = self._pedido_composing()
        segundo = self._pedido_composing()
        self.assertEqual(primero.id, segundo.id)
        self.assertEqual(primero.enteza_portal_state, 'composing')

    def test_submit_without_dates_raises(self):
        pedido = self._pedido_composing()
        pedido._enteza_portal_actualizar_lineas(
            [{'product_id': self.product.id, 'qty': 10}])
        with self.assertRaises(UserError):
            pedido.action_enteza_portal_submit()

    def test_submit_without_lines_raises(self):
        pedido = self._pedido_composing()
        pedido.write({
            'event_date': '2026-09-12',
            'rental_start_date': '2026-09-11 08:00:00',
            'rental_return_date': '2026-09-13 18:00:00',
        })
        with self.assertRaises(UserError):
            pedido.action_enteza_portal_submit()

    def test_submit_with_box_violation_raises_and_lists_it(self):
        caja_25 = self.env['uom.uom'].create({
            'name': 'CAJA 25 UDS (test submit)',
            'relative_factor': 25,
            'relative_uom_id': self.product.uom_id.id,
        })
        self.product.product_tmpl_id.uom_ids = [(6, 0, [caja_25.id])]

        pedido = self._pedido_composing()
        pedido.write({
            'event_date': '2026-09-12',
            'rental_start_date': '2026-09-11 08:00:00',
            'rental_return_date': '2026-09-13 18:00:00',
        })
        pedido._enteza_portal_actualizar_lineas(
            [{'product_id': self.product.id, 'qty': 90}])  # no es múltiplo de 25

        with self.assertRaises(UserError) as contexto:
            pedido.action_enteza_portal_submit()
        self.assertIn('75', str(contexto.exception))
        self.assertIn('100', str(contexto.exception))

    def test_submit_success(self):
        pedido = self._pedido_composing()
        pedido.write({
            'event_date': '2026-09-12',
            'rental_start_date': '2026-09-11 08:00:00',
            'rental_return_date': '2026-09-13 18:00:00',
        })
        pedido._enteza_portal_actualizar_lineas(
            [{'product_id': self.product.id, 'qty': 10}])

        pedido.action_enteza_portal_submit(customer_note='Para la boda de septiembre')

        self.assertEqual(pedido.enteza_portal_state, 'submitted')
        self.assertTrue(pedido.enteza_portal_ref)
        self.assertTrue(pedido.enteza_portal_ref.startswith('SOL/'))
        self.assertTrue(pedido.enteza_portal_snapshot)
        self.assertEqual(len(pedido.enteza_portal_snapshot['lines']), 1)
        self.assertEqual(pedido.enteza_portal_customer_note, 'Para la boda de septiembre')

    def test_submit_is_idempotent(self):
        """Un doble clic del cliente no debe duplicar la referencia ni fallar (PRP §4.1)."""
        pedido = self._pedido_composing()
        pedido.write({
            'event_date': '2026-09-12',
            'rental_start_date': '2026-09-11 08:00:00',
            'rental_return_date': '2026-09-13 18:00:00',
        })
        pedido._enteza_portal_actualizar_lineas(
            [{'product_id': self.product.id, 'qty': 10}])
        pedido.action_enteza_portal_submit()
        referencia = pedido.enteza_portal_ref

        pedido.action_enteza_portal_submit()  # segundo envío, no debe romper nada
        self.assertEqual(pedido.enteza_portal_ref, referencia)
        self.assertEqual(pedido.enteza_portal_state, 'submitted')

    def test_take_and_counter_propose_flow(self):
        pedido = self._pedido_composing()
        pedido.write({
            'event_date': '2026-09-12',
            'rental_start_date': '2026-09-11 08:00:00',
            'rental_return_date': '2026-09-13 18:00:00',
        })
        pedido._enteza_portal_actualizar_lineas(
            [{'product_id': self.product.id, 'qty': 10}])
        pedido.action_enteza_portal_submit()

        pedido.action_enteza_portal_tomar()
        self.assertEqual(pedido.enteza_portal_state, 'reviewing')
        self.assertEqual(pedido.user_id, self.env.user)

        pedido.action_enteza_portal_marcar_contrapropuesta()
        self.assertEqual(pedido.enteza_portal_state, 'counter')

        with self.assertRaises(UserError):
            # Ya no está en 'reviewing': no se puede volver a marcar.
            pedido.action_enteza_portal_marcar_contrapropuesta()
