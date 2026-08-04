"""Pruebas de la disponibilidad en el buscador de producto (petición cliente, 2026-08-04).

`product.product`/`product.template._compute_display_name` (`models/product_product.py`,
`models/product_template.py`) pegan «- X uds.» al nombre que ve el desplegable de «Añadir un
producto», cuando el contexto trae el periodo y el almacén del pedido de alquiler
(`enteza.disponibilidad._enteza_contexto_periodo`). Sin ese contexto —cualquier búsqueda que
no sea la de la línea de un pedido de alquiler— el nombre no se toca.

El texto se recortó en la `19.0.10.0.3`: la primera versión, «— Disponible: X Uds» con la
unidad de medida detrás, se salía del ancho de la columna del desplegable casi siempre.

Se prueba llamando a `display_name` con el contexto que la vista manda, no montando la vista
de verdad: eso lo cubre la comprobación por xpath contra `enteza26` (ver el comentario en
`views/sale_order_product_search_views.xml`), no un `TransactionCase`.
"""

from datetime import timedelta

from odoo import Command
from odoo.fields import Datetime
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestBuscadorProducto(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.propia = cls.env.company
        cls.almacen = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.propia.id)], limit=1,
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

    def _dar_stock(self, cantidad, almacen=None):
        almacen = almacen or self.almacen
        quant = self.env['stock.quant'].with_company(almacen.company_id).create({
            'product_id': self.producto.id,
            'inventory_quantity': cantidad,
            'location_id': almacen.lot_stock_id.id,
        })
        quant.action_apply_inventory()

    def _contexto(self, almacen=None):
        return {
            'enteza_rental_start': self.desde,
            'enteza_rental_end': self.hasta,
            'enteza_rental_warehouse_id': (almacen or self.almacen).id,
        }

    # ------------------------------------------------------------------
    # Sin contexto de alquiler: no se toca nada
    # ------------------------------------------------------------------

    def test_sin_contexto_no_toca_el_nombre(self):
        self._dar_stock(80)
        self.assertEqual(self.producto.display_name, 'Silla plegable (test)')
        self.assertEqual(
            self.producto.product_tmpl_id.display_name, 'Silla plegable (test)',
        )

    def test_contexto_a_medias_no_toca_el_nombre(self):
        """Falta el almacén: es un pedido sin fechas de alquiler, o sin almacén elegido aún."""
        self._dar_stock(80)
        producto = self.producto.with_context(
            enteza_rental_start=self.desde, enteza_rental_end=self.hasta,
        )
        self.assertEqual(producto.display_name, 'Silla plegable (test)')

    # ------------------------------------------------------------------
    # Con contexto completo: se pega la disponibilidad
    # ------------------------------------------------------------------

    def test_producto_muestra_disponible(self):
        self._dar_stock(80)
        producto = self.producto.with_context(**self._contexto())
        self.assertEqual(producto.display_name, 'Silla plegable (test) - 80 uds.')

    def test_plantilla_con_variante_unica_muestra_disponible(self):
        """`product_template_id` es el campo que usa el buscador por defecto."""
        self._dar_stock(80)
        plantilla = self.producto.product_tmpl_id.with_context(**self._contexto())
        self.assertEqual(plantilla.display_name, 'Silla plegable (test) - 80 uds.')

    def test_sin_existencias_muestra_cero(self):
        producto = self.producto.with_context(**self._contexto())
        self.assertEqual(producto.display_name, 'Silla plegable (test) - 0 uds.')

    # ------------------------------------------------------------------
    # Mismo motor que `enteza_falta`: ya descuenta lo prestado
    # ------------------------------------------------------------------

    def test_descuenta_lo_prestado_a_otra_compania(self):
        """El número que ve el comercial al buscar ya está neto de préstamos comprometidos.

        Reutiliza `enteza.disponibilidad.disponible()`, el mismo motor que `enteza_falta` y
        que la corrección de `virtual_available_at_date` (`_compute_qty_at_date`): si aquí se
        recalculara aparte, los tres números podrían discrepar entre sí.
        """
        otra = self.env['res.company'].create({'name': 'Prestamista Test'})
        self._dar_stock(900)
        self.env['enteza.stock.loan'].create({
            'name': 'PRE/TEST/BUSCADOR',
            'company_id': self.propia.id,
            'company_dest_id': otra.id,
            'warehouse_src_id': self.almacen.id,
            'warehouse_dest_id': self.env['stock.warehouse'].search(
                [('company_id', '=', otra.id)], limit=1,
            ).id,
            'state': 'reserved',
            'line_ids': [Command.create({
                'product_id': self.producto.id,
                'product_uom_id': self.producto.uom_id.id,
                'qty_reserved': 850,
                'date_from': self.desde,
                'date_to': self.hasta,
            })],
        })

        producto = self.producto.with_context(**self._contexto())
        self.assertEqual(producto.display_name, 'Silla plegable (test) - 50 uds.')

    # ------------------------------------------------------------------
    # Casos que se dejan sin tocar a propósito
    # ------------------------------------------------------------------

    def test_producto_no_almacenable_no_se_toca(self):
        servicio = self.env['product.product'].create({
            'name': 'Montaje (test)',
            'uom_id': self.env.ref('uom.product_uom_unit').id,
            'type': 'service',
            'company_id': False,
        })
        servicio = servicio.with_context(**self._contexto())
        self.assertEqual(servicio.display_name, 'Montaje (test)')

    def test_plantilla_con_varias_variantes_no_se_toca(self):
        """Con varias variantes, «disponible» no dice nada sin saber cuál."""
        atributo = self.env['product.attribute'].create({
            'name': 'Color (test)',
            'value_ids': [
                Command.create({'name': 'Blanca (test)'}),
                Command.create({'name': 'Negra (test)'}),
            ],
        })
        plantilla = self.env['product.template'].create({
            'name': 'Mesa plegable (test)',
            'uom_id': self.env.ref('uom.product_uom_unit').id,
            'rent_ok': True,
            'is_storable': True,
            'company_id': False,
            'attribute_line_ids': [Command.create({
                'attribute_id': atributo.id,
                'value_ids': [Command.set(atributo.value_ids.ids)],
            })],
        })
        self.assertEqual(len(plantilla.product_variant_ids), 2)

        plantilla = plantilla.with_context(**self._contexto())
        self.assertEqual(plantilla.display_name, 'Mesa plegable (test)')
