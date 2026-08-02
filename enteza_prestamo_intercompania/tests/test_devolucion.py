"""Devolución inteligente: cuánto vuelve y cuánto se queda (PRP §7.5).

La regla en una línea: no devolver material que la receptora va a volver a necesitar en la
ventana de retención, porque sería un viaje de ida y otro de vuelta para nada.
"""

from datetime import timedelta

from odoo import Command
from odoo.exceptions import UserError
from odoo.fields import Datetime
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDevolucionPrestamo(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.receptora = cls.env.company
        cls.prestamista = cls.env['res.company'].create({'name': 'Prestamista Test'})
        cls.almacen_dest = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.receptora.id)], limit=1,
        )
        cls.almacen_src = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.prestamista.id)], limit=1,
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

    def _validar(self, albaran):
        for movimiento in albaran.move_ids:
            movimiento.quantity = movimiento.product_uom_qty
        albaran.picked = True
        albaran._action_done()

    def _prestamo_entregado(self, cantidad=100):
        """Un préstamo con el material ya en el almacén de la receptora."""
        self._dar_stock(cantidad, self.almacen_src)
        prestamo = self.env['enteza.stock.loan'].create({
            'company_id': self.prestamista.id,
            'company_dest_id': self.receptora.id,
            'warehouse_src_id': self.almacen_src.id,
            'warehouse_dest_id': self.almacen_dest.id,
            'line_ids': [Command.create({
                'product_id': self.producto.id,
                'product_uom_id': self.producto.uom_id.id,
                'qty_proposed': cantidad,
                'date_from': self.desde,
                'date_to': self.hasta,
            })],
        })
        prestamo.action_reservar()
        prestamo.action_aprobar()
        self._validar(prestamo.picking_out_id)
        self._validar(prestamo.picking_in_id)
        self.assertEqual(prestamo.state, 'lent')
        return prestamo

    def _pedido_receptora(self, cantidad, dentro_de_dias=3):
        """Demanda de la receptora dentro de la ventana de retención."""
        inicio = Datetime.now() + timedelta(days=dentro_de_dias)
        pedido = self.env['sale.order'].with_context(in_rental_app=True).create({
            'partner_id': self.cliente.id,
            'rental_start_date': inicio,
            'rental_return_date': inicio + timedelta(days=1),
            'order_line': [Command.create({
                'product_id': self.producto.id,
                'product_uom_qty': cantidad,
            })],
        })
        pedido.with_context(enteza_prestamo_aceptado=True).action_confirm()
        return pedido

    # ------------------------------------------------------------------
    # El cálculo
    # ------------------------------------------------------------------

    def test_sin_demanda_se_devuelve_todo(self):
        prestamo = self._prestamo_entregado(100)

        datos = prestamo.line_ids._calcular_devolucion()

        self.assertEqual(datos['pendiente'], 100)
        self.assertEqual(datos['retener'], 0)
        self.assertEqual(datos['devolver'], 100)

    def test_el_ejemplo_del_cliente(self):
        """Prestadas 100, necesita 30 y no le llega con lo suyo → retiene 30, devuelve 70."""
        prestamo = self._prestamo_entregado(100)
        self._pedido_receptora(30)

        datos = prestamo.line_ids._calcular_devolucion()

        self.assertEqual(datos['necesita_receptora'], 30)
        self.assertEqual(datos['propio_receptora'], 0, 'Todo lo que tiene es prestado')
        self.assertEqual(datos['retener'], 30)
        self.assertEqual(datos['devolver'], 70)

    def test_si_la_receptora_se_defiende_sola_no_retiene(self):
        """Con material propio suficiente, lo prestado vuelve entero."""
        prestamo = self._prestamo_entregado(100)
        self._dar_stock(50, self.almacen_dest)
        self._pedido_receptora(30)

        datos = prestamo.line_ids._calcular_devolucion()

        self.assertEqual(datos['propio_receptora'], 50)
        self.assertEqual(datos['retener'], 0, 'Se apaña con lo suyo')
        self.assertEqual(datos['devolver'], 100)

    def test_la_necesidad_de_la_prestamista_manda(self):
        """🔴 `[PENDIENTE-5]`: es su material, su necesidad vence a la retención."""
        prestamo = self._prestamo_entregado(100)
        self._pedido_receptora(30)

        # La prestamista se queda sin nada y necesita 20 en la misma ventana.
        inicio = Datetime.now() + timedelta(days=3)
        pedido = self.env['sale.order'].with_context(in_rental_app=True).create({
            'partner_id': self.cliente.id,
            'company_id': self.prestamista.id,
            'warehouse_id': self.almacen_src.id,
            'rental_start_date': inicio,
            'rental_return_date': inicio + timedelta(days=1),
            'order_line': [Command.create({
                'product_id': self.producto.id, 'product_uom_qty': 20,
            })],
        })
        pedido.with_context(enteza_prestamo_aceptado=True).action_confirm()

        datos = prestamo.line_ids._calcular_devolucion()

        self.assertEqual(datos['necesita_prestamista'], 20)
        self.assertEqual(datos['retener'], 10, 'De las 30 que quería retener, cede 20')
        self.assertEqual(datos['devolver'], 90)

    # ------------------------------------------------------------------
    # El circuito
    # ------------------------------------------------------------------

    def test_el_asistente_solo_propone(self):
        prestamo = self._prestamo_entregado(100)
        self._pedido_receptora(30)

        accion = prestamo.action_proponer_devolucion()
        asistente = self.env['enteza.prestamo.devolucion'].browse(accion['res_id'])

        self.assertEqual(asistente.line_ids.qty_devolver, 70)
        self.assertEqual(asistente.line_ids.qty_retener, 30)
        # Abrirlo no mueve nada.
        self.assertEqual(prestamo.state, 'lent')
        self.assertFalse(prestamo.return_picking_ids)

    def test_devolver_genera_el_par_de_albaranes_al_reves(self):
        prestamo = self._prestamo_entregado(100)
        accion = prestamo.action_proponer_devolucion()
        asistente = self.env['enteza.prestamo.devolucion'].browse(accion['res_id'])

        asistente.action_devolver()

        albaranes = prestamo.return_picking_ids
        self.assertEqual(len(albaranes), 2)
        transito = self.env['enteza.stock.loan']._ubicacion_transito()
        salida = albaranes.filtered(lambda alb: alb.company_id == self.receptora)
        entrada = albaranes.filtered(lambda alb: alb.company_id == self.prestamista)
        self.assertEqual(salida.location_id, self.almacen_dest.lot_stock_id)
        self.assertEqual(salida.location_dest_id, transito)
        self.assertEqual(entrada.location_id, transito)
        self.assertEqual(entrada.location_dest_id, self.almacen_src.lot_stock_id)

    def test_devolucion_parcial_deja_el_prestamo_a_medias(self):
        prestamo = self._prestamo_entregado(100)
        accion = prestamo.action_proponer_devolucion()
        asistente = self.env['enteza.prestamo.devolucion'].browse(accion['res_id'])
        asistente.line_ids.qty_devolver = 70
        asistente.action_devolver()

        for albaran in prestamo.return_picking_ids.sorted('id'):
            self._validar(albaran)

        self.assertEqual(prestamo.line_ids.qty_returned, 70)
        self.assertEqual(prestamo.line_ids.qty_pending, 30)
        self.assertEqual(prestamo.state, 'partially_returned')
        self.assertEqual(prestamo.qty_pendiente_devolver, 30)

    def test_devolver_el_resto_cierra_el_prestamo(self):
        prestamo = self._prestamo_entregado(100)
        for cantidad in (70, 30):
            accion = prestamo.action_proponer_devolucion()
            asistente = self.env['enteza.prestamo.devolucion'].browse(accion['res_id'])
            asistente.line_ids.qty_devolver = cantidad
            asistente.action_devolver()
            for albaran in prestamo.return_picking_ids.filtered(
                lambda alb: alb.state not in ('done', 'cancel')
            ).sorted('id'):
                self._validar(albaran)

        self.assertEqual(prestamo.line_ids.qty_pending, 0)
        self.assertEqual(prestamo.state, 'returned')

    def test_el_material_vuelve_al_almacen_de_quien_lo_presto(self):
        prestamo = self._prestamo_entregado(100)
        accion = prestamo.action_proponer_devolucion()
        self.env['enteza.prestamo.devolucion'].browse(
            accion['res_id']
        ).action_devolver()
        for albaran in prestamo.return_picking_ids.sorted('id'):
            self._validar(albaran)

        en_origen = self.producto.with_company(self.prestamista).with_context(
            warehouse_id=self.almacen_src.id,
        ).qty_available
        self.assertEqual(en_origen, 100)

    # ------------------------------------------------------------------
    # Guardas
    # ------------------------------------------------------------------

    def test_no_se_propone_devolucion_de_lo_que_no_ha_salido(self):
        self._dar_stock(100, self.almacen_src)
        prestamo = self.env['enteza.stock.loan'].create({
            'company_id': self.prestamista.id,
            'company_dest_id': self.receptora.id,
            'warehouse_src_id': self.almacen_src.id,
            'warehouse_dest_id': self.almacen_dest.id,
            'line_ids': [Command.create({
                'product_id': self.producto.id,
                'product_uom_id': self.producto.uom_id.id,
                'qty_proposed': 10,
                'date_from': self.desde,
                'date_to': self.hasta,
            })],
        })
        prestamo.action_reservar()

        with self.assertRaises(UserError):
            prestamo.action_proponer_devolucion()

    def test_no_se_puede_devolver_mas_de_lo_pendiente(self):
        prestamo = self._prestamo_entregado(100)
        accion = prestamo.action_proponer_devolucion()
        asistente = self.env['enteza.prestamo.devolucion'].browse(accion['res_id'])
        asistente.line_ids.qty_devolver = 150

        with self.assertRaises(UserError):
            asistente.action_devolver()
