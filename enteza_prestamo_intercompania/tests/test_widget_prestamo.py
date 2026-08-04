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

    def test_cada_linea_se_evalua_por_su_cuenta(self):
        """En un pedido de muchas líneas, cada una marca su icono o no lo marca."""
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
                Command.create({'product_id': self.producto.id, 'product_uom_qty': 10}),
                Command.create({'product_id': otro_producto.id, 'product_uom_qty': 4}),
            ],
        })
        primera, segunda, tercera = pedido.order_line

        self.assertEqual(primera.enteza_falta, 15)
        # 🔴 Limitación conocida y heredada del nativo: dos líneas del MISMO presupuesto no
        # compiten entre sí. Solo cuenta como demanda lo confirmado (`state = 'sale'`,
        # `_get_active_rental_lines`), así que las dos ven las mismas 80 libres aunque entre
        # ambas pidan 105. El reparto real lo decide la confirmación, que es donde se reserva.
        self.assertEqual(segunda.enteza_falta, 0)
        # De este producto no hay ni una unidad en ningún sitio.
        self.assertEqual(tercera.enteza_falta, 4)
        self.assertEqual(tercera.enteza_prestable_otra, 0)

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
        # El préstamo cubre ESTA línea (llega de fuera), no descuenta del almacén PROPIO:
        # `virtual_available_at_date` solo se corrige cuando el almacén de la línea es quien
        # PRESTA a otro, no cuando recibe. Sigue en 80 aunque `enteza_falta` ya esté a 0 — es
        # justo lo que la prueba de más abajo usa para explicar por qué no sirve de atajo.
        self.assertEqual(linea.virtual_available_at_date, 80)

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
    # El propio disponible nativo también se corrige (bug de cliente, 2026-08-04)
    # ------------------------------------------------------------------

    def test_prestamo_comprometido_se_descuenta_del_disponible_nativo(self):
        """`virtual_available_at_date` ya no ignora lo que este almacén tiene prometido.

        Hasta esta corrección, el popover nativo («Disponible para alquilar») no se enteraba
        de que el almacén ya había comprometido material para prestarlo a otra compañía: un
        comercial que montaba un pedido NUEVO en Stileum, después de que Stileum le prestara
        a Vimaple, seguía viendo el disponible de siempre. `_compute_qty_at_date` (este
        módulo) corrige el campo justo después del cálculo nativo, con el mismo suelo en cero.
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

        # De las 900, 850 están prometidas a la otra compañía: el nativo ahora lo sabe y
        # enseña las 50 que quedan de verdad, no las 900.
        self.assertEqual(linea.virtual_available_at_date, 50)
        self.assertEqual(linea.free_qty_today, 50)
        self.assertEqual(linea.enteza_falta, 50)

    def test_prestamo_en_borrador_no_se_descuenta_del_nativo(self):
        """Una propuesta sin reservar tampoco compromete nada de cara al widget nativo."""
        self._dar_stock(900, self.almacen)
        self.env['enteza.stock.loan'].create({
            'name': 'PRE/TEST/WIDGET-DRAFT',
            'company_id': self.propia.id,
            'company_dest_id': self.otra.id,
            'warehouse_src_id': self.almacen.id,
            'warehouse_dest_id': self.almacen_otra.id,
            'state': 'draft',
            'line_ids': [Command.create({
                'product_id': self.producto.id,
                'product_uom_id': self.producto.uom_id.id,
                'qty_proposed': 850,
                'date_from': self.desde,
                'date_to': self.hasta,
            })],
        })

        linea = self._linea(100)

        self.assertEqual(linea.virtual_available_at_date, 900)
        self.assertEqual(linea.enteza_falta, 0)

    # ------------------------------------------------------------------
    # 🔴 Por qué `enteza_falta` sigue sin usar el campo nativo como atajo
    # ------------------------------------------------------------------

    def test_el_nativo_corregido_no_basta_como_atajo_para_enteza_falta(self):
        """Corregir `virtual_available_at_date` no lo vuelve intercambiable con `enteza_falta`.

        Son dos correcciones distintas sobre el mismo nativo: esta (`_compute_qty_at_date`)
        descuenta lo que el almacén de la línea PRESTA a otros; `enteza_falta` además suma lo
        que un préstamo ENTRANTE cubre para esta línea en concreto
        (`_enteza_cubierto_por_prestamo`). Aquí el almacén propio solo tiene 80 y la línea
        pide 95: el nativo, ya corregido, se queda en 80 porque no sabe nada del préstamo que
        llega de fuera. Si `enteza_falta` se calculara a partir de él, seguiría marcando 15
        de menos con el pedido ya cubierto del todo.
        """
        self._dar_stock(80, self.almacen)
        self._dar_stock(20, self.almacen_otra)
        linea = self._linea(95)

        self.env['enteza.stock.loan'].create({
            'name': 'PRE/TEST/ATAJO',
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
        linea.invalidate_recordset(['enteza_falta', 'virtual_available_at_date'])

        self.assertEqual(linea.virtual_available_at_date, 80)
        self.assertEqual(linea.enteza_falta, 0)
