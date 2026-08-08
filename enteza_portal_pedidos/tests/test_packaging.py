"""Cajas y múltiplos (PRP §7, §15). No ejecutados: ver README del módulo."""
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPackaging(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1)
        cls.uom_unidades = cls.env.ref('uom.product_uom_unit')
        cls.caja_25 = cls.env['uom.uom'].create({
            'name': 'CAJA 25 UDS (test)',
            'relative_factor': 25,
            'relative_uom_id': cls.uom_unidades.id,
        })
        cls.producto_con_caja = cls.env['product.template'].create({
            'name': 'Plato de prueba',
            'type': 'consu',
            'rent_ok': True,
            'uom_id': cls.uom_unidades.id,
            'uom_ids': [(6, 0, [cls.caja_25.id])],
        })
        cls.producto_sin_caja = cls.env['product.template'].create({
            'name': 'Silla suelta de prueba',
            'type': 'consu',
            'rent_ok': True,
            'uom_id': cls.uom_unidades.id,
        })

    def test_compute_box_from_packaging(self):
        """`enteza_units_per_box`/`enteza_box_uom_id` derivan de `uom_ids` (PRP §2.6, §4.3):
        no hay ningún dato nuevo que cargar aparte del packaging nativo ya existente."""
        self.assertEqual(self.producto_con_caja.enteza_units_per_box, 25)
        self.assertEqual(self.producto_con_caja.enteza_box_uom_id, self.caja_25)

    def test_no_packaging_means_no_box(self):
        self.assertEqual(self.producto_sin_caja.enteza_units_per_box, 0)
        self.assertFalse(self.producto_sin_caja.enteza_box_uom_id)

    def test_exact_multiple_is_valid(self):
        aviso = self.env['sale.order']._enteza_portal_check_multiplo(
            self.producto_con_caja.product_variant_id, 100)
        self.assertIsNone(aviso)

    def test_non_multiple_proposes_two_roundings(self):
        aviso = self.env['sale.order']._enteza_portal_check_multiplo(
            self.producto_con_caja.product_variant_id, 90)
        self.assertIsNotNone(aviso)
        self.assertEqual(aviso['round_down'], 75)
        self.assertEqual(aviso['round_up'], 100)

    def test_less_than_one_box_rounds_down_to_zero(self):
        """Menos de una caja: la propuesta «abajo» es 0 = quitar la línea (PRP §7)."""
        aviso = self.env['sale.order']._enteza_portal_check_multiplo(
            self.producto_con_caja.product_variant_id, 10)
        self.assertIsNotNone(aviso)
        self.assertEqual(aviso['round_down'], 0)
        self.assertEqual(aviso['round_up'], 25)

    def test_product_without_box_accepts_any_qty(self):
        """Sin packaging no se aplica ninguna restricción de múltiplo (PRP §2.6)."""
        aviso = self.env['sale.order']._enteza_portal_check_multiplo(
            self.producto_sin_caja.product_variant_id, 7)
        self.assertIsNone(aviso)

    def test_lines_update_reports_warning_without_blocking(self):
        """`guardar` avisa del múltiplo pero SÍ guarda la cantidad tal cual (PRP §7): el
        servidor no redondea por su cuenta, solo avisa. El bloqueo real es al enviar
        (PRP v2: sustituye a `_enteza_portal_actualizar_lineas`)."""
        partner = self.env['res.partner'].create({
            'name': 'Cliente packaging',
            'enteza_portal_pedidos_ok': True,
            'enteza_portal_warehouse_id': self.warehouse.id,
        })
        pedido = self.env['sale.order']._enteza_portal_get_or_create(partner)
        resultado = pedido._enteza_portal_guardar(lines=[
            {'product_id': self.producto_con_caja.product_variant_id.id, 'qty': 90},
        ])
        self.assertEqual(len(resultado['box_warnings']), 1)
        self.assertEqual(resultado['box_warnings'][0]['round_down'], 75)
        linea = pedido.order_line.filtered(
            lambda l: l.product_id == self.producto_con_caja.product_variant_id)
        self.assertEqual(linea.product_uom_qty, 90)
