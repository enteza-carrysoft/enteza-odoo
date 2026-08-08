"""Fechas derivadas (D2) y almacén fijo del cliente (D3) — PRP v2 §5.9f, §7, §11.

No ejecutados: ver README del módulo. Los métodos privados de `sale_stock_renting`
(`_get_unavailable_qty`, `_get_virtual_unavailable_qty_in_rent`) no se pueden llamar por
RPC, así que no se han podido confirmar aquí contra `enteza26` -sólo por lectura del código
de Enterprise 18, como el resto del módulo.
"""
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestFechasYAlmacen(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1)
        cls.partner = cls.env['res.partner'].create({
            'name': 'Cliente fechas (test)',
            'enteza_portal_pedidos_ok': True,
            'enteza_portal_warehouse_id': cls.warehouse.id,
        })

    # ------------------------------------------------------------------
    # D2: fecha única, entrega/retirada derivadas
    # ------------------------------------------------------------------

    def test_fechas_derivadas_de_event_date(self):
        """Entrega = evento - 1 día, retirada = evento + 1 día (mismo criterio que
        `rental_custom.event_date_change` en el backend, PRP v2 D2)."""
        pedido = self.env['sale.order']._enteza_portal_get_or_create(self.partner)
        pedido._enteza_portal_guardar(header={'event_date': '2026-09-15'})
        self.assertEqual(str(pedido.event_date), '2026-09-15')
        self.assertEqual(
            pedido._enteza_portal_fecha_local(pedido.rental_start_date), '2026-09-14')
        self.assertEqual(
            pedido._enteza_portal_fecha_local(pedido.rental_return_date), '2026-09-16')

    def test_fechas_ajustadas_a_mano_prevalecen(self):
        """El cliente puede ajustar entrega/retirada a mano («ajustar» en la interfaz)."""
        pedido = self.env['sale.order']._enteza_portal_get_or_create(self.partner)
        pedido._enteza_portal_guardar(header={
            'event_date': '2026-09-15',
            'pickup_date': '2026-09-10',
            'return_date': '2026-09-20',
        })
        self.assertEqual(
            pedido._enteza_portal_fecha_local(pedido.rental_start_date), '2026-09-10')
        self.assertEqual(
            pedido._enteza_portal_fecha_local(pedido.rental_return_date), '2026-09-20')

    def test_volver_a_automatico_sin_overrides_recalcula(self):
        """Sin `pickup_date`/`return_date` en el `header`, se recalculan del evento -es
        cómo el botón «usar fechas automáticas» resetea un ajuste manual anterior."""
        pedido = self.env['sale.order']._enteza_portal_get_or_create(self.partner)
        pedido._enteza_portal_guardar(header={
            'event_date': '2026-09-15',
            'pickup_date': '2026-09-10',
            'return_date': '2026-09-20',
        })
        pedido._enteza_portal_guardar(header={'event_date': '2026-09-15'})
        self.assertEqual(
            pedido._enteza_portal_fecha_local(pedido.rental_start_date), '2026-09-14')
        self.assertEqual(
            pedido._enteza_portal_fecha_local(pedido.rental_return_date), '2026-09-16')

    def test_evento_fuera_del_periodo_ajustado_raises(self):
        pedido = self.env['sale.order']._enteza_portal_get_or_create(self.partner)
        with self.assertRaises(UserError):
            pedido._enteza_portal_guardar(header={
                'event_date': '2026-09-15',
                'pickup_date': '2026-09-16',
                'return_date': '2026-09-20',
            })

    def test_entrega_posterior_a_retirada_raises(self):
        pedido = self.env['sale.order']._enteza_portal_get_or_create(self.partner)
        with self.assertRaises(UserError):
            pedido._enteza_portal_guardar(header={
                'event_date': '2026-09-15',
                'pickup_date': '2026-09-20',
                'return_date': '2026-09-10',
            })

    def test_antelacion_insuficiente_avisa_sin_bloquear(self):
        """La antelación mínima (`enteza_portal_dias_minimos`, por defecto 2) es
        orientativa: avisa, no bloquea -mismo criterio que el semáforo (PRP §6.4)."""
        pedido = self.env['sale.order']._enteza_portal_get_or_create(self.partner)
        cerca = fields.Date.to_string(fields.Date.today() + timedelta(days=1))
        resultado = pedido._enteza_portal_guardar(header={'event_date': cerca})
        self.assertTrue(resultado['warnings'])
        self.assertEqual(pedido.enteza_portal_state, 'composing')

    def test_fecha_entrega_hora_local(self):
        """PRP v2 §5.9f: no se deja que Odoo complete el `Datetime` con `00:00 UTC` -esa
        hora no significa nada real. Se escribe con hora de negocio (08:00 locales para la
        entrega) convertida desde la zona del usuario."""
        self.env.user.tz = 'Europe/Madrid'
        pedido = self.env['sale.order']._enteza_portal_get_or_create(self.partner)
        pedido._enteza_portal_guardar(header={'event_date': '2026-09-15'})
        # 08:00 en España en septiembre (verano, UTC+2) son las 06:00 UTC.
        self.assertEqual(str(pedido.rental_start_date)[11:16], '06:00')

    # ------------------------------------------------------------------
    # D3: almacén fijo del cliente
    # ------------------------------------------------------------------

    def test_sin_almacen_no_crea_solicitud_huerfana(self):
        """Sin `enteza_portal_warehouse_id` en la ficha, `_enteza_portal_get_or_create` ya
        no elige un almacén arbitrario entre Vimaple y Stileum -eso lo comprueba el
        controlador ANTES de llamar aquí (`controllers/portal.py`). Este test documenta
        que, si algo se salta esa comprobación, falla alto y claro en vez de mezclar
        compañías en silencio."""
        partner_sin_almacen = self.env['res.partner'].create({
            'name': 'Cliente sin almacén (test)', 'enteza_portal_pedidos_ok': True,
        })
        with self.assertRaises(Exception):
            self.env['sale.order']._enteza_portal_get_or_create(partner_sin_almacen)

    # ------------------------------------------------------------------
    # Repetir un pedido anterior no duplica la solicitud en composición (PRP v2 §5.7/F3)
    # ------------------------------------------------------------------

    def test_repetir_no_duplica_composing(self):
        producto = self.env['product.product'].create({
            'name': 'Mesa repetir (test)', 'type': 'consu', 'rent_ok': True,
        })
        origen = self.env['sale.order'].with_context(in_rental_app=True).create({
            'partner_id': self.partner.id,
            'warehouse_id': self.warehouse.id,
            'is_rental_order': True,
            'event_date': '2026-08-01',
        })
        self.env['sale.order.line'].with_context(in_rental_app=True).create({
            'order_id': origen.id, 'product_id': producto.id, 'product_uom_qty': 4,
            'is_rental': True,
        })

        en_composicion = self.env['sale.order']._enteza_portal_get_or_create(self.partner)
        en_composicion._enteza_portal_guardar(
            lines=[{'product_id': producto.id, 'qty': 1}])

        dominio_composing = [
            ('partner_id', '=', self.partner.id),
            ('enteza_portal_state', '=', 'composing'),
        ]
        self.assertEqual(self.env['sale.order'].search_count(dominio_composing), 1)

        resultado = origen.action_enteza_portal_repetir()
        self.assertEqual(resultado.id, en_composicion.id,
                          "debe reutilizar la solicitud en composición, no crear otra")
        self.assertEqual(self.env['sale.order'].search_count(dominio_composing), 1)

        lineas = resultado.order_line.filtered('product_id')
        self.assertEqual(len(lineas), 1)
        self.assertEqual(lineas.product_uom_qty, 4, "reemplazada por la del pedido origen")
