"""Flujo de envío de la solicitud (PRP §4.1, §15; PRP v2 §2.2, §11).

⚠️ No ejecutados: este hosting no da acceso a `odoo-bin --test-enable` (ver README del
módulo). Documentan el comportamiento esperado y están validados por sintaxis, no por
ejecución.

🔴 PRP v2: `_enteza_portal_actualizar_cabecera`/`_enteza_portal_actualizar_lineas` ya no
existen -sustituidos por `_enteza_portal_guardar`, que reconcilia el cesto COMPLETO en una
transacción-, y `action_enteza_portal_submit` ahora recibe `header`/`lines` y guarda+envía de
forma atómica en vez de depender de un guardado previo por separado.
"""
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSubmitFlow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1)
        cls.partner = cls.env['res.partner'].create({
            'name': 'Cliente de prueba portal',
            'enteza_portal_pedidos_ok': True,
            # D3 (PRP v2): sin almacén habitual, `_enteza_portal_get_or_create` ya no
            # asigna uno arbitrario -lo exige.
            'enteza_portal_warehouse_id': cls.warehouse.id,
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
        with self.assertRaises(UserError):
            pedido.action_enteza_portal_submit(
                lines=[{'product_id': self.product.id, 'qty': 10}])

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

        with self.assertRaises(UserError) as contexto:
            # No es múltiplo de 25: `_enteza_portal_guardar` la habría escrito igual (no
            # bloquea), pero `action_enteza_portal_submit` sí bloquea al enviar.
            pedido.action_enteza_portal_submit(
                lines=[{'product_id': self.product.id, 'qty': 90}])
        self.assertIn('75', str(contexto.exception))
        self.assertIn('100', str(contexto.exception))

    def test_submit_success(self):
        pedido = self._pedido_composing()
        pedido.write({
            'event_date': '2026-09-12',
            'rental_start_date': '2026-09-11 08:00:00',
            'rental_return_date': '2026-09-13 18:00:00',
        })
        pedido.action_enteza_portal_submit(
            lines=[{'product_id': self.product.id, 'qty': 10}],
            customer_note='Para la boda de septiembre')

        self.assertEqual(pedido.enteza_portal_state, 'submitted')
        self.assertTrue(pedido.enteza_portal_ref)
        self.assertTrue(pedido.enteza_portal_ref.startswith('SOL/'))
        self.assertTrue(pedido.enteza_portal_snapshot)
        self.assertEqual(len(pedido.enteza_portal_snapshot['lines']), 1)
        self.assertEqual(pedido.enteza_portal_customer_note, 'Para la boda de septiembre')
        # PRP v2 §5.9j: sin esto, ninguna respuesta del comercial en el chatter llega al
        # cliente -no queda como seguidor de su propio pedido.
        self.assertIn(self.partner, pedido.message_partner_ids)

    def test_submit_is_idempotent(self):
        """Un doble clic del cliente no debe duplicar la referencia ni fallar (PRP §4.1)."""
        pedido = self._pedido_composing()
        pedido.write({
            'event_date': '2026-09-12',
            'rental_start_date': '2026-09-11 08:00:00',
            'rental_return_date': '2026-09-13 18:00:00',
        })
        pedido.action_enteza_portal_submit(
            lines=[{'product_id': self.product.id, 'qty': 10}])
        referencia = pedido.enteza_portal_ref

        # Segundo envío, no debe romper nada ni repetir el trabajo -el pedido ya no está
        # en `composing`, así que `action_enteza_portal_submit` devuelve sin más.
        pedido.action_enteza_portal_submit(lines=[{'product_id': self.product.id, 'qty': 77}])
        self.assertEqual(pedido.enteza_portal_ref, referencia)
        self.assertEqual(pedido.enteza_portal_state, 'submitted')
        linea = pedido.order_line.filtered('product_id')
        self.assertEqual(linea.product_uom_qty, 10, "el segundo envío no debe tocar nada")

    def test_take_and_counter_propose_flow(self):
        pedido = self._pedido_composing()
        pedido.write({
            'event_date': '2026-09-12',
            'rental_start_date': '2026-09-11 08:00:00',
            'rental_return_date': '2026-09-13 18:00:00',
        })
        pedido.action_enteza_portal_submit(
            lines=[{'product_id': self.product.id, 'qty': 10}])

        pedido.action_enteza_portal_tomar()
        self.assertEqual(pedido.enteza_portal_state, 'reviewing')
        self.assertEqual(pedido.user_id, self.env.user)

        pedido.action_enteza_portal_marcar_contrapropuesta()
        self.assertEqual(pedido.enteza_portal_state, 'counter')

        with self.assertRaises(UserError):
            # Ya no está en 'reviewing': no se puede volver a marcar.
            pedido.action_enteza_portal_marcar_contrapropuesta()

    # ------------------------------------------------------------------
    # Guardado idempotente del cesto completo (PRP v2 §2.2, §9, §11) — F1
    # ------------------------------------------------------------------

    def test_guardar_idempotente(self):
        """Llamar dos veces con el mismo cesto deja el mismo resultado."""
        pedido = self._pedido_composing()
        cesto = [{'product_id': self.product.id, 'qty': 10}]
        pedido._enteza_portal_guardar(lines=cesto)
        n_lineas_1 = len(pedido.order_line.filtered('product_id'))
        total_1 = pedido.amount_total

        pedido._enteza_portal_guardar(lines=cesto)
        self.assertEqual(len(pedido.order_line.filtered('product_id')), n_lineas_1)
        self.assertEqual(pedido.amount_total, total_1)

    def test_guardar_borra_lo_que_falta(self):
        """El cesto es el estado COMPLETO, no un delta: un producto que desaparece del
        cesto pierde su línea."""
        otro_producto = self.env['product.product'].create({
            'name': 'Mesa de prueba (guardar)', 'type': 'consu', 'rent_ok': True,
        })
        pedido = self._pedido_composing()
        pedido._enteza_portal_guardar(lines=[
            {'product_id': self.product.id, 'qty': 5},
            {'product_id': otro_producto.id, 'qty': 3},
        ])
        self.assertEqual(len(pedido.order_line.filtered('product_id')), 2)

        pedido._enteza_portal_guardar(lines=[{'product_id': self.product.id, 'qty': 5}])
        lineas = pedido.order_line.filtered('product_id')
        self.assertEqual(len(lineas), 1)
        self.assertEqual(lineas.product_id, self.product)

    def test_guardar_ignora_producto_no_servido(self):
        """Un producto que no cumple el filtro del catálogo servido no entra nunca, y se
        avisa (nunca se acepta lo que el portal no serviría)."""
        no_servido = self.env['product.product'].create({
            'name': 'No servido (test)', 'type': 'consu', 'rent_ok': True,
            'enteza_portal_ok': False,
        })
        pedido = self._pedido_composing()
        resultado = pedido._enteza_portal_guardar(
            lines=[{'product_id': no_servido.id, 'qty': 5}])
        self.assertFalse(pedido.order_line.filtered('product_id'))
        self.assertTrue(resultado['warnings'])

    def test_enviar_es_atomico(self):
        """Si la validación de fechas falla al enviar, no queda ninguna solicitud "a
        medias enviada": ni referencia, ni `submitted_on`, y el estado sigue en
        `composing` -totalmente editable. El cesto sí se guarda (mismo comportamiento
        que un autoguardado normal): eso es deseable, no un fallo a medias."""
        pedido = self._pedido_composing()
        with self.assertRaises(UserError):
            pedido.action_enteza_portal_submit(
                lines=[{'product_id': self.product.id, 'qty': 10}])
        self.assertEqual(pedido.enteza_portal_state, 'composing')
        self.assertFalse(pedido.enteza_portal_ref)
        self.assertFalse(pedido.enteza_portal_submitted_on)

    def test_enviar_dos_veces_no_avanza_la_secuencia(self):
        pedido = self._pedido_composing()
        pedido.write({
            'event_date': '2026-09-12',
            'rental_start_date': '2026-09-11 08:00:00',
            'rental_return_date': '2026-09-13 18:00:00',
        })
        pedido.action_enteza_portal_submit(
            lines=[{'product_id': self.product.id, 'qty': 10}])
        referencia = pedido.enteza_portal_ref
        secuencia = self.env['ir.sequence'].search([('code', '=', 'enteza.portal.pedido')])
        numero_tras_primer_envio = secuencia.number_next_actual

        pedido.action_enteza_portal_submit(lines=[{'product_id': self.product.id, 'qty': 99}])
        self.assertEqual(pedido.enteza_portal_ref, referencia)
        self.assertEqual(secuencia.number_next_actual, numero_tras_primer_envio)
