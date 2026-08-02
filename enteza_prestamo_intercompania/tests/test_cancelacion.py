"""Cancelar o reducir un pedido libera lo que tenía comprometido en el préstamo (§7.0.2).

Es la contrapartida obligatoria de haber juntado varios pedidos en un mismo viaje: sin esto,
cancelar un evento dejaba su material comprometido para siempre y, si el traslado ya estaba
aprobado, **viajaba igualmente**.
"""

from datetime import timedelta

from odoo import Command
from odoo.fields import Datetime
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCancelacionPrestamo(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.propia = cls.env.company
        cls.otra = cls.env['res.company'].create({'name': 'Prestamista Test'})
        cls.almacen = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.propia.id)], limit=1,
        )
        cls.almacen_otra = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.otra.id)], limit=1,
        )

        cls.producto = cls.env['product.product'].create({
            'name': 'Vaso maceta (test)',
            'uom_id': cls.env.ref('uom.product_uom_unit').id,
            'rent_ok': True, 'is_storable': True, 'company_id': False,
        })
        cls.producto_b = cls.env['product.product'].create({
            'name': 'Mesa plegable (test)',
            'uom_id': cls.env.ref('uom.product_uom_unit').id,
            'rent_ok': True, 'is_storable': True, 'company_id': False,
        })
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente Test'})

        cls.desde = Datetime.now() + timedelta(days=10)
        cls.hasta = Datetime.now() + timedelta(days=12)

    def _dar_stock(self, cantidad, almacen, producto=None):
        quant = self.env['stock.quant'].with_company(almacen.company_id).create({
            'product_id': (producto or self.producto).id,
            'inventory_quantity': cantidad,
            'location_id': almacen.lot_stock_id.id,
        })
        quant.action_apply_inventory()

    def _confirmar(self, cantidad, producto=None):
        pedido = self.env['sale.order'].with_context(in_rental_app=True).create({
            'partner_id': self.cliente.id,
            'rental_start_date': self.desde,
            'rental_return_date': self.hasta,
            'order_line': [Command.create({
                'product_id': (producto or self.producto).id,
                'product_uom_qty': cantidad,
            })],
        })
        accion = pedido.action_confirm()
        if isinstance(accion, dict):
            self.env['enteza.prestamo.confirm'].browse(
                accion['res_id']
            ).action_confirmar()
        return pedido

    def _escenario(self):
        self._dar_stock(80, self.almacen)
        self._dar_stock(100, self.almacen_otra)
        self._dar_stock(50, self.almacen_otra, self.producto_b)

    def _libre_en_prestamista(self, producto=None):
        motor = self.env['enteza.disponibilidad'].sudo()
        producto = producto or self.producto
        return motor.disponible(
            producto, self.almacen_otra, self.desde, self.hasta,
        )[producto.id]

    # ------------------------------------------------------------------
    # Cancelación
    # ------------------------------------------------------------------

    def test_cancelar_el_unico_pedido_cancela_el_prestamo(self):
        self._escenario()
        pedido = self._confirmar(95)
        prestamo = self.env['enteza.stock.loan'].search([])
        self.assertEqual(prestamo.state, 'reserved')
        self.assertEqual(self._libre_en_prestamista(), 85)

        pedido._action_cancel()

        self.assertEqual(prestamo.state, 'cancelled')
        self.assertFalse(prestamo.line_ids)
        self.assertEqual(self._libre_en_prestamista(), 100, 'El material vuelve a estar libre')

    def test_cancelar_un_pedido_de_varios_solo_retira_su_parte(self):
        """🔴 El caso que motivó todo esto: el viaje sigue, sin la carga cancelada."""
        self._escenario()
        primero = self._confirmar(95)
        segundo = self._confirmar(10, producto=self.producto_b)
        prestamo = self.env['enteza.stock.loan'].search([])
        self.assertEqual(len(prestamo.line_ids), 2)

        primero._action_cancel()

        self.assertEqual(prestamo.state, 'reserved', 'El préstamo sigue vivo')
        self.assertEqual(len(prestamo.line_ids), 1)
        self.assertEqual(prestamo.line_ids.product_id, self.producto_b)
        self.assertEqual(prestamo.origin_order_ids, segundo,
                         'El pedido cancelado deja de figurar como origen')
        self.assertEqual(self._libre_en_prestamista(), 100)
        self.assertEqual(self._libre_en_prestamista(self.producto_b), 40)

    def test_cancelar_con_el_prestamo_aprobado_ajusta_el_albaran(self):
        """§7.0.2: se ajustan los albaranes existentes, no se rehacen."""
        self._escenario()
        primero = self._confirmar(95)
        self._confirmar(10, producto=self.producto_b)
        prestamo = self.env['enteza.stock.loan'].search([])
        prestamo.action_aprobar()
        salida = prestamo.picking_out_id
        self.assertEqual(len(salida.move_ids), 2)

        primero._action_cancel()

        self.assertEqual(prestamo.picking_out_id, salida, 'El mismo albarán')
        vivos = salida.move_ids.filtered(lambda mov: mov.state != 'cancel')
        self.assertEqual(len(vivos), 1)
        self.assertEqual(vivos.product_id, self.producto_b)

    def test_cancelar_todo_con_el_prestamo_aprobado_cancela_los_albaranes(self):
        self._escenario()
        pedido = self._confirmar(95)
        prestamo = self.env['enteza.stock.loan'].search([])
        prestamo.action_aprobar()
        albaranes = prestamo.picking_out_id | prestamo.picking_in_id

        pedido._action_cancel()

        self.assertEqual(prestamo.state, 'cancelled')
        self.assertEqual(set(albaranes.mapped('state')), {'cancel'})

    # ------------------------------------------------------------------
    # Cuando ya no se puede deshacer
    # ------------------------------------------------------------------

    def test_si_el_material_ya_salio_se_marca_para_revision(self):
        """No se puede deshacer un movimiento validado desde aquí (§12, caso 11).

        Lo que no puede pasar es que nadie se entere: el préstamo queda marcado y sale en el
        filtro «Necesitan revisión».
        """
        self._escenario()
        pedido = self._confirmar(95)
        prestamo = self.env['enteza.stock.loan'].search([])
        prestamo.action_aprobar()
        salida = prestamo.picking_out_id
        for movimiento in salida.move_ids:
            movimiento.quantity = movimiento.product_uom_qty
        salida.picked = True
        salida._action_done()
        self.assertEqual(prestamo.state, 'in_transit')

        pedido._action_cancel()

        self.assertTrue(prestamo.revision_pendiente)
        self.assertTrue(prestamo.revision_motivo)
        self.assertEqual(prestamo.state, 'in_transit', 'No se toca lo ya movido')
        self.assertEqual(len(prestamo.line_ids), 1, 'La línea sigue: el material salió')

    # ------------------------------------------------------------------
    # Reducción
    # ------------------------------------------------------------------

    def test_reducir_la_cantidad_libera_la_parte_proporcional(self):
        self._escenario()
        pedido = self._confirmar(95)
        prestamo = self.env['enteza.stock.loan'].search([])
        self.assertEqual(prestamo.line_ids.qty_reserved, 15)

        pedido.order_line.product_uom_qty = 90

        self.assertEqual(prestamo.line_ids.qty_reserved, 10)
        self.assertEqual(self._libre_en_prestamista(), 90)

    def test_reducir_por_debajo_de_lo_prestado_cancela_el_prestamo(self):
        self._escenario()
        pedido = self._confirmar(95)
        prestamo = self.env['enteza.stock.loan'].search([])

        pedido.order_line.product_uom_qty = 80

        self.assertEqual(prestamo.state, 'cancelled')
        self.assertEqual(self._libre_en_prestamista(), 100)

    def test_ampliar_no_libera_nada(self):
        """Ampliar necesita volver a pasar por el diálogo, y eso todavía no está."""
        self._escenario()
        pedido = self._confirmar(95)
        prestamo = self.env['enteza.stock.loan'].search([])

        pedido.order_line.product_uom_qty = 120

        self.assertEqual(prestamo.line_ids.qty_reserved, 15, 'No se toca')
