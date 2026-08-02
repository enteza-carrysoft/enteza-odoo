"""Pruebas del camino principal: confirmar el pedido con préstamo (PRP D5/D5.1, §7.0).

Cubren las pruebas 9, 9bis, 9ter y 10 del §15. La 10 (concurrencia real con dos
transacciones a la vez) **no se puede escribir con `TransactionCase`**: haría falta
`TransactionCase` con dos cursores o un `HttpCase`, y aquí no se puede ejecutar nada de todos
modos. Lo que sí se prueba es el recálculo del paso 2, que es lo que hace útil al bloqueo.
"""

from datetime import timedelta

from odoo import Command
from odoo.exceptions import UserError
from odoo.fields import Datetime
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestConfirmacionConPrestamo(TransactionCase):

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
        # Segundo producto para poder montar dos pedidos que NO compitan por el mismo stock:
        # así las cifras de las pruebas de acumulación se leen sin hacer cuentas.
        cls.producto_b = cls.env['product.product'].create({
            'name': 'Mesa plegable (test)',
            'uom_id': cls.env.ref('uom.product_uom_unit').id,
            'rent_ok': True,
            'is_storable': True,
            'company_id': False,
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

    def _pedido(self, cantidad, producto=None, desde=None, hasta=None):
        return self.env['sale.order'].with_context(in_rental_app=True).create({
            'partner_id': self.cliente.id,
            'rental_start_date': desde or self.desde,
            'rental_return_date': hasta or self.hasta,
            'order_line': [Command.create({
                'product_id': (producto or self.producto).id,
                'product_uom_qty': cantidad,
            })],
        })

    def _abrir_dialogo(self, pedido):
        """Confirma y devuelve el asistente que abre la acción."""
        accion = pedido.action_confirm()
        self.assertIsInstance(accion, dict, 'Se esperaba la acción del diálogo')
        self.assertEqual(accion['res_model'], 'enteza.prestamo.confirm')
        return self.env['enteza.prestamo.confirm'].browse(accion['res_id'])

    # ------------------------------------------------------------------
    # Sin déficit no se pregunta nada
    # ------------------------------------------------------------------

    def test_sin_deficit_confirma_directamente(self):
        self._dar_stock(80, self.almacen)
        pedido = self._pedido(50)

        self.assertTrue(pedido.action_confirm())
        self.assertEqual(pedido.state, 'sale')
        self.assertFalse(self.env['enteza.stock.loan'].search([
            ('origin_order_ids', 'in', pedido.ids),
        ]))

    # ------------------------------------------------------------------
    # Prueba 9 del §15: el caso del cliente
    # ------------------------------------------------------------------

    def test_el_dialogo_propone_lo_que_falta(self):
        self._dar_stock(80, self.almacen)
        self._dar_stock(20, self.almacen_otra)
        pedido = self._pedido(95)

        asistente = self._abrir_dialogo(pedido)

        # Abrir el diálogo NO confirma ni reserva.
        self.assertEqual(pedido.state, 'draft')
        self.assertEqual(len(asistente.line_ids), 1)
        self.assertEqual(asistente.line_ids.qty_falta, 15)
        self.assertEqual(asistente.line_ids.qty_prestable, 15)
        self.assertEqual(asistente.line_ids.qty_sin_cubrir, 0)
        self.assertEqual(asistente.line_ids.warehouse_src_id, self.almacen_otra)
        self.assertTrue(asistente.todo_cubierto)
        self.assertFalse(asistente.nada_cubierto)

    def test_aceptar_reserva_y_confirma(self):
        self._dar_stock(80, self.almacen)
        self._dar_stock(20, self.almacen_otra)
        pedido = self._pedido(95)

        self._abrir_dialogo(pedido).action_confirmar()

        self.assertEqual(pedido.state, 'sale')
        prestamo = self.env['enteza.stock.loan'].search([
            ('origin_order_ids', 'in', pedido.ids),
        ])
        self.assertEqual(len(prestamo), 1)
        self.assertEqual(prestamo.state, 'reserved')
        self.assertEqual(prestamo.company_id, self.otra, 'El préstamo es de quien presta')
        self.assertEqual(prestamo.company_dest_id, self.propia)
        self.assertEqual(prestamo.warehouse_src_id, self.almacen_otra)
        self.assertEqual(prestamo.warehouse_dest_id, self.almacen)
        self.assertEqual(prestamo.origin, 'confirmation')
        self.assertEqual(prestamo.line_ids.qty_reserved, 15)
        self.assertEqual(prestamo.line_ids.sale_line_id, pedido.order_line)
        # `date_reserved` es el criterio de prioridad: sin él se pierde quién pilló antes.
        self.assertTrue(prestamo.date_reserved)
        # Traslado programado tres días antes del inicio del alquiler (parámetro).
        self.assertEqual(
            prestamo.date_transfer,
            (self.desde - timedelta(days=3)).date(),
        )

    def test_tras_reservar_la_linea_deja_de_avisar(self):
        """El déficit está cubierto: el icono tiene que dejar de estar rojo."""
        self._dar_stock(80, self.almacen)
        self._dar_stock(20, self.almacen_otra)
        pedido = self._pedido(95)

        self._abrir_dialogo(pedido).action_confirmar()
        pedido.order_line.invalidate_recordset(['enteza_falta'])

        self.assertEqual(pedido.order_line.enteza_falta, 0)

    def test_el_material_prestado_deja_de_estar_libre_en_la_prestamista(self):
        """Prueba 11 del §15: nadie más puede contar con esas unidades."""
        self._dar_stock(80, self.almacen)
        self._dar_stock(20, self.almacen_otra)
        pedido = self._pedido(95)
        self._abrir_dialogo(pedido).action_confirmar()

        motor = self.env['enteza.disponibilidad'].sudo()
        libre = motor.disponible(
            self.producto, self.almacen_otra, self.desde, self.hasta,
        )[self.producto.id]

        self.assertEqual(libre, 5, 'De las 20 de Jerez, 15 están comprometidas')

    # ------------------------------------------------------------------
    # Prueba 9bis: cancelar no deja rastro
    # ------------------------------------------------------------------

    def test_cancelar_el_dialogo_no_confirma_ni_reserva(self):
        self._dar_stock(80, self.almacen)
        self._dar_stock(20, self.almacen_otra)
        pedido = self._pedido(95)

        self._abrir_dialogo(pedido).action_cancelar()

        self.assertEqual(pedido.state, 'draft')
        self.assertFalse(self.env['enteza.stock.loan'].search([]))

    # ------------------------------------------------------------------
    # Prueba 9ter: la propuesta caduca
    # ------------------------------------------------------------------

    def test_si_desaparece_el_material_no_se_reserva_nada(self):
        """Entre abrir el diálogo y aceptarlo, otro pedido se lleva lo de la prestamista.

        Es la prueba que justifica que el paso 2 recalcule en vez de fiarse de lo que se
        enseñó. Sin ella, el comercial aceptaría una propuesta que ya no existe.
        """
        self._dar_stock(80, self.almacen)
        self._dar_stock(20, self.almacen_otra)
        pedido = self._pedido(95)
        asistente = self._abrir_dialogo(pedido)

        # Mientras el comercial lee el diálogo, la otra compañía vende lo suyo.
        otro = self.env['sale.order'].with_context(in_rental_app=True).create({
            'partner_id': self.cliente.id,
            'company_id': self.otra.id,
            'warehouse_id': self.almacen_otra.id,
            'rental_start_date': self.desde,
            'rental_return_date': self.hasta,
            'order_line': [Command.create({
                'product_id': self.producto.id,
                'product_uom_qty': 20,
            })],
        })
        otro.with_context(enteza_prestamo_aceptado=True).action_confirm()

        with self.assertRaises(UserError):
            asistente.action_confirmar()

        self.assertEqual(pedido.state, 'draft')
        self.assertFalse(self.env['enteza.stock.loan'].search([
            ('origin_order_ids', 'in', pedido.ids),
        ]))

    # ------------------------------------------------------------------
    # Nadie puede prestar: se avisa, pero se deja confirmar (PENDIENTE-8)
    # ------------------------------------------------------------------

    def test_sin_prestamista_se_avisa_y_se_permite_confirmar(self):
        self._dar_stock(80, self.almacen)
        pedido = self._pedido(95)

        asistente = self._abrir_dialogo(pedido)
        self.assertTrue(asistente.nada_cubierto)
        self.assertEqual(asistente.line_ids.qty_sin_cubrir, 15)

        asistente.action_confirmar()

        self.assertEqual(pedido.state, 'sale')
        self.assertFalse(self.env['enteza.stock.loan'].search([]))
        # El déficit sigue a la vista en la línea: es lo único que impide perderlo de vista.
        pedido.order_line.invalidate_recordset(['enteza_falta'])
        self.assertEqual(pedido.order_line.enteza_falta, 15)

    # ------------------------------------------------------------------
    # Acumulación: un préstamo es un VIAJE, no un pedido
    # ------------------------------------------------------------------

    def _confirmar_con_prestamo(self, pedido):
        self._abrir_dialogo(pedido).action_confirmar()

    def test_dos_pedidos_de_la_misma_fecha_van_en_un_solo_prestamo(self):
        """Lo que pidió el cliente: un viaje, un documento, un par de albaranes."""
        self._dar_stock(80, self.almacen)
        self._dar_stock(100, self.almacen_otra)
        self._dar_stock(50, self.almacen_otra, self.producto_b)

        primero = self._pedido(95)
        self._confirmar_con_prestamo(primero)
        segundo = self._pedido(10, producto=self.producto_b)
        self._confirmar_con_prestamo(segundo)

        prestamos = self.env['enteza.stock.loan'].search([])
        self.assertEqual(len(prestamos), 1, 'Los dos pedidos comparten viaje')
        self.assertEqual(len(prestamos.line_ids), 2)
        self.assertEqual(prestamos.origin_order_ids, primero | segundo)
        self.assertEqual(
            set(prestamos.line_ids.mapped('product_id')),
            {self.producto, self.producto_b},
        )

    def test_fechas_de_traslado_distintas_son_viajes_distintos(self):
        """Un evento del sábado y otro del domingo no caben en el mismo porte."""
        self._dar_stock(80, self.almacen)
        self._dar_stock(100, self.almacen_otra)
        self._dar_stock(50, self.almacen_otra, self.producto_b)

        self._confirmar_con_prestamo(self._pedido(95))
        otro_dia = self._pedido(
            10, producto=self.producto_b,
            desde=self.desde + timedelta(days=1), hasta=self.hasta + timedelta(days=1),
        )
        self._confirmar_con_prestamo(otro_dia)

        prestamos = self.env['enteza.stock.loan'].search([])
        self.assertEqual(len(prestamos), 2)
        self.assertEqual(len(set(prestamos.mapped('date_transfer'))), 2)

    def test_se_acumula_sobre_un_prestamo_ya_aprobado_sin_reabrirlo(self):
        """El responsable no tiene que refirmar lo que ya autorizó."""
        self._dar_stock(80, self.almacen)
        self._dar_stock(100, self.almacen_otra)
        self._dar_stock(50, self.almacen_otra, self.producto_b)

        self._confirmar_con_prestamo(self._pedido(95))
        prestamo = self.env['enteza.stock.loan'].search([])
        prestamo.action_aprobar()
        self.assertEqual(prestamo.state, 'approved')
        self.assertFalse(prestamo.tiene_pendiente_aprobacion)

        self._confirmar_con_prestamo(self._pedido(10, producto=self.producto_b))

        self.assertEqual(len(self.env['enteza.stock.loan'].search([])), 1)
        self.assertEqual(prestamo.state, 'approved', 'No se reabre lo ya aprobado')
        self.assertTrue(prestamo.tiene_pendiente_aprobacion)

        nueva = prestamo.line_ids.filtered(
            lambda linea: linea.product_id == self.producto_b
        )
        self.assertEqual(nueva.qty_reserved, 10)
        self.assertEqual(nueva.qty_approved, 0, 'Reservada, pero sin firmar')

    def test_el_material_acumulado_queda_comprometido_antes_de_firmarse(self):
        """🔴 No puede haber una ventana en la que otro comercial venda esas unidades.

        `_qty_comprometida()` devuelve `qty_reserved` mientras `qty_approved` esté a cero,
        así que la reserva protege desde el instante en que se añade la línea. La firma hace
        falta para MOVER el material, no para reservarlo.
        """
        self._dar_stock(80, self.almacen)
        self._dar_stock(100, self.almacen_otra)
        self._dar_stock(50, self.almacen_otra, self.producto_b)

        self._confirmar_con_prestamo(self._pedido(95))
        self.env['enteza.stock.loan'].search([]).action_aprobar()
        self._confirmar_con_prestamo(self._pedido(10, producto=self.producto_b))

        motor = self.env['enteza.disponibilidad'].sudo()
        libre = motor.disponible(
            self.producto_b, self.almacen_otra, self.desde, self.hasta,
        )[self.producto_b.id]

        self.assertEqual(libre, 40, 'De las 50 de Jerez, 10 ya están comprometidas')

    def test_aprobar_lo_añadido_firma_solo_el_incremento(self):
        self._dar_stock(80, self.almacen)
        self._dar_stock(100, self.almacen_otra)
        self._dar_stock(50, self.almacen_otra, self.producto_b)

        self._confirmar_con_prestamo(self._pedido(95))
        prestamo = self.env['enteza.stock.loan'].search([])
        prestamo.action_aprobar()
        # El responsable recorta a mano lo que autoriza de la primera línea.
        primera = prestamo.line_ids
        primera.qty_approved = 12

        self._confirmar_con_prestamo(self._pedido(10, producto=self.producto_b))
        prestamo.action_aprobar()

        self.assertFalse(prestamo.tiene_pendiente_aprobacion)
        self.assertEqual(primera.qty_approved, 12, 'El recorte del responsable se respeta')
        nueva = prestamo.line_ids - primera
        self.assertEqual(nueva.qty_approved, 10)

    def test_aprobar_sin_nada_pendiente_avisa(self):
        self._dar_stock(80, self.almacen)
        self._dar_stock(100, self.almacen_otra)
        self._confirmar_con_prestamo(self._pedido(95))
        prestamo = self.env['enteza.stock.loan'].search([])
        prestamo.action_aprobar()

        with self.assertRaises(UserError):
            prestamo.action_aprobar()

    def test_no_se_acumula_sobre_un_prestamo_ya_trasladado(self):
        """Desde `in_transit` el camión salió: lo que llegue después es otro viaje."""
        self._dar_stock(80, self.almacen)
        self._dar_stock(100, self.almacen_otra)
        self._dar_stock(50, self.almacen_otra, self.producto_b)

        self._confirmar_con_prestamo(self._pedido(95))
        prestamo = self.env['enteza.stock.loan'].search([])
        prestamo.action_aprobar()
        prestamo.state = 'in_transit'

        self._confirmar_con_prestamo(self._pedido(10, producto=self.producto_b))

        prestamos = self.env['enteza.stock.loan'].search([])
        self.assertEqual(len(prestamos), 2, 'El material nuevo necesita un viaje nuevo')

    # ------------------------------------------------------------------
    # Guardas
    # ------------------------------------------------------------------

    def test_confirmar_varios_a_la_vez_se_para(self):
        """Desde la lista no se puede preguntar por uno sin dejar los demás a medias."""
        self._dar_stock(80, self.almacen)
        self._dar_stock(20, self.almacen_otra)
        pedidos = self._pedido(95) | self._pedido(95)

        with self.assertRaises(UserError):
            pedidos.action_confirm()

        self.assertEqual(set(pedidos.mapped('state')), {'draft'})

    def test_el_contexto_de_aceptado_no_vuelve_a_preguntar(self):
        """Sin esta salida, el asistente reabriría el diálogo al reconfirmar: bucle."""
        self._dar_stock(80, self.almacen)
        pedido = self._pedido(95)

        self.assertTrue(
            pedido.with_context(enteza_prestamo_aceptado=True).action_confirm()
        )
        self.assertEqual(pedido.state, 'sale')
