"""Envases en el portal (spec 005, AC15). Escritas SIN ejecutar: ver README del módulo."""
from odoo import Command
from odoo.exceptions import UserError
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

    def test_guardar_no_multiplo_rechazado(self):
        pedido = self.env['sale.order']._enteza_portal_get_or_create(self.partner)
        with self.assertRaises(UserError) as cm:
            pedido._enteza_portal_guardar(lines=[
                {'product_id': self.barco.id, 'qty': 30}])
        self.assertEqual(cm.exception.args[0], MSG_30)
        self.assertFalse(pedido.order_line.filtered('product_id'))

    def test_guardar_rechazo_no_borra_ni_modifica(self):
        pedido = self.env['sale.order']._enteza_portal_get_or_create(self.partner)
        pedido._enteza_portal_guardar(lines=[{'product_id': self.barco.id, 'qty': 50}])
        with self.assertRaises(UserError):
            pedido._enteza_portal_guardar(lines=[{'product_id': self.barco.id, 'qty': 30}])
        self.assertEqual(pedido.order_line.filtered('product_id').product_uom_qty, 50)

    def test_guardar_multiplo_aceptado(self):
        pedido = self.env['sale.order']._enteza_portal_get_or_create(self.partner)
        pedido._enteza_portal_guardar(lines=[{'product_id': self.barco.id, 'qty': 75}])
        self.assertEqual(pedido.order_line.filtered('product_id').product_uom_qty, 75)

    def test_repetir_omite_y_avisa(self):
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
        # El envase se asigna DESPUÉS: la línea de 30 queda fuera de regla.
        antiguo.product_tmpl_id.uom_ids = [Command.set([self.envase_25.id])]

        omitidas = []
        nueva = origen.action_enteza_portal_repetir(omitidas)
        lineas = nueva.order_line.filtered('product_id')
        self.assertEqual(lineas.product_id, self.barco)
        self.assertEqual(lineas.product_uom_qty, 50)
        self.assertEqual(omitidas, [
            "Plato antiguo (25): 30 uds no es múltiplo del envase de 25. "
            "Prueba con 25 o 50."])
