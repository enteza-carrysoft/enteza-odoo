"""Pruebas del traslado de ida: los dos albaranes vía tránsito (PRP §6.1 y §7.4)."""

from datetime import timedelta

from odoo import Command
from odoo.fields import Datetime
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAlbaranesPrestamo(TransactionCase):

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
            'rent_ok': True,
            'is_storable': True,
            'company_id': False,
        })

        cls.desde = Datetime.now() + timedelta(days=10)
        cls.hasta = Datetime.now() + timedelta(days=12)

    def _dar_stock(self, cantidad, almacen):
        quant = self.env['stock.quant'].with_company(almacen.company_id).create({
            'product_id': self.producto.id,
            'inventory_quantity': cantidad,
            'location_id': almacen.lot_stock_id.id,
        })
        quant.action_apply_inventory()

    def _prestamo(self, cantidad=15):
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
        return prestamo

    def _validar(self, albaran):
        for movimiento in albaran.move_ids:
            movimiento.quantity = movimiento.product_uom_qty
        albaran.picked = True
        albaran._action_done()

    # ------------------------------------------------------------------
    # Infraestructura
    # ------------------------------------------------------------------

    def test_la_ubicacion_de_transito_es_usable(self):
        """Sin `company_id` vacío, la mitad del flujo falla con un error de acceso."""
        transito = self.env['enteza.stock.loan']._ubicacion_transito()

        self.assertEqual(transito.usage, 'transit')
        self.assertFalse(transito.company_id, 'Tiene que estar SIN compañía')
        self.assertTrue(transito.active)

    def test_los_tipos_de_operacion_se_crean_solos(self):
        """No se reutilizan los OUT/IN de cliente: ensuciarían el reparto diario."""
        salida = self.almacen_src._enteza_tipo_prestamo(True)
        entrada = self.almacen_dest._enteza_tipo_prestamo(False)
        transito = self.env['enteza.stock.loan']._ubicacion_transito()

        self.assertEqual(salida.code, 'outgoing')
        self.assertEqual(salida.warehouse_id, self.almacen_src)
        self.assertEqual(salida.default_location_src_id, self.almacen_src.lot_stock_id)
        self.assertEqual(salida.default_location_dest_id, transito)

        self.assertEqual(entrada.code, 'incoming')
        self.assertEqual(entrada.default_location_src_id, transito)
        self.assertEqual(entrada.default_location_dest_id, self.almacen_dest.lot_stock_id)

        # Segunda llamada: no se crea otro.
        self.assertEqual(self.almacen_src._enteza_tipo_prestamo(True), salida)

    # ------------------------------------------------------------------
    # Aprobar genera el doble albarán
    # ------------------------------------------------------------------

    def test_aprobar_genera_los_dos_albaranes(self):
        self._dar_stock(100, self.almacen_src)
        prestamo = self._prestamo(15)
        prestamo.action_aprobar()

        transito = self.env['enteza.stock.loan']._ubicacion_transito()
        self.assertTrue(prestamo.picking_out_id)
        self.assertTrue(prestamo.picking_in_id)

        salida = prestamo.picking_out_id
        self.assertEqual(salida.company_id, self.prestamista)
        self.assertEqual(salida.location_id, self.almacen_src.lot_stock_id)
        self.assertEqual(salida.location_dest_id, transito)
        self.assertEqual(salida.move_ids.product_uom_qty, 15)

        entrada = prestamo.picking_in_id
        self.assertEqual(entrada.company_id, self.receptora)
        self.assertEqual(entrada.location_id, transito)
        self.assertEqual(entrada.location_dest_id, self.almacen_dest.lot_stock_id)
        self.assertEqual(entrada.move_ids.product_uom_qty, 15)

    def test_los_movimientos_apuntan_a_su_linea(self):
        """Emparejar por producto mezclaría dos líneas del mismo artículo."""
        self._dar_stock(100, self.almacen_src)
        prestamo = self._prestamo(15)
        prestamo.action_aprobar()

        self.assertEqual(
            prestamo.picking_out_id.move_ids.enteza_loan_line_id, prestamo.line_ids,
        )

    # ------------------------------------------------------------------
    # El estado lo mueve el hecho físico
    # ------------------------------------------------------------------

    def test_validar_la_salida_pone_el_prestamo_en_transito(self):
        self._dar_stock(100, self.almacen_src)
        prestamo = self._prestamo(15)
        prestamo.action_aprobar()

        self._validar(prestamo.picking_out_id)

        self.assertEqual(prestamo.state, 'in_transit')
        self.assertEqual(prestamo.line_ids.qty_sent, 15)

    def test_al_salir_deja_de_contar_como_comprometido(self):
        """Desde `in_transit` el stock real ya lo refleja: contarlo restaría dos veces."""
        self._dar_stock(100, self.almacen_src)
        prestamo = self._prestamo(15)
        prestamo.action_aprobar()
        motor = self.env['enteza.disponibilidad'].sudo()

        antes = motor.disponible(
            self.producto, self.almacen_src, self.desde, self.hasta,
        )[self.producto.id]
        self.assertEqual(antes, 85)

        self._validar(prestamo.picking_out_id)

        despues = motor.disponible(
            self.producto, self.almacen_src, self.desde, self.hasta,
        )[self.producto.id]
        self.assertEqual(despues, 85, 'El descuento lo hace ahora el stock real')

    def test_validar_la_entrada_pone_el_prestamo_en_prestado(self):
        self._dar_stock(100, self.almacen_src)
        prestamo = self._prestamo(15)
        prestamo.action_aprobar()

        self._validar(prestamo.picking_out_id)
        self._validar(prestamo.picking_in_id)

        self.assertEqual(prestamo.state, 'lent')

    def test_el_material_acaba_siendo_inventario_de_la_receptora(self):
        """D1: la propiedad pasa a quien recibe, y el alquiler nativo ya puede servirlo."""
        self._dar_stock(100, self.almacen_src)
        prestamo = self._prestamo(15)
        prestamo.action_aprobar()
        self._validar(prestamo.picking_out_id)
        self._validar(prestamo.picking_in_id)

        en_destino = self.producto.with_company(self.receptora).with_context(
            warehouse_id=self.almacen_dest.id,
        ).qty_available
        self.assertEqual(en_destino, 15)

    # ------------------------------------------------------------------
    # Acumulación: se AMPLÍA el albarán, no se rehace
    # ------------------------------------------------------------------

    def test_aprobar_lo_añadido_amplia_el_albaran_existente(self):
        """§7.0.2: nunca cancelar albaranes que el almacén ya puede haber impreso."""
        self._dar_stock(100, self.almacen_src)
        prestamo = self._prestamo(15)
        prestamo.action_aprobar()
        salida_original = prestamo.picking_out_id

        prestamo.incorporar([{
            'product_id': self.producto.id,
            'product_uom_id': self.producto.uom_id.id,
            'qty_proposed': 10,
            'date_from': self.desde,
            'date_to': self.hasta,
        }])
        self.assertTrue(prestamo.tiene_pendiente_aprobacion)
        # Todavía sin firmar: no se mueve nada más.
        self.assertEqual(len(salida_original.move_ids), 1)

        prestamo.action_aprobar()

        self.assertEqual(prestamo.picking_out_id, salida_original, 'Mismo albarán')
        self.assertEqual(len(salida_original.move_ids), 2)
        self.assertEqual(sum(salida_original.move_ids.mapped('product_uom_qty')), 25)
