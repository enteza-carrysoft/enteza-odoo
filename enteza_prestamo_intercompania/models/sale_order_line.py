"""Aviso de déficit y de préstamo posible en la línea de pedido de alquiler.

Para qué es esto (PRP §10.3)
----------------------------
El widget nativo de disponibilidad **oculta justo lo que el comercial necesita saber**. El
campo que enseña, `virtual_available_at_date`, está acotado a cero en el propio Odoo
(`sale_stock_renting`, `_compute_qty_at_date`):

    virtual_available_at_date = max(rentable_qty - rented_qty_during_period, 0)

Así que quien pide 95 unidades teniendo 80 lee «Disponible para alquilar: 80» y se queda
igual: no ve que faltan 15, ni que la otra compañía las tiene, ni que al confirmar se le va a
proponer un préstamo. Estos tres campos son los que rellenan ese hueco.

🔴 La cifra sale del MISMO motor que decide la reserva
------------------------------------------------------
`enteza.disponibilidad` es la única fuente. Si el widget dijera «Stileum presta 15» y al
confirmar se reservara otra cosa, el comercial dejaría de fiarse de los dos números — y es la
misma razón por la que el motor delega en el nativo en vez de reimplementarlo.

Por eso NO se usa `virtual_available_at_date` como atajo para saber si hay déficit, aunque
sería gratis: el nativo no descuenta los préstamos ya comprometidos, así que diría que hay 80
libres cuando 30 están reservadas para la otra compañía. Un prefiltro optimista **esconde
déficits reales**, que es exactamente el fallo que este módulo existe para impedir.
"""

import logging

from odoo import _, api, fields, models
from odoo.tools import float_compare, float_is_zero

_logger = logging.getLogger(__name__)


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    enteza_falta = fields.Float(
        string='Falta en el almacén propio', compute='_compute_enteza_prestamo',
        digits='Product Unit of Measure',
        help='Unidades que este almacén no puede servir en las fechas del alquiler. '
             'A diferencia del disponible nativo, puede ser mayor que cero aunque el '
             'nativo muestre 0: descuenta también lo comprometido para préstamos.',
    )
    enteza_prestable_otra = fields.Float(
        string='Puede prestar la otra compañía', compute='_compute_enteza_prestamo',
        digits='Product Unit of Measure',
    )
    enteza_origen_prestamo = fields.Char(
        string='Quién lo presta', compute='_compute_enteza_prestamo',
        help='Compañía y almacén desde los que se propondrá el préstamo al confirmar.',
    )

    @api.depends(
        'product_id', 'product_uom_qty', 'is_rental', 'start_date', 'return_date',
        'order_id.warehouse_id',
    )
    def _compute_enteza_prestamo(self):
        motor = self.env['enteza.disponibilidad']
        for linea in self:
            linea.enteza_falta = 0.0
            linea.enteza_prestable_otra = 0.0
            linea.enteza_origen_prestamo = False

            almacen = linea.order_id.warehouse_id
            if not (linea.is_rental and linea.product_id.is_storable and almacen
                    and linea.start_date and linea.return_date):
                # Mismo criterio que el nativo, que descarta los no almacenables antes de
                # llamar al motor. Sin fechas no hay pregunta que hacer.
                continue

            disponible = motor.disponible(
                linea.product_id, almacen, linea.start_date, linea.return_date,
                ignorar_linea=linea,
            )[linea.product_id.id]

            falta = linea.product_uom_qty - disponible
            if float_compare(falta, 0.0, precision_rounding=linea.product_uom_id.rounding) <= 0:
                # Se sirve con lo propio: no se toca nada más. Este corte es el que mantiene
                # el coste a raya —la consulta a la otra compañía es la cara— y es también lo
                # que hace que el widget se comporte como el nativo en el caso normal.
                continue

            linea.enteza_falta = falta
            prestable, origen = linea._enteza_buscar_prestamista(falta)
            linea.enteza_prestable_otra = prestable
            linea.enteza_origen_prestamo = origen

    def _enteza_buscar_prestamista(self, falta):
        """Busca en las compañías del grupo quién puede cubrir `falta`.

        Devuelve `(prestable, descripción)`. `prestable` se acota a lo que falta: al comercial
        no le sirve saber que la otra compañía tiene 500 libres, le sirve saber que sus 15
        están cubiertas.

        🔴 `sudo()` deliberado y acotado a esta lectura. Un comercial de Vimaple no tiene
        acceso a los quants de Stileum, y sin esto el widget le diría «no hay nada» en vez de
        «Stileum lo presta»: un cálculo que da distinto según quién lo mire, que es la peor
        clase de error posible aquí. Se expone **la cifra agregada, nunca los registros**.
        Mismo criterio que `_prestado_a_terceros` en el motor.
        """
        self.ensure_one()
        # Todos los almacenes que NO son de la compañía del pedido. No se asume «la otra
        # compañía» en singular ni un almacén por sociedad: el cliente ha confirmado que
        # habrá más almacenes (`[PENDIENTE-1]`).
        almacenes = self.env['stock.warehouse'].sudo().search([
            ('company_id', '!=', self.order_id.company_id.id),
        ])
        if not almacenes:
            return 0.0, False

        motor = self.env['enteza.disponibilidad'].sudo()
        mejor_qty = 0.0
        mejor_almacen = None
        for almacen in almacenes:
            # `with_company` porque `preparation_time` (el padding del alquiler) es
            # company_dependent: el que vale es el de la compañía que presta, no el de quien
            # está mirando la pantalla.
            producto = self.product_id.sudo().with_company(almacen.company_id)
            prestable = motor.with_company(almacen.company_id).prestable(
                producto, almacen, self.start_date, self.return_date,
            )[producto.id]
            # Regla por defecto del `[PENDIENTE-1]`: gana el almacén con más prestable y, a
            # igualdad, el de menor id (`search` ya devuelve ordenado). Vive solo aquí, así
            # que cambiarla el día que el cliente decida otra cosa no toca nada más.
            if float_compare(prestable, mejor_qty,
                             precision_rounding=self.product_uom_id.rounding) > 0:
                mejor_qty = prestable
                mejor_almacen = almacen

        if not mejor_almacen or float_is_zero(
            mejor_qty, precision_rounding=self.product_uom_id.rounding
        ):
            return 0.0, False

        return min(mejor_qty, falta), _(
            '%(compania)s · %(almacen)s',
            compania=mejor_almacen.company_id.display_name,
            almacen=mejor_almacen.display_name,
        )
