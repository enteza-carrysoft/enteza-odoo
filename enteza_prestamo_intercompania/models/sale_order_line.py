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

🔴 El propio `virtual_available_at_date` también miente (bug detectado en pruebas con cliente,
2026-08-04)
--------------------------------------------------------------------------------------------
Lo de arriba es sobre el CÁLCULO propio (`enteza_falta`), que siempre fue correcto. El
problema es otro: el número que el comercial VE en el popover nativo — «Disponible para
alquilar X Uds» — es justo ese `virtual_available_at_date`, y **nunca se tocaba**. Así que si
Stileum le presta 15 a Vimaple (`reserved`), un comercial que monta un pedido NUEVO en Stileum
para ese mismo artículo y esas fechas seguía viendo el disponible de siempre, sin las 15 ya
prestadas: el icono rojo de `enteza_falta` avisaba bien si el nuevo pedido se pasaba, pero el
número base que lo alimentaba visualmente estaba inflado.

`_compute_qty_at_date()` de más abajo corrige esto: llama a `super()` (el cálculo nativo
íntegro, fórmula en `sale_stock_renting`) y le resta `_prestado_a_terceros` del motor, con el
mismo suelo en cero que ya aplica el nativo. Es la MISMA fuente que `enteza_falta`, así que
los dos números — el disponible que se ve y el aviso de préstamo — no pueden discrepar.

No sustituye a `enteza_falta`: ese sigue haciendo falta para decir QUIÉN presta y para el
diálogo de confirmación. Esto solo corrige el número que el nativo ya mostraba, que hasta
ahora era el único dato de la pantalla que no pasaba por `enteza.disponibilidad`.
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
    # El almacén, y no solo su nombre, porque el diálogo de confirmación necesita el registro
    # para crear el préstamo. Sale del MISMO cálculo que la cifra que ve el comercial: es lo
    # que garantiza que se reserve exactamente de donde el widget dijo que se reservaría.
    enteza_almacen_prestamista_id = fields.Many2one(
        'stock.warehouse', string='Almacén prestamista propuesto',
        compute='_compute_enteza_prestamo',
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
            linea.enteza_almacen_prestamista_id = False

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

            falta = linea.product_uom_qty - disponible - linea._enteza_cubierto_por_prestamo()
            if float_compare(falta, 0.0, precision_rounding=linea.product_uom_id.rounding) <= 0:
                # Se sirve con lo propio: no se toca nada más. Este corte es el que mantiene
                # el coste a raya —la consulta a la otra compañía es la cara— y es también lo
                # que hace que el widget se comporte como el nativo en el caso normal.
                continue

            linea.enteza_falta = falta
            prestable, almacen_origen = linea._enteza_buscar_prestamista(falta)
            linea.enteza_prestable_otra = prestable
            linea.enteza_almacen_prestamista_id = almacen_origen
            linea.enteza_origen_prestamo = almacen_origen and _(
                '%(compania)s · %(almacen)s',
                compania=almacen_origen.company_id.display_name,
                almacen=almacen_origen.display_name,
            )

    @api.depends(
        # Los mismos de `sale_stock_renting` (`reservation_begin`, `return_date`,
        # `product_id`) más el almacén: es el que decide qué compañía es la prestamista y
        # `_prestado_a_terceros` cambia si el pedido se pasa a otro almacén.
        'reservation_begin', 'return_date', 'product_id', 'order_id.warehouse_id',
    )
    def _compute_qty_at_date(self):
        """Descuenta del disponible NATIVO lo que este almacén ya tiene prestado.

        Bug detectado en pruebas con cliente el 2026-08-04: Vimaple confirma un pedido que
        Stileum le cubre con un préstamo `reserved`; al montar DESPUÉS un pedido nuevo en
        Stileum para el mismo artículo y las mismas fechas, el popover «Disponible para
        alquilar» seguía enseñando el disponible de siempre, sin las unidades ya prometidas a
        Vimaple. Ver la cabecera del fichero para el porqué completo.

        Se llama a `super()` primero — la fórmula nativa completa de
        `RentalOrderLine._compute_qty_at_date`, verificada contra el código de la 18 EE
        (`sale_stock_renting/models/sale_order_line.py`, no confirmable por RPC al ser
        privada) y contra los campos de la 19 por RPC (`virtual_available_at_date`,
        `free_qty_today`, no almacenados) — y se corrige el resultado encima, nunca al
        revés: así una línea normal, sin préstamos de por medio, se comporta exactamente
        como el nativo.

        Se tocan los DOS campos que lee el popover en presupuesto (`draft`/`sent`):
        `virtual_available_at_date` y `free_qty_today`, confirmado leyendo
        `sale_stock/static/src/widgets/qty_at_date_widget.xml` de la 19 (módulo Community,
        público). El nativo ya los deja iguales entre sí para una línea de alquiler
        (`RentalOrderLine._compute_qty_at_date` los fija los dos al mismo
        `virtual_available_at_date`), así que se corrigen igual.
        """
        super()._compute_qty_at_date()
        motor = self.env['enteza.disponibilidad']
        for linea in self:
            almacen = linea.order_id.warehouse_id
            if not (linea.is_rental and linea.product_id.is_storable and almacen
                    and linea.start_date and linea.return_date):
                # Mismo criterio que el nativo y que `_compute_enteza_prestamo`: sin fechas
                # o almacén no hay préstamo que pueda estar pesando sobre esta línea.
                continue

            # `_prestado_a_terceros` y no `disponible()`: ya se tiene el «rentable -
            # alquilado» nativo recién calculado por el `super()` de arriba, y volver a
            # pedírselo al motor sería repetir la misma cuenta dos veces para llegar al
            # mismo sitio.
            prestado = motor._prestado_a_terceros(
                linea.product_id, almacen, linea.start_date, linea.return_date,
            )
            if not prestado:
                continue

            # Mismo suelo en cero que aplica el nativo (`max(rentable - alquilado, 0)`):
            # `max(max(a, 0) - b, 0) == max(a - b, 0)` para `b >= 0`, así que restar aquí
            # DESPUÉS del suelo nativo da el mismo número que si el préstamo se hubiera
            # descontado dentro de la fórmula desde el principio.
            corregido = max(linea.virtual_available_at_date - prestado, 0.0)
            linea.virtual_available_at_date = corregido
            linea.free_qty_today = corregido

    def write(self, vals):
        """Reducir la cantidad de una línea confirmada libera su parte del préstamo (§7.0.2).

        Solo la **reducción**. Ampliar un pedido ya confirmado necesita volver a pasar por el
        cálculo de déficit y por el diálogo de D5.1, y eso todavía no está: por ahora el icono
        de la línea se pondrá rojo y habrá que resolverlo a mano. Está anotado en el README.

        Las cantidades se leen **antes** de `super()`, que es cuando todavía se sabe cuánto
        había.
        """
        reducciones = []
        if 'product_uom_qty' in vals:
            nueva = vals['product_uom_qty']
            for linea in self:
                if linea.state != 'sale' or not linea.is_rental:
                    continue
                quitado = linea.product_uom_qty - nueva
                if float_compare(quitado, 0.0,
                                 precision_rounding=linea.product_uom_id.rounding) > 0:
                    reducciones.append((linea, quitado))

        # §12, caso 2: cambiar las fechas de un pedido confirmado mueve el intervalo de la
        # reserva, y en las fechas nuevas puede no haber material aunque lo hubiera en las
        # viejas. No se supone que si valía antes vale ahora.
        cambian_fechas = {'start_date', 'return_date'} & set(vals)
        afectadas = self.env['sale.order.line']
        if cambian_fechas:
            afectadas = self.filtered(
                lambda linea: linea.state == 'sale' and linea.is_rental
            )

        resultado = super().write(vals)

        if afectadas:
            afectadas._enteza_reajustar_fechas_prestamo()

        for linea, quitado in reducciones:
            linea._enteza_liberar_prestamo(cantidad=quitado, motivo=_(
                'Se ha reducido en %(cantidad)s la línea de %(producto)s del pedido '
                '%(pedido)s.',
                cantidad=quitado,
                producto=linea.product_id.display_name,
                pedido=linea.order_id.name,
            ))
        return resultado

    def _enteza_reajustar_fechas_prestamo(self):
        """Las fechas del pedido han cambiado: el préstamo tiene que enterarse (§12, caso 2).

        - Si el préstamo sigue **reservado**, se mueven las fechas de su línea y se revalida
          contra las nuevas. Si en esas fechas no hay material, salta el error y el cambio de
          fecha se deshace entero: es preferible a confirmar un pedido que no se puede servir.
        - Si ya está **aprobado o en marcha**, no se toca: hay un viaje programado y puede que
          albaranes impresos. Se marca para revisión, que es lo que pide el §12.
        """
        for linea in self:
            lineas_prestamo = self.env['enteza.stock.loan.line'].sudo().search([
                ('sale_line_id', '=', linea.id),
            ])
            for prestamo in lineas_prestamo.loan_id:
                if prestamo.state in ('cancelled', 'returned'):
                    continue
                suyas = lineas_prestamo.filtered(lambda lin: lin.loan_id == prestamo)
                if prestamo.state != 'reserved':
                    prestamo._marcar_para_revision(_(
                        'El pedido %(pedido)s ha cambiado de fechas (%(desde)s a %(hasta)s) '
                        'y este traslado ya estaba aprobado.',
                        pedido=linea.order_id.name,
                        desde=linea.start_date, hasta=linea.return_date,
                    ))
                    continue
                suyas.write({
                    'date_from': linea.start_date,
                    'date_to': linea.return_date,
                })
                prestamo.date_transfer = prestamo._fecha_traslado()
                prestamo._revalidar_disponibilidad()

    def _enteza_liberar_prestamo(self, cantidad=None, motivo=''):
        """Retira de los préstamos vivos lo que estas líneas tenían comprometido.

        `cantidad` a `None` es «todo» (cancelación); con un número, esa cantidad (reducción).

        `sudo()` porque el préstamo pertenece a la compañía prestamista y quien cancela el
        pedido es de la receptora: sin él no vería el documento que tiene que liberar, y el
        material se quedaría comprometido sin que nadie se enterara.
        """
        for linea in self:
            lineas_prestamo = self.env['enteza.stock.loan.line'].sudo().search(
                [('sale_line_id', '=', linea.id)], order='id',
            )
            for prestamo in lineas_prestamo.loan_id:
                suyas = lineas_prestamo.filtered(
                    lambda lin: lin.loan_id == prestamo
                )
                prestamo._enteza_liberar(suyas, cantidad=cantidad, motivo=motivo)
                # El pedido deja de figurar como origen si ya no aporta ninguna línea: si no,
                # el préstamo seguiría apuntando a un pedido que ya no tiene nada que ver.
                if prestamo.exists() and not prestamo.line_ids.filtered(
                    lambda lin: lin.sale_line_id.order_id == linea.order_id
                ):
                    prestamo.origin_order_ids = [(3, linea.order_id.id)]

    def _enteza_cubierto_por_prestamo(self):
        """Unidades que un préstamo ya comprometido aporta para esta línea.

        🔴 Sin esta resta, en cuanto el enganche de `action_confirm` cree el préstamo la línea
        **seguiría avisando de que faltan 15 aunque ya estuvieran resueltas**: el material lo
        pone la OTRA compañía, así que la disponibilidad del almacén propio no cambia y el
        cálculo de arriba no se entera por sí solo.

        Se cuenta desde `reserved`: es cuando el material queda comprometido de verdad. Un
        préstamo en `draft` es una propuesta y no cubre nada; uno cancelado, tampoco.
        """
        self.ensure_one()
        if not self.id:
            return 0.0
        # `sudo()`: el préstamo pertenece a la compañía prestamista y la regla de registro
        # puede ocultárselo a quien mira el pedido. Se lee solo la cantidad.
        lineas = self.env['enteza.stock.loan.line'].sudo().search([
            ('sale_line_id', '=', self.id),
            ('state', 'not in', ('draft', 'cancelled')),
        ])
        # `qty_sent` como respaldo para los estados en los que el material ya salió y la
        # reserva pudo ajustarse a la baja.
        return sum((linea._qty_comprometida() or linea.qty_sent) for linea in lineas)

    def _enteza_buscar_prestamista(self, falta):
        """Busca en las compañías del grupo quién puede cubrir `falta`.

        Devuelve `(prestable, almacén)`. `prestable` se acota a lo que falta: al comercial
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
        vacio = self.env['stock.warehouse']
        almacenes = self.env['stock.warehouse'].sudo().search([
            ('company_id', '!=', self.order_id.company_id.id),
        ])
        if not almacenes:
            return 0.0, vacio

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
            return 0.0, vacio

        # El almacén se devuelve SIN `sudo()`: quien lo reciba decide con qué permisos lo usa.
        # Dejar un registro con superusuario paseándose por el resto del código es la forma
        # habitual de que un `sudo()` acotado deje de estarlo.
        return min(mejor_qty, falta), mejor_almacen.sudo(False)
