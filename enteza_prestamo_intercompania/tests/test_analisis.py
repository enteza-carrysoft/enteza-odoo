"""Análisis por lotes: la red de seguridad (PRP §7.1).

Lo que importa de estas pruebas es que el análisis recoja lo que el camino de la
confirmación no puede: sobre todo **la ampliación de un pedido ya confirmado**, que hoy no
vuelve a pasar por el diálogo.
"""

from datetime import timedelta

from odoo import Command
from odoo.fields import Datetime
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAnalisisDeficit(TransactionCase):

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
        cls.analisis = cls.env['enteza.stock.deficit']

        cls.desde = Datetime.now() + timedelta(days=10)
        cls.hasta = Datetime.now() + timedelta(days=12)

    def _dar_stock(self, cantidad, almacen):
        quant = self.env['stock.quant'].with_company(almacen.company_id).create({
            'product_id': self.producto.id,
            'inventory_quantity': cantidad,
            'location_id': almacen.lot_stock_id.id,
        })
        quant.action_apply_inventory()

    def _confirmar(self, cantidad):
        pedido = self.env['sale.order'].with_context(in_rental_app=True).create({
            'partner_id': self.cliente.id,
            'rental_start_date': self.desde,
            'rental_return_date': self.hasta,
            'order_line': [Command.create({
                'product_id': self.producto.id, 'product_uom_qty': cantidad,
            })],
        })
        pedido.with_context(enteza_prestamo_aceptado=True).action_confirm()
        return pedido

    # ------------------------------------------------------------------

    def test_sin_deficit_no_anota_nada(self):
        self._dar_stock(80, self.almacen)
        self._confirmar(50)

        self.assertFalse(self.analisis.analizar())

    def test_detecta_el_deficit_y_quien_puede_cubrirlo(self):
        self._dar_stock(80, self.almacen)
        self._dar_stock(100, self.almacen_otra)
        self._confirmar(95)

        deficits = self.analisis.analizar()

        self.assertEqual(len(deficits), 1)
        self.assertEqual(deficits.product_id, self.producto)
        self.assertEqual(deficits.warehouse_id, self.almacen)
        self.assertEqual(deficits.qty_deficit, 15)
        self.assertEqual(deficits.qty_cubrible, 15)
        self.assertEqual(deficits.warehouse_src_id, self.almacen_otra)
        self.assertEqual(deficits.qty_sin_cubrir, 0)

    def test_marca_lo_que_nadie_puede_cubrir(self):
        """Es lo único de la lista que exige una decisión de negocio."""
        self._dar_stock(80, self.almacen)
        self._confirmar(95)

        deficits = self.analisis.analizar()

        self.assertEqual(deficits.qty_deficit, 15)
        self.assertEqual(deficits.qty_cubrible, 0)
        self.assertEqual(deficits.qty_sin_cubrir, 15)

    def test_recoge_la_ampliacion_de_un_pedido_confirmado(self):
        """🔴 El hueco conocido del módulo: ampliar no vuelve a pasar por el diálogo.

        Esta es la red que lo recoge, y la razón de que el cron siga haciendo falta con D5.
        """
        self._dar_stock(80, self.almacen)
        self._dar_stock(100, self.almacen_otra)
        pedido = self._confirmar(70)
        self.assertFalse(self.analisis.analizar(), 'De entrada cabe')

        pedido.order_line.product_uom_qty = 120

        deficits = self.analisis.analizar()
        self.assertEqual(deficits.qty_deficit, 40)
        self.assertEqual(deficits.warehouse_src_id, self.almacen_otra)

    def test_los_presupuestos_no_generan_deficit(self):
        """Solo lo confirmado cuenta como demanda (§5.7)."""
        self._dar_stock(80, self.almacen)
        self.env['sale.order'].with_context(in_rental_app=True).create({
            'partner_id': self.cliente.id,
            'rental_start_date': self.desde,
            'rental_return_date': self.hasta,
            'order_line': [Command.create({
                'product_id': self.producto.id, 'product_uom_qty': 500,
            })],
        })

        self.assertFalse(self.analisis.analizar())

    def test_es_idempotente(self):
        """Ejecutarlo dos veces no duplica nada (prueba 8 del §15)."""
        self._dar_stock(80, self.almacen)
        self._confirmar(95)

        self.analisis.analizar()
        segunda = self.analisis.analizar()

        self.assertEqual(len(self.analisis.search([])), 1)
        self.assertEqual(len(segunda), 1)

    def test_fuera_del_horizonte_no_se_mira(self):
        self._dar_stock(80, self.almacen)
        lejos = Datetime.now() + timedelta(days=200)
        pedido = self.env['sale.order'].with_context(in_rental_app=True).create({
            'partner_id': self.cliente.id,
            'rental_start_date': lejos,
            'rental_return_date': lejos + timedelta(days=1),
            'order_line': [Command.create({
                'product_id': self.producto.id, 'product_uom_qty': 500,
            })],
        })
        pedido.with_context(enteza_prestamo_aceptado=True).action_confirm()

        self.assertFalse(self.analisis.analizar())

    # ------------------------------------------------------------------
    # Propuesta (§7.2)
    # ------------------------------------------------------------------

    def test_proponer_crea_prestamos_en_borrador(self):
        """En borrador: esto lo dispara quien mira una lista, no quien cierra una venta."""
        self._dar_stock(80, self.almacen)
        self._dar_stock(100, self.almacen_otra)
        self._confirmar(95)
        deficits = self.analisis.analizar()

        deficits.action_proponer_prestamos()

        prestamo = self.env['enteza.stock.loan'].search([('origin', '=', 'batch')])
        self.assertEqual(len(prestamo), 1)
        self.assertEqual(prestamo.state, 'draft', 'No compromete material por su cuenta')
        self.assertEqual(prestamo.line_ids.qty_proposed, 15)
        self.assertEqual(prestamo.warehouse_src_id, self.almacen_otra)
        self.assertEqual(
            prestamo.date_transfer, (self.desde - timedelta(days=3)).date(),
        )
