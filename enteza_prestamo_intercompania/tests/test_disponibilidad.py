"""Pruebas del motor de disponibilidad (PRP §5, fase 1).

El escenario se construye con los mismos idiomas que usa Odoo en
`sale_stock_renting/tests/test_rental.py`: pedidos creados con `in_rental_app=True` y
confirmados de verdad, y existencias aplicadas por inventario. Se hace así a propósito: el
motor delega en el cálculo nativo, y montar el escenario a mano por SQL probaría una
realidad que no es la que se va a dar en producción.

Lo que se prueba aquí es lo que este módulo añade sobre el nativo —la resta del material
comprometido para prestar— y que la delegación está bien enganchada. La aritmética del
propio `_get_unavailable_qty` ya la prueba Odoo.
"""

from datetime import timedelta

from psycopg2 import IntegrityError

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.fields import Datetime
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestDisponibilidad(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.motor = cls.env['enteza.disponibilidad']

        cls.prestamista = cls.env.company
        cls.receptora = cls.env['res.company'].create({'name': 'Receptora Test'})
        cls.almacen = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.prestamista.id)], limit=1,
        )
        cls.almacen_receptora = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.receptora.id)], limit=1,
        )

        # Producto compartido entre compañías (`company_id` vacío). Es la premisa de todo
        # el diseño: sin productos compartidos no hay préstamo posible (PRP §11.5).
        cls.producto = cls.env['product.product'].create({
            'name': 'Silla plegable (test)',
            'uom_id': cls.env.ref('uom.product_uom_unit').id,
            'rent_ok': True,
            'is_storable': True,
            'company_id': False,
        })
        cls.productos = cls.producto
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente Test'})

        # Intervalo de referencia, siempre en el futuro para que el motor tome la rama de
        # disponibilidad prevista, que es la que se usa al confirmar un pedido.
        cls.desde = Datetime.now() + timedelta(days=10)
        cls.hasta = Datetime.now() + timedelta(days=12)

    # ------------------------------------------------------------------
    # Utilidades de escenario
    # ------------------------------------------------------------------

    def _dar_stock(self, cantidad, almacen=None):
        almacen = almacen or self.almacen
        quant = self.env['stock.quant'].with_company(almacen.company_id).create({
            'product_id': self.producto.id,
            'inventory_quantity': cantidad,
            'location_id': almacen.lot_stock_id.id,
        })
        quant.action_apply_inventory()

    def _crear_pedido(self, cantidad, desde=None, hasta=None, confirmar=True):
        pedido = self.env['sale.order'].with_context(in_rental_app=True).create({
            'partner_id': self.cliente.id,
            'rental_start_date': desde or self.desde,
            'rental_return_date': hasta or self.hasta,
            'order_line': [Command.create({
                'product_id': self.producto.id,
                'product_uom_qty': cantidad,
            })],
        })
        if confirmar:
            pedido.action_confirm()
        return pedido

    def _crear_prestamo(self, cantidad, estado='reserved', desde=None, hasta=None,
                        almacen=None):
        return self.env['enteza.stock.loan'].create({
            'name': 'PRE/TEST',
            'company_id': self.prestamista.id,
            'company_dest_id': self.receptora.id,
            'warehouse_src_id': (almacen or self.almacen).id,
            'warehouse_dest_id': self.almacen_receptora.id,
            'state': estado,
            'line_ids': [Command.create({
                'product_id': self.producto.id,
                'product_uom_id': self.producto.uom_id.id,
                'qty_reserved': cantidad,
                'date_from': desde or self.desde,
                'date_to': hasta or self.hasta,
            })],
        })

    def _disponible(self, **kwargs):
        return self.motor.disponible(
            self.productos, self.almacen, self.desde, self.hasta, **kwargs,
        )[self.producto.id]

    # ------------------------------------------------------------------
    # Delegación en el cálculo nativo
    # ------------------------------------------------------------------

    def test_sin_compromisos_esta_todo_disponible(self):
        self._dar_stock(900)
        self.assertEqual(self._disponible(), 900)

    def test_pedido_confirmado_resta(self):
        self._dar_stock(900)
        self._crear_pedido(300)
        self.assertEqual(self._disponible(), 600)

    def test_la_propia_linea_confirmada_no_se_resta_dos_veces(self):
        """Regresión del 2026-08-02, y de las caras porque solo aparece tras confirmar.

        Al preguntar ignorando una línea YA CONFIRMADA, sus unidades no pueden restarse. El
        movimiento de stock existe y `virtual_available` ya lo descontó; `_rentable` vuelve a
        sumarlo con `_get_virtual_unavailable_qty_in_rent`, y esa devolución solo se salta
        cuando el pedido está en borrador — que es lo que hace el nativo.

        Con el fallo, un pedido confirmado de 95 unidades sobre 80 en almacén daba un déficit
        de 110 en vez de 15: el material se contaba dos veces.
        """
        self._dar_stock(900)
        pedido = self._crear_pedido(300)

        self.assertEqual(self._disponible(ignorar_linea=pedido.order_line), 900)

    def test_presupuesto_sin_confirmar_no_resta(self):
        """Los presupuestos no reservan material (PRP §5.7, PENDIENTE-2 resuelto).

        El riesgo de que dos comerciales vendan lo mismo se resuelve reservando al
        confirmar (D5), no contando presupuestos.
        """
        self._dar_stock(900)
        self._crear_pedido(300, confirmar=False)
        self.assertEqual(self._disponible(), 900)

    def test_pedido_que_no_solapa_no_resta(self):
        self._dar_stock(900)
        self._crear_pedido(
            300,
            desde=self.desde + timedelta(days=30),
            hasta=self.hasta + timedelta(days=30),
        )
        self.assertEqual(self._disponible(), 900)

    def test_ignorar_linea_excluye_el_pedido_que_se_modifica(self):
        """Al recalcular un pedido confirmado no debe competir consigo mismo (§7.0.2)."""
        self._dar_stock(900)
        pedido = self._crear_pedido(300)
        self.assertEqual(self._disponible(), 600)
        self.assertEqual(self._disponible(ignorar_linea=pedido.order_line), 900)

    # ------------------------------------------------------------------
    # Material comprometido para prestar — lo propio del módulo
    # ------------------------------------------------------------------

    def test_reserva_de_prestamo_resta(self):
        """Prueba 11 del §15: no se puede vender dos veces el material ya prestado."""
        self._dar_stock(900)
        self._crear_prestamo(100)
        self.assertEqual(self._disponible(), 800)

    def test_reserva_aprobada_resta_la_cantidad_aprobada(self):
        self._dar_stock(900)
        prestamo = self._crear_prestamo(100, estado='approved')
        prestamo.line_ids.qty_approved = 60
        self.assertEqual(self._disponible(), 840)

    def test_prestamo_ya_trasladado_no_resta_dos_veces(self):
        """🔴 Corrección deliberada respecto al PRP §5.1.

        En `in_transit` y `lent` la salida ya está validada: el material ya no está en el
        almacén y el stock ya lo refleja. Contarlo además como comprometido lo restaría dos
        veces y bloquearía ventas legítimas de la prestamista.

        Aquí el stock se deja intacto a propósito para aislar el efecto: si el préstamo en
        `lent` restara, saldrían 800 en vez de 900.
        """
        self._dar_stock(900)
        self._crear_prestamo(100, estado='lent')
        self.assertEqual(self._disponible(), 900)

    def test_prestamo_cancelado_libera_la_reserva(self):
        """Prueba 12 del §15."""
        self._dar_stock(900)
        prestamo = self._crear_prestamo(100)
        self.assertEqual(self._disponible(), 800)
        prestamo.state = 'cancelled'
        self.assertEqual(self._disponible(), 900)

    def test_prestamo_fuera_de_fechas_no_resta(self):
        """Una reserva sin intervalo bloquearía el material para siempre (PRP §5.5)."""
        self._dar_stock(900)
        self._crear_prestamo(
            100,
            desde=self.desde + timedelta(days=60),
            hasta=self.hasta + timedelta(days=60),
        )
        self.assertEqual(self._disponible(), 900)

    def test_prestamo_de_otro_almacen_no_resta(self):
        """El cálculo se scopea por almacén, como el nativo."""
        self._dar_stock(900)
        self._crear_prestamo(100, almacen=self.almacen_receptora)
        self.assertEqual(self._disponible(), 900)

    def test_prestamo_que_envuelve_el_intervalo_resta(self):
        """🔴 El préstamo empieza antes y acaba después: no tiene ningún evento dentro.

        Es el caso que se escapaba midiendo el pico solo en los eventos interiores del
        barrido: el préstamo no aportaba ninguna fecha entre `desde` y `hasta`, el máximo
        se quedaba en cero y la prestamista habría vuelto a vender material ya
        comprometido. Se da siempre que se presta para un fin de semana largo y luego se
        consulta un día suelto de dentro.
        """
        self._dar_stock(900)
        self._crear_prestamo(
            100,
            desde=self.desde - timedelta(days=5),
            hasta=self.hasta + timedelta(days=5),
        )
        self.assertEqual(self._disponible(), 800)

    def test_prestamo_que_acaba_al_empezar_el_intervalo_no_resta(self):
        """Los intervalos se tratan como semiabiertos `[date_from, date_to)`.

        Un préstamo que se devuelve justo cuando empieza el alquiler ya no compromete nada.
        El dominio lo trae (`date_to >= desde`), así que el barrido tiene que descontarlo.
        """
        self._dar_stock(900)
        self._crear_prestamo(
            100,
            desde=self.desde - timedelta(days=5),
            hasta=self.desde,
        )
        self.assertEqual(self._disponible(), 900)

    def test_prestamos_solapados_suman_su_pico(self):
        self._dar_stock(900)
        self._crear_prestamo(100)
        self._crear_prestamo(50)
        self.assertEqual(self._disponible(), 750)

    def test_ignorar_prestamos_excluye_el_que_se_recalcula(self):
        self._dar_stock(900)
        prestamo = self._crear_prestamo(100)
        self.assertEqual(self._disponible(ignorar_prestamos=prestamo), 900)

    def test_pedido_y_prestamo_se_acumulan(self):
        self._dar_stock(900)
        self._crear_pedido(300)
        self._crear_prestamo(100)
        self.assertEqual(self._disponible(), 500)

    # ------------------------------------------------------------------
    # Prestable y déficit
    # ------------------------------------------------------------------

    def test_prestable_nunca_es_negativo(self):
        """Un almacén en déficit no presta «en negativo»."""
        self._dar_stock(100)
        self._crear_pedido(150)
        self.assertEqual(self._disponible(), -50)
        prestable = self.motor.prestable(
            self.productos, self.almacen, self.desde, self.hasta,
        )
        self.assertEqual(prestable[self.producto.id], 0)

    def test_deficit_caso_canonico(self):
        """El caso del §1: 900 en casa, hacen falta 1.000, faltan 100."""
        self._dar_stock(900)
        faltas = self.motor.deficit(
            self.productos, self.almacen, self.desde, self.hasta,
            {self.producto.id: 1000},
        )
        self.assertEqual(faltas.get(self.producto.id), 100)

    def test_sin_deficit_no_devuelve_entrada(self):
        self._dar_stock(900)
        faltas = self.motor.deficit(
            self.productos, self.almacen, self.desde, self.hasta,
            {self.producto.id: 900},
        )
        self.assertFalse(faltas)

    def test_deficit_cuenta_el_material_ya_prestado(self):
        """El déficit tiene que ver la reserva de préstamo, no solo los pedidos."""
        self._dar_stock(900)
        self._crear_prestamo(100)
        faltas = self.motor.deficit(
            self.productos, self.almacen, self.desde, self.hasta,
            {self.producto.id: 850},
        )
        self.assertEqual(faltas.get(self.producto.id), 50)

    # ------------------------------------------------------------------
    # Fachada RPC
    # ------------------------------------------------------------------

    def _consultar(self, **kwargs):
        """Llama a la fachada como lo haría un cliente RPC: ids y fechas en texto."""
        return self.motor.consultar(
            self.productos.ids,
            self.almacen.id,
            fields.Datetime.to_string(self.desde),
            fields.Datetime.to_string(self.hasta),
            **kwargs,
        )

    def test_fachada_acepta_ids_y_fechas_en_texto(self):
        """Es lo único que atraviesa una llamada RPC.

        Con la API interna la consulta reventaba en `'<=' not supported between str and
        datetime`, comprobado contra `enteza26` el 2026-08-01.
        """
        self._dar_stock(900)
        self._crear_pedido(300)
        filas = self._consultar()
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]['product_id'], self.producto.id)
        self.assertEqual(filas[0]['disponible'], 600)
        self.assertEqual(filas[0]['prestable'], 600)

    def test_fachada_devuelve_la_falta_si_se_le_pasan_cantidades(self):
        """El caso del §1 preguntado desde fuera: 900 en casa, hacen falta 1.000."""
        self._dar_stock(900)
        filas = self._consultar(cantidades={self.producto.id: 1000})
        self.assertEqual(filas[0]['necesita'], 1000)
        self.assertEqual(filas[0]['falta'], 100)

    def test_fachada_admite_claves_de_cantidad_en_texto(self):
        """Un objeto JSON siempre llega con las claves como cadenas."""
        self._dar_stock(900)
        filas = self._consultar(cantidades={str(self.producto.id): 1000})
        self.assertEqual(filas[0]['falta'], 100)

    def test_fachada_descarta_los_productos_no_almacenables(self):
        """El motor nativo solo tiene sentido sobre almacenables (`_compute_qty_at_date`)."""
        servicio = self.env['product.product'].create({
            'name': 'Montaje (test)', 'type': 'service', 'company_id': False,
        })
        self._dar_stock(900)
        filas = self.motor.consultar(
            (self.producto | servicio).ids,
            self.almacen.id,
            fields.Datetime.to_string(self.desde),
            fields.Datetime.to_string(self.hasta),
        )
        self.assertEqual([f['product_id'] for f in filas], [self.producto.id])

    def test_fachada_avisa_si_el_almacen_no_existe(self):
        with self.assertRaises(UserError):
            self.motor.consultar(
                self.productos.ids, 0,
                fields.Datetime.to_string(self.desde),
                fields.Datetime.to_string(self.hasta),
            )

    def test_fachada_avisa_si_las_fechas_estan_del_reves(self):
        with self.assertRaises(UserError):
            self.motor.consultar(
                self.productos.ids, self.almacen.id,
                fields.Datetime.to_string(self.hasta),
                fields.Datetime.to_string(self.desde),
            )

    # ------------------------------------------------------------------
    # Integridad del modelo
    # ------------------------------------------------------------------

    def test_no_se_puede_prestar_a_uno_mismo(self):
        """La restricción tiene que existir DE VERDAD en la base de datos.

        Se comprueba provocando la violación en PostgreSQL, no leyendo la definición del
        modelo: con `_sql_constraints` (la forma anterior, ya no soportada en la 19) el
        modelo parecía correcto y la restricción no llegaba a crearse.
        """
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self.env['enteza.stock.loan'].create({
                'name': 'PRE/TEST/MISMA',
                'company_id': self.prestamista.id,
                'company_dest_id': self.prestamista.id,
            })
            self.env.flush_all()
