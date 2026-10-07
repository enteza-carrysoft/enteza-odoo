"""«Registrar faltas» desde el pedido de alquiler, sin albarán de recogida (19.0.1.16.0).

Spec `specs/002-faltas-desde-pedido`. Las pruebas no dependen de cómo esté «Traslado de
alquiler»: tras confirmar se cancelan los albaranes que haya, que es la situación en la que se
ofrece el botón en los dos modos.
"""

from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestFaltasDesdePedido(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente faltas pedido'})
        cls.vaso = cls.env['product.product'].create({
            'name': 'Vaso (faltas pedido)', 'is_storable': True, 'rent_ok': True,
            'lst_price': 2.0,
        })
        cls.servicio = cls.env['product.product'].create({
            'name': 'Precio por plaza (faltas pedido)', 'type': 'service', 'rent_ok': True,
        })
        cls.comercial = new_test_user(
            cls.env, login='comercial_faltas_pedido',
            groups='base.group_user,sales_team.group_sale_salesman',
        )

    def _alquiler(self, cantidad=100):
        desde = fields.Datetime.now() - timedelta(days=3)
        pedido = self.env['sale.order'].with_context(in_rental_app=True).create({
            'partner_id': self.cliente.id,
            'event_date': fields.Date.today() - timedelta(days=2),
            'rental_start_date': desde,
            'rental_return_date': desde + timedelta(days=1),
            'order_line': [
                Command.create({'product_id': self.vaso.id, 'product_uom_qty': cantidad}),
                Command.create({'product_id': self.servicio.id, 'product_uom_qty': 1}),
            ],
        })
        pedido.action_confirm()
        pedido.picking_ids.filtered(
            lambda p: p.state not in ('done', 'cancel')
        ).action_cancel()
        return pedido

    def _asistente(self, pedido, faltas=0.0, usuario=None):
        accion = pedido.with_user(usuario or self.env.user).action_open_missing_wizard()
        asistente = self.env['rental.missing.wizard'].with_user(
            usuario or self.env.user
        ).browse(accion['res_id'])
        asistente.line_ids.qty_missing = faltas
        return asistente

    # AC1 --------------------------------------------------------------

    def test_boton_solo_sin_albaranes_abiertos(self):
        pedido = self._alquiler()
        self.assertTrue(pedido.missing_from_order_allowed)

        abierto = self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_out').id,
            'location_id': self.env.ref('stock.stock_location_stock').id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            'sale_id': pedido.id,
        })
        pedido.invalidate_recordset(['missing_from_order_allowed'])
        self.assertFalse(pedido.missing_from_order_allowed)
        with self.assertRaises(UserError):
            pedido.action_open_missing_wizard()

        abierto.action_cancel()
        pedido.invalidate_recordset(['missing_from_order_allowed'])
        self.assertTrue(pedido.missing_from_order_allowed)

    # AC2 --------------------------------------------------------------

    def test_asistente_lista_lineas_de_material(self):
        asistente = self._asistente(self._alquiler(100))
        self.assertEqual(asistente.line_ids.product_id, self.vaso)
        self.assertEqual(asistente.line_ids.qty_rented, 100)
        self.assertEqual(asistente.line_ids.qty_missing, 0)

    # AC3 --------------------------------------------------------------

    def test_facturar_faltas_crea_el_mismo_pedido(self):
        pedido = self._alquiler(100)
        accion = self._asistente(pedido, 5).action_confirm()

        faltas = self.env['sale.order'].browse(accion['res_id'])
        self.assertEqual(faltas.state, 'draft')
        self.assertEqual(faltas.partner_id, pedido.partner_invoice_id)
        self.assertEqual(faltas.company_id, pedido.company_id)
        self.assertEqual(faltas.origin, pedido.name)
        self.assertEqual(faltas.rental_order_id, pedido)
        self.assertEqual(faltas.event_date, pedido.event_date)
        self.assertFalse(faltas.is_rental_order)
        self.assertFalse(faltas.missing_from_rental_location)
        self.assertTrue(faltas.missing_auto_validate)
        self.assertEqual(faltas.order_line.product_id, self.vaso)
        self.assertEqual(faltas.order_line.product_uom_qty, 5)
        self.assertFalse(faltas.order_line.is_rental)
        self.assertIn(faltas, pedido.compensation_order_ids)

    # AC4 --------------------------------------------------------------

    def test_faltas_acumulan_y_no_superan_lo_alquilado(self):
        pedido = self._alquiler(10)
        linea = pedido.order_line.filtered(lambda l: l.product_id == self.vaso)

        self._asistente(pedido, 4).action_confirm()
        self._asistente(pedido, 3).action_confirm()
        self.assertEqual(linea.qty_lost, 7)

        antes = self.env['sale.order'].search_count([('rental_order_id', '=', pedido.id)])
        with self.assertRaises(UserError):
            self._asistente(pedido, 4).action_confirm()
        self.assertEqual(linea.qty_lost, 7)
        self.assertEqual(
            self.env['sale.order'].search_count([('rental_order_id', '=', pedido.id)]), antes,
        )

    # AC5 --------------------------------------------------------------

    def test_sin_faltas_solo_marca_devuelto(self):
        pedido = self._alquiler(10)
        accion = self._asistente(pedido, 0).action_confirm()

        self.assertEqual(accion['type'], 'ir.actions.act_window_close')
        self.assertFalse(pedido.compensation_order_ids)
        self.assertEqual(pedido.rental_status, 'returned')

    def test_con_faltas_marca_devuelto(self):
        pedido = self._alquiler(10)
        self._asistente(pedido, 2).action_confirm()

        for linea in pedido.order_line.filtered('is_rental'):
            self.assertEqual(linea.qty_delivered, linea.product_uom_qty)
            self.assertEqual(linea.qty_returned, linea.product_uom_qty)
        self.assertEqual(pedido.rental_status, 'returned')

    def test_aviso_ignora_faltas_canceladas(self):
        """Spec 003: un pedido de faltas cancelado deja de contar en el aviso del alquiler."""
        pedido = self._alquiler(10)
        primero = self.env['sale.order'].browse(
            self._asistente(pedido, 2).action_confirm()['res_id'])
        segundo = self.env['sale.order'].browse(
            self._asistente(pedido, 1).action_confirm()['res_id'])
        self.assertEqual(pedido.compensation_order_ids, primero | segundo)

        primero.action_cancel()
        pedido.invalidate_recordset(['compensation_order_ids'])
        self.assertEqual(pedido.compensation_order_ids, segundo)
        self.assertEqual(primero.rental_order_id, pedido, 'el enlace se conserva')

        segundo.action_cancel()
        pedido.invalidate_recordset(['compensation_order_ids'])
        self.assertFalse(pedido.compensation_order_ids)

    # AC6 --------------------------------------------------------------

    def test_confirmar_faltas_valida_la_salida(self):
        """Lo confirma un comercial sin permisos de almacén: la baja se hace igual."""
        pedido = self._alquiler(10)
        accion = self._asistente(pedido, 3).action_confirm()
        faltas = self.env['sale.order'].browse(accion['res_id'])

        faltas.with_user(self.comercial).action_confirm()

        salidas = faltas.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing')
        self.assertTrue(salidas)
        self.assertEqual(set(salidas.mapped('state')), {'done'})
        self.assertEqual(sum(salidas.move_ids.mapped('quantity')), 3)

    def test_faltas_desde_albaran_no_se_validan_solas(self):
        """El camino del albarán sigue como antes: la salida queda pendiente."""
        faltas = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'order_line': [Command.create({'product_id': self.vaso.id,
                                           'product_uom_qty': 2, 'is_rental': False})],
        })
        self.assertFalse(faltas.missing_auto_validate)
        faltas.action_confirm()
        self.assertTrue(faltas.picking_ids)
        self.assertNotIn('done', faltas.picking_ids.mapped('state'))

    # AC9 --------------------------------------------------------------

    def test_usuario_sin_ventas_no_accede(self):
        interno = new_test_user(self.env, login='interno_sin_ventas_faltas',
                                groups='base.group_user')
        with self.assertRaises(AccessError):
            self.env['rental.missing.wizard'].with_user(interno).create({
                'order_id': self._alquiler(1).id,
            })
