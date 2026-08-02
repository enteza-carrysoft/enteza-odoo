"""Casos límite del §12 del PRP que no caen en ningún otro fichero."""

from datetime import timedelta

from odoo import Command
from odoo.exceptions import UserError
from odoo.fields import Datetime
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCasosLimite(TransactionCase):

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
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente Test'})
        cls.desde = Datetime.now() + timedelta(days=10)
        cls.hasta = Datetime.now() + timedelta(days=12)

    def _dar_stock(self, cantidad, almacen):
        quant = self.env['stock.quant'].with_company(almacen.company_id).create({
            'product_id': self.producto.id,
            'inventory_quantity': cantidad,
            'location_id': almacen.lot_stock_id.id,
        })
        quant.action_apply_inventory()

    def _confirmar_con_prestamo(self, cantidad=95):
        pedido = self.env['sale.order'].with_context(in_rental_app=True).create({
            'partner_id': self.cliente.id,
            'rental_start_date': self.desde,
            'rental_return_date': self.hasta,
            'order_line': [Command.create({
                'product_id': self.producto.id, 'product_uom_qty': cantidad,
            })],
        })
        accion = pedido.action_confirm()
        self.env['enteza.prestamo.confirm'].browse(accion['res_id']).action_confirmar()
        return pedido

    def _validar(self, albaran):
        for movimiento in albaran.move_ids:
            movimiento.quantity = movimiento.product_uom_qty
        albaran.picked = True
        albaran._action_done()

    # ------------------------------------------------------------------
    # Caso 2: cambio de fechas de un pedido confirmado
    # ------------------------------------------------------------------

    def test_cambiar_fechas_con_el_prestamo_reservado_mueve_la_reserva(self):
        self._dar_stock(80, self.almacen)
        self._dar_stock(100, self.almacen_otra)
        pedido = self._confirmar_con_prestamo()
        prestamo = self.env['enteza.stock.loan'].search([])
        nuevo_inicio = self.desde + timedelta(days=5)

        pedido.order_line.write({
            'start_date': nuevo_inicio,
            'return_date': self.hasta + timedelta(days=5),
        })

        self.assertEqual(prestamo.line_ids.date_from, nuevo_inicio)
        self.assertEqual(
            prestamo.date_transfer, (nuevo_inicio - timedelta(days=3)).date(),
        )

    def test_cambiar_fechas_con_el_prestamo_aprobado_pide_revision(self):
        """Hay un viaje programado y puede haber albaranes impresos: no se toca solo."""
        self._dar_stock(80, self.almacen)
        self._dar_stock(100, self.almacen_otra)
        pedido = self._confirmar_con_prestamo()
        prestamo = self.env['enteza.stock.loan'].search([])
        prestamo.action_aprobar()
        fecha_original = prestamo.date_transfer

        pedido.order_line.write({'start_date': self.desde + timedelta(days=5)})

        self.assertTrue(prestamo.revision_pendiente)
        self.assertEqual(prestamo.date_transfer, fecha_original, 'No se mueve solo')

    # ------------------------------------------------------------------
    # Caso 3: material que no vuelve
    # ------------------------------------------------------------------

    def test_cerrar_con_diferencia_deja_rastro(self):
        self._dar_stock(80, self.almacen)
        self._dar_stock(100, self.almacen_otra)
        self._confirmar_con_prestamo()
        prestamo = self.env['enteza.stock.loan'].search([])
        prestamo.action_aprobar()
        self._validar(prestamo.picking_out_id)
        self._validar(prestamo.picking_in_id)

        prestamo.action_cerrar_con_diferencia()

        self.assertEqual(prestamo.state, 'returned')
        self.assertTrue(prestamo.revision_pendiente)
        self.assertIn('15', prestamo.revision_motivo)
        self.assertTrue(prestamo.notes, 'Tiene que quedar anotado quién lo decidió')

    def test_no_se_cierra_con_diferencia_lo_que_no_ha_salido(self):
        self._dar_stock(80, self.almacen)
        self._dar_stock(100, self.almacen_otra)
        self._confirmar_con_prestamo()
        prestamo = self.env['enteza.stock.loan'].search([])

        with self.assertRaises(UserError):
            prestamo.action_cerrar_con_diferencia()

    # ------------------------------------------------------------------
    # Caso 12: reserva huérfana
    # ------------------------------------------------------------------

    def test_el_analisis_detecta_una_reserva_huerfana(self):
        """Si la liberación al cancelar fallara, el material se quedaría inmovilizado.

        No se libera automáticamente: se marca. Deshacer una reserva por si acaso es peor
        que enseñarla.
        """
        self._dar_stock(80, self.almacen)
        self._dar_stock(100, self.almacen_otra)
        pedido = self._confirmar_con_prestamo()
        prestamo = self.env['enteza.stock.loan'].search([])

        # Se escribe el estado directamente para saltarse `_action_cancel` y su liberación:
        # simula justo el fallo que esta red tiene que recoger.
        pedido.write({'state': 'cancel'})
        self.assertTrue(prestamo.line_ids, 'La reserva sigue ahí')

        self.env['enteza.stock.deficit']._marcar_reservas_huerfanas()

        self.assertTrue(prestamo.revision_pendiente)

    # ------------------------------------------------------------------
    # Caso 8: fechas con hora
    # ------------------------------------------------------------------

    def test_la_fecha_de_traslado_usa_la_zona_del_usuario(self):
        """Un alquiler que empieza de madrugada no puede adelantar el traslado un día.

        Los `Datetime` de Odoo son UTC: en España, las 00:30 del sábado están guardadas como
        las 22:30 del viernes. Quedarse con la fecha en crudo programaría el porte un día
        antes de lo que ve el almacén.
        """
        Prestamo = self.env['enteza.stock.loan']
        madrugada = Datetime.to_datetime('2026-08-14 22:30:00')  # 15/08 00:30 en Madrid

        fecha = Prestamo.with_context(tz='Europe/Madrid')._fecha_traslado_de(madrugada)

        self.assertEqual(str(fecha), '2026-08-12', 'El 15 menos 3 días, no el 14')
