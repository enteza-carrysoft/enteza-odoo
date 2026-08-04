"""Ciclo de vida del documento de préstamo (PRP §6.4, fase 2).

Se prueba el documento, no el cálculo: la aritmética de disponibilidad está en
`test_disponibilidad.py`. Aquí interesa que los estados no se salten, que la reserva
comprometa de verdad y que nada físico dependa de un usuario sin permiso (D2).
"""

from datetime import timedelta

from odoo import Command
from odoo.exceptions import UserError
from odoo.fields import Datetime
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestCicloVida(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.prestamista = cls.env.company
        cls.receptora = cls.env['res.company'].create({'name': 'Receptora Test'})
        cls.almacen = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.prestamista.id)], limit=1,
        )
        cls.almacen_receptora = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.receptora.id)], limit=1,
        )
        cls.producto = cls.env['product.product'].create({
            'name': 'Silla plegable (test)',
            'uom_id': cls.env.ref('uom.product_uom_unit').id,
            'rent_ok': True,
            'is_storable': True,
            'company_id': False,
        })
        cls.desde = Datetime.now() + timedelta(days=10)
        cls.hasta = Datetime.now() + timedelta(days=12)

        # `new_test_user` en vez de `res.users.create`: se encarga de los grupos base que un
        # usuario interno necesita para que las reglas de registro se comporten como en
        # producción. Creado a mano, el usuario se queda sin `base.group_user` y las pruebas
        # fallarían por permisos, no por lo que se quiere probar.
        cls.responsable = new_test_user(
            cls.env, login='responsable_prestamo_test',
            groups='base.group_user,'
                   'enteza_prestamo_intercompania.group_prestamo_responsable',
        )
        cls.comercial = new_test_user(
            cls.env, login='usuario_prestamo_test',
            groups='base.group_user,'
                   'enteza_prestamo_intercompania.group_prestamo_usuario',
        )

    def _dar_stock(self, cantidad):
        quant = self.env['stock.quant'].with_company(self.almacen.company_id).create({
            'product_id': self.producto.id,
            'inventory_quantity': cantidad,
            'location_id': self.almacen.lot_stock_id.id,
        })
        quant.action_apply_inventory()

    def _crear_prestamo(self, cantidad=100, **extra):
        valores = {
            'company_id': self.prestamista.id,
            'company_dest_id': self.receptora.id,
            'warehouse_src_id': self.almacen.id,
            'warehouse_dest_id': self.almacen_receptora.id,
            'line_ids': [Command.create({
                'product_id': self.producto.id,
                'product_uom_id': self.producto.uom_id.id,
                'qty_proposed': cantidad,
                'date_from': self.desde,
                'date_to': self.hasta,
            })],
        }
        valores.update(extra)
        return self.env['enteza.stock.loan'].create(valores)

    # ------------------------------------------------------------------
    # Numeración
    # ------------------------------------------------------------------

    def test_la_referencia_se_numera_sola(self):
        prestamo = self._crear_prestamo()
        self.assertTrue(prestamo.name.startswith('PRE/'))
        self.assertNotEqual(prestamo.name, 'Nuevo')

    def test_dos_prestamos_no_comparten_referencia(self):
        """La serie no tiene compañía: el mismo número no puede salir dos veces."""
        self.assertNotEqual(self._crear_prestamo().name, self._crear_prestamo().name)

    # ------------------------------------------------------------------
    # Reserva
    # ------------------------------------------------------------------

    def test_reservar_compromete_el_material(self):
        """Tras reservar, la prestamista ya no puede contar con esas unidades."""
        self._dar_stock(900)
        motor = self.env['enteza.disponibilidad']
        prestamo = self._crear_prestamo(100)
        prestamo.action_reservar()

        self.assertEqual(prestamo.state, 'reserved')
        self.assertTrue(prestamo.date_reserved)
        self.assertEqual(prestamo.line_ids.qty_reserved, 100)

        disponible = motor.disponible(
            self.producto, self.almacen, self.desde, self.hasta,
        )
        self.assertEqual(disponible[self.producto.id], 800)

    def test_reservar_calcula_la_fecha_de_traslado(self):
        """El día de la semana configurado en la prestamista, antes del inicio del préstamo."""
        self._dar_stock(900)
        prestamo = self._crear_prestamo(100)
        prestamo.action_reservar()
        self.assertEqual(
            prestamo.date_transfer,
            self.env['enteza.stock.loan']._fecha_traslado_de(self.desde, self.prestamista),
        )

    def test_no_se_puede_reservar_mas_de_lo_que_hay(self):
        """El aviso tiene que llegar al reservar, no al intentar mover el material."""
        self._dar_stock(50)
        prestamo = self._crear_prestamo(100)
        with self.assertRaises(UserError):
            prestamo.action_reservar()
        self.assertEqual(prestamo.state, 'draft')

    def test_no_se_puede_reservar_sin_lineas(self):
        prestamo = self.env['enteza.stock.loan'].create({
            'company_id': self.prestamista.id,
            'company_dest_id': self.receptora.id,
            'warehouse_src_id': self.almacen.id,
            'warehouse_dest_id': self.almacen_receptora.id,
        })
        with self.assertRaises(UserError):
            prestamo.action_reservar()

    def test_no_se_puede_reservar_con_almacenes_cruzados(self):
        """El almacén de origen tiene que ser de la prestamista, no de la otra."""
        self._dar_stock(900)
        prestamo = self._crear_prestamo(100)
        prestamo.warehouse_src_id = self.almacen_receptora
        with self.assertRaises(UserError):
            prestamo.action_reservar()

    def test_reservar_no_compite_contra_su_propia_reserva(self):
        """Un préstamo ya reservado tiene que poder aprobarse.

        Si la revalidación no se excluyera a sí misma, el préstamo vería su propia reserva
        como material comprometido y nunca pasaría de `reserved`.
        """
        self._dar_stock(100)
        prestamo = self._crear_prestamo(100)
        prestamo.action_reservar()
        prestamo.with_user(self.responsable).action_aprobar()
        self.assertEqual(prestamo.state, 'approved')

    # ------------------------------------------------------------------
    # Aprobación — D2: nada sale del almacén sin una persona
    # ------------------------------------------------------------------

    def test_un_usuario_normal_no_puede_aprobar(self):
        self._dar_stock(900)
        prestamo = self._crear_prestamo(100)
        prestamo.action_reservar()
        with self.assertRaises(UserError):
            prestamo.with_user(self.comercial).action_aprobar()
        self.assertEqual(prestamo.state, 'reserved')

    def test_aprobar_copia_la_cantidad_reservada(self):
        self._dar_stock(900)
        prestamo = self._crear_prestamo(100)
        prestamo.action_reservar()
        prestamo.with_user(self.responsable).action_aprobar()
        self.assertEqual(prestamo.line_ids.qty_approved, 100)

    def test_el_responsable_puede_ajustar_a_la_baja_antes_de_aprobar(self):
        """Y entonces manda lo aprobado, no lo reservado (§7.3)."""
        self._dar_stock(900)
        motor = self.env['enteza.disponibilidad']
        prestamo = self._crear_prestamo(100)
        prestamo.action_reservar()
        prestamo.line_ids.qty_approved = 60
        prestamo.with_user(self.responsable).action_aprobar()

        disponible = motor.disponible(
            self.producto, self.almacen, self.desde, self.hasta,
        )
        self.assertEqual(disponible[self.producto.id], 840)

    def test_no_se_puede_aprobar_desde_borrador(self):
        """Sin pasar por la reserva no hay nada comprometido que aprobar."""
        self._dar_stock(900)
        prestamo = self._crear_prestamo(100)
        with self.assertRaises(UserError):
            prestamo.with_user(self.responsable).action_aprobar()

    # ------------------------------------------------------------------
    # Cancelación y vuelta atrás
    # ------------------------------------------------------------------

    def test_cancelar_libera_la_reserva(self):
        """Prueba 12 del §15, ahora por la acción y no escribiendo el estado a mano."""
        self._dar_stock(900)
        motor = self.env['enteza.disponibilidad']
        prestamo = self._crear_prestamo(100)
        prestamo.action_reservar()
        prestamo.with_user(self.responsable).action_cancelar()

        self.assertEqual(prestamo.state, 'cancelled')
        disponible = motor.disponible(
            self.producto, self.almacen, self.desde, self.hasta,
        )
        self.assertEqual(disponible[self.producto.id], 900)

    def test_un_usuario_normal_no_puede_cancelar(self):
        self._dar_stock(900)
        prestamo = self._crear_prestamo(100)
        prestamo.action_reservar()
        with self.assertRaises(UserError):
            prestamo.with_user(self.comercial).action_cancelar()

    def test_no_se_puede_cancelar_lo_ya_trasladado(self):
        """🔴 El material ya salió: deshacerlo es un movimiento nuevo, no un cambio de estado.

        Cancelar aquí dejaría existencias descuadradas en las dos compañías (§12.11).
        """
        self._dar_stock(900)
        prestamo = self._crear_prestamo(100)
        prestamo.action_reservar()
        prestamo.state = 'lent'
        with self.assertRaises(UserError):
            prestamo.with_user(self.responsable).action_cancelar()

    def test_volver_a_borrador_olvida_la_marca_de_reserva(self):
        """`date_reserved` es el criterio de prioridad: si se libera, deja de valer."""
        self._dar_stock(900)
        prestamo = self._crear_prestamo(100)
        prestamo.action_reservar()
        prestamo.with_user(self.responsable).action_volver_borrador()
        self.assertEqual(prestamo.state, 'draft')
        self.assertFalse(prestamo.date_reserved)

    def test_no_se_puede_volver_a_borrador_desde_aprobado(self):
        """Con albaranes ya creados, volver atrás los dejaría huérfanos."""
        self._dar_stock(900)
        prestamo = self._crear_prestamo(100)
        prestamo.action_reservar()
        prestamo.with_user(self.responsable).action_aprobar()
        with self.assertRaises(UserError):
            prestamo.with_user(self.responsable).action_volver_borrador()

    # ------------------------------------------------------------------
    # Avisos de la vista de control
    # ------------------------------------------------------------------

    def test_traslado_retrasado_se_marca(self):
        """Reservado, con la fecha de traslado pasada y sin aprobar (§6.4)."""
        self._dar_stock(900)
        prestamo = self._crear_prestamo(100)
        prestamo.action_reservar()
        self.assertFalse(prestamo.traslado_retrasado)

        prestamo.date_transfer = Datetime.now().date() - timedelta(days=1)
        self.assertTrue(prestamo.traslado_retrasado)

    def test_aprobado_a_tiempo_no_se_marca_como_retrasado(self):
        """Solo alerta lo que sigue sin aprobar: aprobado ya está en marcha."""
        self._dar_stock(900)
        prestamo = self._crear_prestamo(100)
        prestamo.action_reservar()
        prestamo.with_user(self.responsable).action_aprobar()
        prestamo.date_transfer = Datetime.now().date() - timedelta(days=1)
        self.assertFalse(prestamo.traslado_retrasado)
