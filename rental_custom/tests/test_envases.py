"""Envases y múltiplos en las líneas de alquiler (19.0.1.19.0).

Spec `specs/005-envases-multiplos-alquiler`. Escritas SIN ejecutar: la instancia `enteza` es
producción, sin `odoo -u` ni `--test-enable`; solo validadas por sintaxis.
"""

from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import Form, new_test_user, tagged
from odoo.tests.common import TransactionCase

MSG_30 = "BOL BARCO (25): 30 uds no es múltiplo del envase de 25. Prueba con 25 o 50."


@tagged('post_install', '-at_install')
class TestEnvases(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente envases'})
        cls.unidad = cls.env.ref('uom.product_uom_unit')
        Uom = cls.env['uom.uom']
        cls.envase_25 = Uom.create({
            'name': 'Envase de 25 (test)', 'relative_uom_id': cls.unidad.id,
            'relative_factor': 25})
        cls.envase_10 = Uom.create({
            'name': 'Envase de 10 (test)', 'relative_uom_id': cls.unidad.id,
            'relative_factor': 10})
        cls.envase_1 = Uom.create({
            'name': 'Envase de 1 (test)', 'relative_uom_id': cls.unidad.id,
            'relative_factor': 1})
        cls.envase_medio = Uom.create({
            'name': 'Envase de 0,5 (test)', 'relative_uom_id': cls.unidad.id,
            'relative_factor': 0.5})
        cls.docena_otra_ref = Uom.create({
            'name': 'Envase de 12 sobre 25 (test)',
            'relative_uom_id': cls.envase_25.id, 'relative_factor': 12})
        cls.barco = cls._producto("BOL BARCO (25)", [cls.envase_25])
        cls.sin_envase = cls._producto("Silla suelta", [])

    @classmethod
    def _producto(cls, nombre, envases):
        plantilla = cls.env['product.template'].create({
            'name': nombre, 'type': 'consu', 'rent_ok': True, 'is_storable': True,
            'uom_id': cls.unidad.id, 'list_price': 2.0,
            'uom_ids': [Command.set([e.id for e in envases])],
        })
        return plantilla.product_variant_id

    def _alquiler(self, lineas=(), extra=None):
        """Pedido de alquiler en borrador; `lineas` = [(producto, cantidad)]."""
        desde = fields.Datetime.now() + timedelta(days=3)
        vals = {
            'partner_id': self.cliente.id,
            'event_date': fields.Date.today() + timedelta(days=4),
            'rental_start_date': desde,
            'rental_return_date': desde + timedelta(days=1),
            'order_line': [
                Command.create({
                    'product_id': p.id, 'product_uom_qty': q, 'is_rental': True})
                for p, q in lineas],
        }
        vals.update(extra or {})
        return self.env['sale.order'].with_context(in_rental_app=True).create(vals)

    def _linea(self, pedido, producto, qty, **extra):
        vals = {'order_id': pedido.id, 'product_id': producto.id,
                'product_uom_qty': qty, 'is_rental': True}
        vals.update(extra)
        return self.env['sale.order.line'].with_context(in_rental_app=True).create(vals)

    def _linea_antigua(self, qty):
        """Línea de `qty` uds creada ANTES de asignar el envase (queda fuera de regla)."""
        producto = self._producto("Plato antiguo (25)", [])
        pedido = self._alquiler([(producto, qty)])
        producto.product_tmpl_id.uom_ids = [Command.set([self.envase_25.id])]
        return pedido, pedido.order_line, producto

    # AC1 / AC2 ----------------------------------------------------------

    def test_count_multiplo_y_decimal(self):
        pedido = self._alquiler([(self.barco, 50)])
        self.assertEqual(pedido.order_line.enteza_envase_count, 2)
        _pedido, antigua, _producto = self._linea_antigua(30)
        self.assertEqual(antigua.enteza_envase_count, 1.2)
        cero = self._linea(pedido, self.barco, 0)
        self.assertFalse(cero.enteza_envase_count)
        seccion = self.env['sale.order.line'].create({
            'order_id': pedido.id, 'display_type': 'line_section', 'name': 'Sección'})
        nota = self.env['sale.order.line'].create({
            'order_id': pedido.id, 'display_type': 'line_note', 'name': 'Nota'})
        self.assertFalse(seccion.enteza_envase_count)
        self.assertFalse(nota.enteza_envase_count)

    def test_sin_envase(self):
        pedido = self._alquiler([(self.sin_envase, 30)])
        self.assertFalse(pedido.order_line.enteza_envase_count)
        self.assertEqual(pedido.order_line.product_uom_qty, 30)

    # AC3 / AC4 ----------------------------------------------------------

    def test_no_multiplo_rechazado(self):
        pedido = self._alquiler()
        with self.assertRaises(ValidationError) as cm:
            self._linea(pedido, self.barco, 30)
        self.assertEqual(cm.exception.args[0], MSG_30)
        # Cambiar la cantidad, el producto o la unidad de una línea válida.
        linea = self._linea(pedido, self.barco, 50)
        with self.assertRaises(ValidationError):
            linea.product_uom_qty = 30
        otra = self._linea(pedido, self.sin_envase, 30)
        with self.assertRaises(ValidationError):
            otra.product_id = self.barco
        con_unidad = self._linea(pedido, self.sin_envase, 50)
        with self.assertRaises(ValidationError):
            con_unidad.write({'product_id': self.barco.id, 'product_uom_qty': 30})
        # Precisión: 50,0000001 se acepta; el cero también; los negativos no.
        linea.product_uom_qty = 50.0000001
        linea.product_uom_qty = 0
        with self.assertRaises(ValidationError):
            linea.product_uom_qty = -25

    def test_proponer_solo_envase_si_menos_de_uno(self):
        mensaje = self.barco._enteza_envase_error_multiplo(10, self.unidad)
        self.assertIn("Prueba con 25.", mensaje)

    def test_multiplos_aceptados(self):
        pedido = self._alquiler()
        for qty in (25, 50, 75):
            linea = self._linea(pedido, self.barco, qty)
            linea.product_uom_qty = qty + 25
            self.assertEqual(linea.product_uom_qty, qty + 25)

    # AC5 / AC6 ----------------------------------------------------------

    def test_venta_normal_no_afectada(self):
        venta = self.env['sale.order'].create({'partner_id': self.cliente.id})
        linea = self.env['sale.order.line'].create({
            'order_id': venta.id, 'product_id': self.barco.id, 'product_uom_qty': 30,
            'is_rental': False})
        self.assertEqual(linea.product_uom_qty, 30)

    def test_pedido_faltas_exento(self):
        origen = self._alquiler([(self.barco, 50)])
        faltas = self.env['sale.order'].create({
            'partner_id': self.cliente.id, 'rental_order_id': origen.id})
        linea = self.env['sale.order.line'].create({
            'order_id': faltas.id, 'product_id': self.barco.id, 'product_uom_qty': 30,
            'is_rental': True})
        linea.write({'product_uom_qty': 31, 'is_rental': True})
        en_envase = self.env['sale.order.line'].create({
            'order_id': faltas.id, 'product_id': self.barco.id, 'product_uom_qty': 3,
            'product_uom_id': self.envase_25.id, 'is_rental': True})
        self.assertEqual(linea.product_uom_qty, 31)
        self.assertEqual(en_envase.product_uom_qty, 3)

    # AC7 ----------------------------------------------------------------

    def test_precio_por_unidad(self):
        pedido = self._alquiler([(self.barco, 50)])
        linea = pedido.order_line
        una = self.env['sale.order.line'].with_context(in_rental_app=True).new({
            'order_id': pedido.id, 'product_id': self.barco.id, 'product_uom_qty': 1,
            'is_rental': True})
        self.assertAlmostEqual(linea.price_unit, una.price_unit)
        self.assertAlmostEqual(linea.price_subtotal, 50 * linea.price_unit)

    # AC8 ----------------------------------------------------------------

    def test_etiqueta_parte_recogida(self):
        pedido = self._alquiler([(self.barco, 50), (self.sin_envase, 40)])
        con_envase, sin = pedido.order_line
        self.assertEqual(con_envase._enteza_envase_label(), "50 uds (2 envases de 25)")
        self.assertEqual(sin._enteza_envase_label(), "40 uds")
        self.assertEqual(self._linea(pedido, self.barco, 25)._enteza_envase_label(),
                         "25 uds (1 envase de 25)")
        _p, antigua, _prod = self._linea_antigua(30)
        self.assertEqual(antigua._enteza_envase_label(), "30 uds (1,2 envases de 25)")

    def test_parte_todas_las_lineas(self):
        pedido = self._alquiler([(self.barco, 50), (self.sin_envase, 40)])
        self.assertEqual(pedido._enteza_pickup_lines(), pedido.order_line)
        self.assertTrue(all(not l.qty_delivered for l in pedido.order_line))
        html, _tipo = self.env['ir.actions.report']._render_qweb_html(
            'sale_renting.report_rental_order', pedido.ids)
        texto = html.decode()
        self.assertIn("Pedido", texto)
        self.assertIn("50 uds (2 envases de 25)", texto)
        self.assertIn("40 uds", texto)

    # AC9 ----------------------------------------------------------------

    def test_columna_solo_en_alquiler(self):
        alquiler = self.env['sale.order'].get_view(
            self.env.ref('sale_renting.rental_order_primary_form_view').id, 'form')
        venta = self.env['sale.order'].get_view(
            self.env.ref('sale.view_order_form').id, 'form')
        self.assertIn('enteza_envase_count', alquiler['arch'])
        self.assertNotIn('enteza_envase_count', venta['arch'])

    # AC10 ---------------------------------------------------------------

    def test_campo_solo_lectura(self):
        campo = self.env['sale.order.line']._fields['enteza_envase_count']
        self.assertTrue(campo.compute)
        self.assertFalse(campo.store)
        self.assertFalse(campo.inverse)
        self.assertTrue(campo.readonly)
        pedido = self._alquiler([(self.barco, 50)])
        pedido.order_line.write({'enteza_envase_count': 7})
        self.assertEqual(pedido.order_line.product_uom_qty, 50)
        sin_derechos = new_test_user(
            self.env, login='sin_derechos_envases', groups='base.group_user')
        with self.assertRaises(AccessError):
            pedido.order_line.with_user(sin_derechos).write({'product_uom_qty': 75})

    # AC11 ---------------------------------------------------------------

    def test_unidad_distinta_rechazada(self):
        pedido = self._alquiler()
        with self.assertRaises(ValidationError) as cm:
            self._linea(pedido, self.barco, 2, product_uom_id=self.envase_25.id)
        self.assertIn("unidad base", cm.exception.args[0])
        linea = self._linea(pedido, self.barco, 50)
        with self.assertRaises(ValidationError):
            linea.product_uom_id = self.envase_25
        otra = self._linea(pedido, self.sin_envase, 3)
        with self.assertRaises(ValidationError):
            otra.write({'product_id': self.barco.id, 'product_uom_id': self.envase_25.id})

    def test_linea_antigua_en_otra_unidad_editable(self):
        producto = self._producto("Fuente antigua (25)", [])
        pedido = self._alquiler()
        antigua = self._linea(pedido, producto, 2, product_uom_id=self.envase_25.id)
        producto.product_tmpl_id.uom_ids = [Command.set([self.envase_25.id])]
        antigua.write({'price_unit': 3.0, 'name': 'Descripción nueva'})
        self.assertEqual(antigua.price_unit, 3.0)

    # AC12 ---------------------------------------------------------------

    def test_linea_antigua_editable(self):
        _pedido, antigua, _producto = self._linea_antigua(30)
        antigua.write({'price_unit': 5.0, 'name': 'Otro nombre', 'discount': 10.0})
        self.assertEqual(antigua.price_unit, 5.0)
        with self.assertRaises(ValidationError):
            antigua.product_uom_qty = 31
        antigua.product_uom_qty = 50
        self.assertEqual(antigua.product_uom_qty, 50)

    # AC13 ---------------------------------------------------------------

    def test_pedido_confirmado_fuera_de_regla(self):
        producto = self._producto("Cesta confirmada (25)", [])
        pedido = self._alquiler([(producto, 30)])
        pedido.action_confirm()
        producto.product_tmpl_id.uom_ids = [Command.set([self.envase_25.id])]
        pedido.order_line.qty_delivered = 30
        pedido._mark_rental_returned()
        pedido._create_invoices()
        self.assertEqual(pedido.order_line.product_uom_qty, 30)

    # AC14 ---------------------------------------------------------------

    def test_copy_rechazado(self):
        _pedido, antigua, producto = self._linea_antigua(30)
        with self.assertRaises(ValidationError) as cm:
            antigua.order_id.copy()
        self.assertEqual(
            cm.exception.args[0],
            "Plato antiguo (25): 30 uds no es múltiplo del envase de 25. Prueba con 25 o 50.")

    # AC16 ---------------------------------------------------------------

    def test_dos_envases_menor_factor(self):
        producto = self._producto("Bandeja doble", [self.envase_25, self.envase_10])
        pedido = self._alquiler([(producto, 30)])
        self.assertEqual(pedido.order_line.enteza_envase_count, 3)

    def test_envases_invalidos_ignorados(self):
        for envase in (self.envase_1, self.envase_medio, self.docena_otra_ref):
            producto = self._producto("Raro %s" % envase.name, [envase])
            self.assertFalse(producto._enteza_envase_uom())
            pedido = self._alquiler([(producto, 7)])
            self.assertFalse(pedido.order_line.enteza_envase_count)

    # AC17 ---------------------------------------------------------------

    def test_no_propone_envase(self):
        with Form(self.env['sale.order'].with_context(in_rental_app=True),
                  view='sale_renting.rental_order_primary_form_view') as form:
            form.partner_id = self.cliente
            form.event_date = fields.Date.today() + timedelta(days=4)
            with form.order_line.new() as linea:
                linea.product_id = self.barco
                linea.product_uom_qty = 50
                self.assertEqual(linea.product_uom_id, self.unidad)

    # AC18 ---------------------------------------------------------------

    def test_usuario_stileum(self):
        compania = self.env['res.company'].create({'name': 'Segunda sociedad (test)'})
        usuario = new_test_user(
            self.env, login='stileum_envases',
            groups='base.group_user,sales_team.group_sale_salesman',
            company_id=compania.id, company_ids=[Command.set([compania.id])])
        self.assertFalse(self.barco.company_id)
        env = self.env(user=usuario, context=dict(
            self.env.context, allowed_company_ids=[compania.id]))
        pedido = env['sale.order'].with_context(in_rental_app=True).create({
            'partner_id': self.cliente.id, 'company_id': compania.id})
        linea = env['sale.order.line'].with_context(in_rental_app=True).create({
            'order_id': pedido.id, 'product_id': self.barco.id, 'product_uom_qty': 50,
            'is_rental': True})
        self.assertEqual(linea.enteza_envase_count, 2)
