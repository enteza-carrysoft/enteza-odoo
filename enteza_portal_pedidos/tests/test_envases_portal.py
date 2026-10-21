"""Envases en el portal (spec 005, AC15; spec 006: solo avisan, no bloquean). Escritas SIN ejecutar: ver README del módulo."""
from odoo import Command
from odoo.tests.common import TransactionCase, tagged

MSG_30 = "BOL BARCO (25): 30 uds no es múltiplo del envase de 25. Prueba con 25 o 50."


@tagged('post_install', '-at_install')
class TestEnvasesPortal(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1)
        cls.unidad = cls.env.ref('uom.product_uom_unit')
        cls.envase_25 = cls.env['uom.uom'].create({
            'name': 'Envase de 25 (portal test)', 'relative_uom_id': cls.unidad.id,
            'relative_factor': 25})
        cls.barco = cls._producto("BOL BARCO (25)", [cls.envase_25])
        cls.partner = cls.env['res.partner'].create({
            'name': 'Cliente envases portal (test)',
            'enteza_portal_pedidos_ok': True,
            'enteza_portal_warehouse_id': cls.warehouse.id,
        })

    @classmethod
    def _producto(cls, nombre, envases):
        plantilla = cls.env['product.template'].create({
            'name': nombre, 'type': 'consu', 'rent_ok': True,
            'uom_id': cls.unidad.id,
            'uom_ids': [Command.set([e.id for e in envases])],
        })
        return plantilla.product_variant_id

    def test_guardar_no_multiplo_guarda_y_avisa(self):
        """AC5: se guarda lo tecleado y se devuelve el aviso (texto del backend)."""
        pedido = self.env['sale.order']._enteza_portal_get_or_create(self.partner)
        resultado = pedido._enteza_portal_guardar(lines=[
            {'product_id': self.barco.id, 'qty': 30}])
        self.assertEqual(pedido.order_line.filtered('product_id').product_uom_qty, 30)
        self.assertIn(MSG_30, resultado['warnings'])
        self.assertEqual(len(resultado['box_warnings']), 1)

    def test_guardar_cambio_a_no_multiplo_modifica(self):
        pedido = self.env['sale.order']._enteza_portal_get_or_create(self.partner)
        pedido._enteza_portal_guardar(lines=[{'product_id': self.barco.id, 'qty': 50}])
        pedido._enteza_portal_guardar(lines=[{'product_id': self.barco.id, 'qty': 30}])
        self.assertEqual(pedido.order_line.filtered('product_id').product_uom_qty, 30)

    def test_create_api_no_multiplo(self):
        """Pedido creado por API con `order_line` (como la integración): sin error."""
        pedido = self.env['sale.order'].with_context(in_rental_app=True).create({
            'partner_id': self.partner.id,
            'warehouse_id': self.warehouse.id,
            'order_line': [Command.create({
                'product_id': self.barco.id, 'product_uom_qty': 30, 'is_rental': True})],
        })
        self.assertEqual(pedido.order_line.product_uom_qty, 30)

    def test_guardar_multiplo_aceptado(self):
        pedido = self.env['sale.order']._enteza_portal_get_or_create(self.partner)
        pedido._enteza_portal_guardar(lines=[{'product_id': self.barco.id, 'qty': 75}])
        self.assertEqual(pedido.order_line.filtered('product_id').product_uom_qty, 75)

    def test_repetir_copia_todo_y_avisa(self):
        """AC6: «Repetir pedido» copia todas las líneas y avisa de las no múltiplo."""
        antiguo = self._producto("Plato antiguo (25)", [])
        origen = self.env['sale.order'].with_context(in_rental_app=True).create({
            'partner_id': self.partner.id,
            'warehouse_id': self.warehouse.id,
            'is_rental_order': True,
            'event_date': '2026-08-01',
        })
        Linea = self.env['sale.order.line'].with_context(in_rental_app=True)
        Linea.create({'order_id': origen.id, 'product_id': self.barco.id,
                      'product_uom_qty': 50, 'is_rental': True})
        Linea.create({'order_id': origen.id, 'product_id': antiguo.id,
                      'product_uom_qty': 30, 'is_rental': True})
        # El envase se asigna DESPUÉS: la línea de 30 queda no múltiplo.
        antiguo.product_tmpl_id.uom_ids = [Command.set([self.envase_25.id])]

        omitidas, avisos = [], []
        nueva = origen.action_enteza_portal_repetir(omitidas, avisos)
        lineas = nueva.order_line.filtered('product_id')
        self.assertEqual(lineas.product_id, self.barco | antiguo)
        self.assertEqual(sorted(lineas.mapped('product_uom_qty')), [30, 50])
        self.assertFalse(omitidas)
        self.assertEqual(avisos, [
            "Plato antiguo (25): 30 uds no es múltiplo del envase de 25. "
            "Prueba con 25 o 50."])
