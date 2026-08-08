"""Disponibilidad y semáforo (PRP §6, §15). No ejecutados: ver README del módulo.

Monta escenarios copiando el idioma de `sale_stock_renting/tests/test_rental.py`
(`with_context(in_rental_app=True)`, `stock.quant` + `action_apply_inventory()`), tal como
recomienda `references/convenciones-modulo.md` del skill `odoo19-dev`.
"""
from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAvailability(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1)
        cls.product = cls.env['product.product'].create({
            'name': 'Mesa de prueba disponibilidad',
            'type': 'consu',
            'is_storable': True,
            'rent_ok': True,
        })
        quant = cls.env['stock.quant'].create({
            'product_id': cls.product.id,
            'location_id': cls.warehouse.lot_stock_id.id,
            'inventory_quantity': 10,
        })
        quant.action_apply_inventory()

    def _crear_cliente_portal(self):
        return self.env['res.partner'].create({
            'name': 'Cliente disponibilidad',
            'enteza_portal_pedidos_ok': True,
        })

    def _crear_alquiler_confirmado(self, qty, desde, hasta):
        """Alquiler confirmado que compite por el mismo producto y fechas (PRP §6.1)."""
        pedido = self.env['sale.order'].with_context(in_rental_app=True).create({
            'partner_id': self.env['res.partner'].create({'name': 'Otro cliente'}).id,
            'warehouse_id': self.warehouse.id,
            'event_date': '2026-09-12',
            'rental_start_date': desde,
            'rental_return_date': hasta,
        })
        self.env['sale.order.line'].with_context(in_rental_app=True).create({
            'order_id': pedido.id,
            'product_id': self.product.id,
            'product_uom_qty': qty,
        })
        pedido.action_confirm()
        return pedido

    def test_full_availability_is_green(self):
        color = self.product._enteza_portal_semaforo(
            5,
            fields.Datetime.to_datetime('2026-09-11 08:00:00'),
            fields.Datetime.to_datetime('2026-09-13 18:00:00'),
            self.warehouse,
        )
        self.assertEqual(color, 'green')

    def test_partial_availability_is_amber(self):
        self._crear_alquiler_confirmado(7, '2026-09-11 08:00:00', '2026-09-13 18:00:00')
        color = self.product._enteza_portal_semaforo(
            5,
            fields.Datetime.to_datetime('2026-09-11 08:00:00'),
            fields.Datetime.to_datetime('2026-09-13 18:00:00'),
            self.warehouse,
        )
        self.assertEqual(color, 'amber')

    def test_no_availability_is_red(self):
        self._crear_alquiler_confirmado(10, '2026-09-11 08:00:00', '2026-09-13 18:00:00')
        color = self.product._enteza_portal_semaforo(
            1,
            fields.Datetime.to_datetime('2026-09-11 08:00:00'),
            fields.Datetime.to_datetime('2026-09-13 18:00:00'),
            self.warehouse,
        )
        self.assertEqual(color, 'red')

    def test_result_is_only_a_color_string(self):
        """El endpoint nunca devuelve la cantidad libre (PRP §6.3): solo el color."""
        partner = self._crear_cliente_portal()
        pedido = self.env['sale.order']._enteza_portal_get_or_create(partner)
        pedido.write({
            'warehouse_id': self.warehouse.id,
            'rental_start_date': '2026-09-11 08:00:00',
            'rental_return_date': '2026-09-13 18:00:00',
        })
        self.env.company.enteza_portal_semaforo = True

        resultado = pedido._enteza_portal_disponibilidad([self.product.id])
        self.assertIsInstance(resultado[self.product.id], str)
        self.assertIn(resultado[self.product.id], ('green', 'amber', 'red', 'grey'))

    def test_semaforo_off_returns_grey_without_computing(self):
        """`enteza_portal_semaforo=False` en compañía: `grey` para todo, sin consultar
        (PRP §6.2). Arranca en `False` a propósito mientras el inventario está a medio
        cargar."""
        partner = self._crear_cliente_portal()
        pedido = self.env['sale.order']._enteza_portal_get_or_create(partner)
        pedido.write({
            'warehouse_id': self.warehouse.id,
            'rental_start_date': '2026-09-11 08:00:00',
            'rental_return_date': '2026-09-13 18:00:00',
        })
        self.env.company.enteza_portal_semaforo = False

        resultado = pedido._enteza_portal_disponibilidad([self.product.id])
        self.assertEqual(resultado[self.product.id], 'grey')

    def test_non_storable_product_is_always_grey(self):
        servicio = self.env['product.product'].create({
            'name': 'Fianza de prueba', 'type': 'service', 'rent_ok': True,
        })
        color = servicio._enteza_portal_semaforo(
            1,
            fields.Datetime.to_datetime('2026-09-11 08:00:00'),
            fields.Datetime.to_datetime('2026-09-13 18:00:00'),
            self.warehouse,
        )
        self.assertEqual(color, 'grey')
