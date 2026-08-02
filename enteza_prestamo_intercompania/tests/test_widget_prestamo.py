"""Pruebas de los campos que alimentan el widget de disponibilidad (PRP §10.3, prueba 10bis).

Se prueba el cálculo del servidor, no la plantilla: lo que se pinta depende de estos tres
campos, así que si están bien el popover está bien. La herencia de la plantilla no se puede
probar con `TransactionCase` —vive en el bundle de assets— y se verifica aparte con
`.claude/skills/odoo19-dev/scripts/simular_herencia_owl.py`.

⚠️ Estas pruebas asumen que en la base solo hay dos compañías con almacén: la del entorno y
la que crea `setUpClass`. `_enteza_buscar_prestamista` mira **todos** los almacenes ajenos a
la compañía del pedido, así que una tercera compañía con existencias cambiaría los números.
"""

from datetime import timedelta

from odoo import Command
from odoo.fields import Datetime
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestWidgetPrestamo(TransactionCase):

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
            'rent_ok': True,
            'is_storable': True,
            'company_id': False,
        })
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente Test'})

        cls.desde = Datetime.now() + timedelta(days=10)
        cls.hasta = Datetime.now() + timedelta(days=12)

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def _dar_stock(self, cantidad, almacen):
        quant = self.env['stock.quant'].with_company(almacen.company_id).create({
            'product_id': self.producto.id,
            'inventory_quantity': cantidad,
            'location_id': almacen.lot_stock_id.id,
        })
        quant.action_apply_inventory()

    def _linea(self, cantidad):
        """Presupuesto sin confirmar: es cuando el comercial mira el widget."""
        pedido = self.env['sale.order'].with_context(in_rental_app=True).create({
            'partner_id': self.cliente.id,
            'rental_start_date': self.desde,
            'rental_return_date': self.hasta,
            'order_line': [Command.create({
                'product_id': self.producto.id,
                'product_uom_qty': cantidad,
            })],
        })
        return pedido.order_line

    # ------------------------------------------------------------------
    # El caso normal: el widget no dice nada
    # ------------------------------------------------------------------

    def test_sin_deficit_no_avisa(self):
        """Con material de sobra el widget se comporta como el nativo (decisión 2026-08-02)."""
        self._dar_stock(80, self.almacen)
        linea = self._linea(50)

        self.assertEqual(linea.enteza_falta, 0)
        self.assertEqual(linea.enteza_prestable_otra, 0)
        self.assertFalse(linea.enteza_origen_prestamo)

    def test_justo_lo_que_hay_no_avisa(self):
        """Pedir exactamente el disponible no es un déficit."""
        self._dar_stock(80, self.almacen)
        linea = self._linea(80)

        self.assertEqual(linea.enteza_falta, 0)

    def test_linea_que_no_es_alquiler_no_calcula(self):
        self._dar_stock(80, self.almacen)
        pedido = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'order_line': [Command.create({
                'product_id': self.producto.id,
                'product_uom_qty': 500,
            })],
        })
        self.assertFalse(pedido.order_line.is_rental)
        self.assertEqual(pedido.order_line.enteza_falta, 0)

    # ------------------------------------------------------------------
    # El caso del cliente: 80 en casa, piden 95, la otra compañía tiene
    # ------------------------------------------------------------------

    def test_deficit_cubierto_por_la_otra_compania(self):
        self._dar_stock(80, self.almacen)
        self._dar_stock(20, self.almacen_otra)
        linea = self._linea(95)

        self.assertEqual(linea.enteza_falta, 15)
        # Se acota a lo que falta: al comercial no le sirve saber que sobran 5 en Jerez.
        self.assertEqual(linea.enteza_prestable_otra, 15)
        self.assertIn(self.otra.name, linea.enteza_origen_prestamo)
        self.assertIn(self.almacen_otra.name, linea.enteza_origen_prestamo)

    def test_cobertura_parcial(self):
        """Cubrir 8 de 15 se dice tal cual: nunca dar por resuelto lo que no lo está."""
        self._dar_stock(80, self.almacen)
        self._dar_stock(8, self.almacen_otra)
        linea = self._linea(95)

        self.assertEqual(linea.enteza_falta, 15)
        self.assertEqual(linea.enteza_prestable_otra, 8)
        self.assertTrue(linea.enteza_origen_prestamo)

    def test_nadie_puede_prestar(self):
        self._dar_stock(80, self.almacen)
        linea = self._linea(95)

        self.assertEqual(linea.enteza_falta, 15)
        self.assertEqual(linea.enteza_prestable_otra, 0)
        self.assertFalse(linea.enteza_origen_prestamo)

    # ------------------------------------------------------------------
    # Aviso de la cabecera del pedido
    # ------------------------------------------------------------------

    def test_sin_deficit_no_hay_aviso_en_cabecera(self):
        self._dar_stock(80, self.almacen)
        linea = self._linea(50)

        self.assertFalse(linea.order_id.enteza_aviso_deficit)

    def test_el_aviso_nombra_producto_cantidad_y_prestamista(self):
        self._dar_stock(80, self.almacen)
        self._dar_stock(20, self.almacen_otra)
        linea = self._linea(95)

        aviso = linea.order_id.enteza_aviso_deficit
        self.assertTrue(aviso)
        self.assertIn(self.producto.name, aviso)
        self.assertIn('15', aviso)
        self.assertIn(self.otra.name, aviso)

    def test_el_aviso_recoge_todas_las_lineas_con_deficit(self):
        """En un pedido largo el aviso es lo único que se lee: tiene que estar completo."""
        otro_producto = self.env['product.product'].create({
            'name': 'Mesa plegable (test)',
            'uom_id': self.env.ref('uom.product_uom_unit').id,
            'rent_ok': True,
            'is_storable': True,
            'company_id': False,
        })
        self._dar_stock(80, self.almacen)
        pedido = self.env['sale.order'].with_context(in_rental_app=True).create({
            'partner_id': self.cliente.id,
            'rental_start_date': self.desde,
            'rental_return_date': self.hasta,
            'order_line': [
                Command.create({'product_id': self.producto.id, 'product_uom_qty': 95}),
                Command.create({'product_id': otro_producto.id, 'product_uom_qty': 4}),
            ],
        })

        aviso = pedido.enteza_aviso_deficit
        self.assertIn(self.producto.name, aviso)
        self.assertIn(otro_producto.name, aviso)

    def test_el_aviso_escapa_el_nombre_del_producto(self):
        """El aviso es HTML construido a mano: que un nombre raro no inyecte marcado."""
        travieso = self.env['product.product'].create({
            'name': 'Silla <b>rota</b> & Cía',
            'uom_id': self.env.ref('uom.product_uom_unit').id,
            'rent_ok': True,
            'is_storable': True,
            'company_id': False,
        })
        pedido = self.env['sale.order'].with_context(in_rental_app=True).create({
            'partner_id': self.cliente.id,
            'rental_start_date': self.desde,
            'rental_return_date': self.hasta,
            'order_line': [Command.create({
                'product_id': travieso.id, 'product_uom_qty': 10,
            })],
        })

        self.assertIn('&lt;b&gt;', pedido.enteza_aviso_deficit)
        self.assertNotIn('<b>rota</b>', pedido.enteza_aviso_deficit)

    # ------------------------------------------------------------------
    # Un préstamo ya reservado deja de contar como déficit
    # ------------------------------------------------------------------

    def test_un_prestamo_para_esta_linea_tapa_el_deficit(self):
        """El material lo pone la OTRA compañía, así que el almacén propio no cambia.

        Sin la resta de `_enteza_cubierto_por_prestamo`, el pedido seguiría avisando de que
        faltan 15 cuando ya están resueltas — y eso es lo que va a pasar en cuanto el
        enganche de `action_confirm` empiece a crear préstamos.
        """
        self._dar_stock(80, self.almacen)
        self._dar_stock(20, self.almacen_otra)
        linea = self._linea(95)
        self.assertEqual(linea.enteza_falta, 15)

        self.env['enteza.stock.loan'].create({
            'name': 'PRE/TEST/CUBRE',
            'company_id': self.otra.id,
            'company_dest_id': self.propia.id,
            'warehouse_src_id': self.almacen_otra.id,
            'warehouse_dest_id': self.almacen.id,
            'state': 'reserved',
            'line_ids': [Command.create({
                'product_id': self.producto.id,
                'product_uom_id': self.producto.uom_id.id,
                'qty_reserved': 15,
                'sale_line_id': linea.id,
                'date_from': self.desde,
                'date_to': self.hasta,
            })],
        })
        linea.invalidate_recordset(['enteza_falta'])

        self.assertEqual(linea.enteza_falta, 0)
        self.assertFalse(linea.order_id.enteza_aviso_deficit)

    def test_un_prestamo_en_borrador_no_tapa_nada(self):
        """Una propuesta sin reservar no compromete material: no puede tapar el aviso."""
        self._dar_stock(80, self.almacen)
        self._dar_stock(20, self.almacen_otra)
        linea = self._linea(95)

        self.env['enteza.stock.loan'].create({
            'name': 'PRE/TEST/BORRADOR',
            'company_id': self.otra.id,
            'company_dest_id': self.propia.id,
            'warehouse_src_id': self.almacen_otra.id,
            'warehouse_dest_id': self.almacen.id,
            'state': 'draft',
            'line_ids': [Command.create({
                'product_id': self.producto.id,
                'product_uom_id': self.producto.uom_id.id,
                'qty_proposed': 15,
                'sale_line_id': linea.id,
                'date_from': self.desde,
                'date_to': self.hasta,
            })],
        })
        linea.invalidate_recordset(['enteza_falta'])

        self.assertEqual(linea.enteza_falta, 15)

    # ------------------------------------------------------------------
    # 🔴 Por qué no se usa el campo nativo como atajo
    # ------------------------------------------------------------------

    def test_un_prestamo_comprometido_genera_deficit_que_el_nativo_no_ve(self):
        """El nativo no descuenta los préstamos, así que no sirve de prefiltro.

        Es la prueba que justifica el coste de recalcular con el motor propio en cada línea.
        Si algún día alguien "optimiza" el compute usando `virtual_available_at_date` para
        decidir si hay déficit, esta prueba es la que lo tiene que parar: el nativo dirá que
        hay 900 libres mientras 850 están comprometidas para prestar.
        """
        self._dar_stock(900, self.almacen)
        self.env['enteza.stock.loan'].create({
            'name': 'PRE/TEST/WIDGET',
            'company_id': self.propia.id,
            'company_dest_id': self.otra.id,
            'warehouse_src_id': self.almacen.id,
            'warehouse_dest_id': self.almacen_otra.id,
            'state': 'reserved',
            'line_ids': [Command.create({
                'product_id': self.producto.id,
                'product_uom_id': self.producto.uom_id.id,
                'qty_reserved': 850,
                'date_from': self.desde,
                'date_to': self.hasta,
            })],
        })

        linea = self._linea(100)

        # El nativo ignora el préstamo y no ve problema...
        self.assertGreaterEqual(linea.virtual_available_at_date, 100)
        # ...pero de las 900 solo quedan 50 libres de verdad.
        self.assertEqual(linea.enteza_falta, 50)
