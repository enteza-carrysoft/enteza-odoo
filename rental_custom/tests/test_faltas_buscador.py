"""«Registrar faltas» con muchas líneas (19.0.1.17.0).

Spec `specs/004-faltas-buscador-ordenado`. Aquí solo lo que vive en el servidor: el orden de
las líneas, la referencia, la vista sin paginación y que las faltas de todas las líneas se
facturan. El buscador, el filtro y el teclado son del cliente web y se comprueban en pantalla.
"""

from datetime import timedelta

from lxml import etree

from odoo import Command, fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestFaltasBuscador(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente faltas buscador'})
        producto = cls.env['product.product']
        datos = {'is_storable': True, 'rent_ok': True, 'lst_price': 1.0}
        cls.mesa = producto.create({**datos, 'name': 'Mesa (buscador)', 'default_code': '9803'})
        cls.silla = producto.create({**datos, 'name': 'Silla (buscador)', 'default_code': '0412'})
        cls.vaso = producto.create({**datos, 'name': 'Vaso (buscador)', 'default_code': '4681'})
        cls.atril = producto.create({**datos, 'name': 'Atril sin código (buscador)'})
        cls.banco = producto.create({**datos, 'name': 'Banco sin código (buscador)'})

    def _alquiler(self, productos):
        desde = fields.Datetime.now() - timedelta(days=3)
        pedido = self.env['sale.order'].with_context(in_rental_app=True).create({
            'partner_id': self.cliente.id,
            'event_date': fields.Date.today() - timedelta(days=2),
            'rental_start_date': desde,
            'rental_return_date': desde + timedelta(days=1),
            'order_line': [
                Command.create({'product_id': p.id, 'product_uom_qty': 10}) for p in productos
            ],
        })
        pedido.action_confirm()
        pedido.picking_ids.filtered(
            lambda p: p.state not in ('done', 'cancel')
        ).action_cancel()
        return pedido

    def _asistente(self, pedido):
        accion = pedido.action_open_missing_wizard()
        return self.env['rental.missing.wizard'].browse(accion['res_id'])

    # AC1 --------------------------------------------------------------

    def test_lineas_en_el_orden_del_pedido(self):
        """19.0.1.17.1: mismo orden que el pedido impreso, no por referencia."""
        productos = [self.banco, self.vaso, self.mesa, self.atril, self.silla, self.vaso]
        pedido = self._alquiler(productos)
        asistente = self._asistente(pedido)
        self.assertEqual(
            asistente.line_ids.mapped('product_id').ids,
            [p.id for p in productos],
        )
        self.assertEqual(asistente.line_ids.mapped('sale_line_id'),
                         pedido.order_line.filtered('is_rental'))

    # AC2 --------------------------------------------------------------

    def test_referencia_en_linea(self):
        asistente = self._asistente(self._alquiler([self.mesa, self.atril]))
        self.assertEqual(asistente.line_ids.mapped('default_code'), ['9803', False])

    # AC3 --------------------------------------------------------------

    def test_vista_sin_paginacion(self):
        vista = self.env.ref('rental_custom.rental_missing_wizard_view_form')
        arch = etree.fromstring(vista.arch)
        campo = arch.xpath("//field[@name='line_ids']")[0]
        self.assertEqual(campo.get('widget'), 'rental_missing_lines')
        lista = campo.xpath('./list')[0]
        self.assertGreaterEqual(int(lista.get('limit')), 500)
        self.assertTrue(lista.xpath("./field[@name='default_code']"))

    # AC9 --------------------------------------------------------------

    def test_faltas_en_todas_las_lineas_se_facturan(self):
        """Las filas ocultas por el filtro siguen en el asistente: todas viajan al facturar."""
        pedido = self._alquiler([self.mesa, self.silla, self.vaso])
        asistente = self._asistente(pedido)
        asistente.line_ids.filtered(lambda l: l.product_id == self.silla).qty_missing = 2
        asistente.line_ids.filtered(lambda l: l.product_id == self.mesa).qty_missing = 1
        asistente.action_confirm()

        faltas = pedido.compensation_order_ids
        self.assertEqual(len(faltas), 1)
        cantidades = {l.product_id: l.product_uom_qty for l in faltas.order_line}
        self.assertEqual(cantidades, {self.silla: 2, self.mesa: 1})
