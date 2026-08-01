"""Motor de disponibilidad de material de alquiler.

Decisión de diseño (2026-08-01), tras analizar el código de `sale_renting` y
`sale_stock_renting` de la 18 EE
=====================================================================================

**No se reimplementa el cálculo de disponibilidad. Se delega en el nativo.**

El PRP §5 describe un motor propio con SQL agrupado, escrito bajo la premisa de que Odoo
no traía nada. Sí lo trae, y en `sale_stock_renting`, que está instalado en esta instancia
aunque el PRP §2.1 no lo liste:

- `product.product._get_unavailable_qty(desde, hasta, ignored_soline_id, warehouse_id)`
  hace ya el barrido por eventos con máximo del intervalo que pide el §5.3.
- `sale.order.line._get_rented_quantities()` ajusta además por **recogidas y devoluciones
  tempranas**, que el PRP no contempla.
- `ignored_soline_id` resuelve de fábrica el «excluir la línea que se está modificando»
  del §7.0.2.

Reimplementarlo daría al comercial dos cifras distintas para la misma pregunta: la de la
ficha del producto y la de este módulo. Eso no se sostiene en un equipo que además está
arrancando en Odoo 19 sin rodaje.

**Lo único propio es `_prestado_a_terceros`**: el nativo no sabe nada de préstamos, y sin
esa resta la compañía prestamista volvería a vender el material que ya ha comprometido.

Ámbito: almacén, no compañía
----------------------------
Todo el cálculo nativo se scopea por `warehouse_id`. Este módulo hace lo mismo. Hoy hay un
almacén por compañía y el resultado coincide con razonar por compañía, pero cuando se
definan los almacenes reales (`[PENDIENTE-1]`) no habrá que rehacer nada.

Rendimiento (limitación conocida)
---------------------------------
`_get_unavailable_qty` hace `ensure_one()` y una búsqueda por producto. Para el camino de
confirmación (decenas de líneas) va sobrado. Para el análisis por lotes de ~1.000 productos
del §7.1 **no se espera cumplir los 30 s de la prueba 7 del §15**. Es una limitación
aceptada a cambio de coherencia con el nativo. Si hiciera falta, la vía es añadir una
implementación agrupada DETRÁS de estos mismos métodos, sin tocar a quien los llama.
"""

import logging
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

from .enteza_stock_loan import ESTADOS_COMPROMETEN

_logger = logging.getLogger(__name__)


class EntezaDisponibilidad(models.AbstractModel):
    _name = 'enteza.disponibilidad'
    _description = 'Motor de cálculo de disponibilidad de alquiler'

    # ------------------------------------------------------------------
    # Fachada: la única entrada llamable desde fuera del servidor
    # ------------------------------------------------------------------

    @api.model
    def consultar(self, producto_ids, almacen_id, desde, hasta,
                  cantidades=None, ignorar_linea_id=False, ignorar_prestamo_ids=None):
        """Consulta de disponibilidad con argumentos que viajan por RPC.

        El resto de la API de este modelo trabaja con **recordsets y `datetime`**, que es lo
        cómodo desde dentro del servidor pero **no atraviesa una llamada RPC**: por ahí solo
        llegan ids y cadenas. Sin esta fachada el motor no se puede ejercitar de ninguna
        forma —no hay interfaz, no hay `--test-enable` en este hosting y los métodos internos
        no son llamables—, que es exactamente donde se quedó la fase 1.

        También es la entrada que necesitará la interfaz de la fase 2 (el widget de
        disponibilidad y el aviso al confirmar un pedido llaman desde el cliente web, con
        ids). Por eso vive aquí y no en un script suelto.

        :param producto_ids: lista de ids de `product.product`
        :param almacen_id: id del `stock.warehouse` desde el que se serviría
        :param desde, hasta: fecha y hora, en texto (`'2026-08-15 08:00:00'`) o `datetime`
        :param cantidades: opcional, `{product_id: cantidad}` necesaria. Si se pasa, cada
            línea incluye además `falta`
        :param ignorar_linea_id: id de `sale.order.line` a excluir (pedido que se modifica)
        :param ignorar_prestamo_ids: ids de `enteza.stock.loan` a excluir
        :return: lista de diccionarios, uno por producto, con `product_id`, `producto`,
            `disponible`, `prestable` y, si procede, `falta`. Se devuelve **lista y no
            diccionario** porque las claves numéricas de un dict se convierten en cadenas al
            serializar a JSON, y eso obliga a quien llama a deshacer la conversión.
        """
        almacen = self.env['stock.warehouse'].browse(almacen_id).exists()
        if not almacen:
            raise UserError(_('No existe el almacén con id %s.', almacen_id))

        desde = fields.Datetime.to_datetime(desde)
        hasta = fields.Datetime.to_datetime(hasta)
        if not desde or not hasta:
            raise UserError(_('Hay que indicar la fecha de inicio y la de fin.'))
        if hasta < desde:
            raise UserError(_('La fecha de fin es anterior a la de inicio.'))

        productos = self.env['product.product'].browse(producto_ids).exists()
        # El cálculo nativo solo tiene sentido sobre productos almacenables: es lo que filtra
        # `_compute_qty_at_date` antes de llamar al motor. Los demás se descartan aquí en vez
        # de dejar que fallen dentro, y se avisa de cuáles para que quien pregunte no crea
        # que se le ha respondido por todos.
        almacenables = productos.filtered('is_storable')
        descartados = productos - almacenables
        if descartados:
            _logger.info(
                'Disponibilidad: se ignoran %s productos no almacenables (%s)',
                len(descartados), descartados.ids,
            )
        if not almacenables:
            return []

        prestamos = self.env['enteza.stock.loan'].browse(ignorar_prestamo_ids or [])
        linea = self.env['sale.order.line'].browse(ignorar_linea_id) if ignorar_linea_id \
            else None

        opciones = {'ignorar_linea': linea, 'ignorar_prestamos': prestamos}
        disponible = self.disponible(almacenables, almacen, desde, hasta, **opciones)
        prestable = self.prestable(almacenables, almacen, desde, hasta, **opciones)
        faltas = {}
        if cantidades:
            # Las claves llegan como cadenas si el que llama las envió en un objeto JSON.
            cantidades = {int(pid): qty for pid, qty in cantidades.items()}
            faltas = self.deficit(
                almacenables, almacen, desde, hasta, cantidades, **opciones,
            )

        resultado = []
        for producto in almacenables:
            fila = {
                'product_id': producto.id,
                'producto': producto.display_name,
                'disponible': disponible[producto.id],
                'prestable': prestable[producto.id],
            }
            if cantidades:
                fila['necesita'] = cantidades.get(producto.id, 0.0)
                fila['falta'] = faltas.get(producto.id, 0.0)
            resultado.append(fila)
        return resultado

    # ------------------------------------------------------------------
    # API interna — recordsets y datetime
    # ------------------------------------------------------------------

    def disponible(self, productos, almacen, desde, hasta,
                   ignorar_linea=None, ignorar_prestamos=None):
        """Unidades de `productos` libres en `almacen` durante todo el intervalo.

        :param productos: recordset de `product.product`
        :param almacen: `stock.warehouse` desde el que se serviría
        :param desde, hasta: datetime del intervalo de alquiler
        :param ignorar_linea: `sale.order.line` a excluir del cálculo. Es lo que permite
            recalcular un pedido que se está modificando sin que se compita a sí mismo.
        :param ignorar_prestamos: `enteza.stock.loan` a excluir, para poder recalcular un
            préstamo existente sin contar su propia reserva.
        :return: `{product_id: cantidad}`. Puede ser negativo: eso es un déficit.
        """
        resultado = {}
        for producto in productos:
            rentable = self._rentable(producto, almacen, desde, hasta, ignorar_linea)
            alquilado = producto._get_unavailable_qty(
                desde, hasta,
                ignored_soline_id=ignorar_linea and ignorar_linea.id,
                warehouse_id=almacen.id,
            )
            prestado = self._prestado_a_terceros(
                producto, almacen, desde, hasta, ignorar_prestamos,
            )
            resultado[producto.id] = rentable - alquilado - prestado
        return resultado

    def prestable(self, productos, almacen, desde, hasta, **kwargs):
        """Cuánto puede prestar `almacen` sin quedarse corto ningún día del intervalo.

        Es `disponible` acotado a cero: un almacén en déficit no presta «en negativo».
        """
        disponible = self.disponible(productos, almacen, desde, hasta, **kwargs)
        return {pid: max(0.0, cantidad) for pid, cantidad in disponible.items()}

    def deficit(self, productos, almacen, desde, hasta, cantidades, **kwargs):
        """Cuánto falta para cubrir `cantidades` (`{product_id: cantidad}`).

        Devuelve solo los productos con déficit real.
        """
        disponible = self.disponible(productos, almacen, desde, hasta, **kwargs)
        # Misma precisión que usa `sale_renting` para comparar cantidades de alquiler.
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        faltas = {}
        for producto in productos:
            falta = cantidades.get(producto.id, 0.0) - disponible[producto.id]
            # Comparar con la precisión de la unidad y no con `> 0`: los arrastres de coma
            # flotante generarían déficits de 0,0000001 y propuestas de préstamo absurdas.
            if float_compare(falta, 0.0, precision_digits=precision) > 0:
                faltas[producto.id] = falta
        return faltas

    # ------------------------------------------------------------------
    # Cantidad rentable — réplica fiel del cálculo nativo
    # ------------------------------------------------------------------

    def _rentable(self, producto, almacen, desde, hasta, ignorar_linea=None):
        """Unidades del almacén sobre las que se puede montar un alquiler nuevo.

        ⚠️ Esto es una **réplica de `RentalOrderLine._compute_qty_at_date`**
        (`sale_stock_renting/models/sale_order_line.py`). Se replica en vez de llamarlo
        porque el nativo es un `compute` que necesita líneas de pedido existentes, y aquí
        se pregunta por un alquiler hipotético que todavía no existe.

        **Si Odoo cambia ese compute, hay que revisar este método.** Es la única deuda que
        deja delegar en el nativo.

        Los dos caminos y el porqué del ajuste, tal cual los razona Odoo:

        - Si el alquiler ya ha empezado, vale el stock a fecha.
        - Si es futuro, se usa el disponible previsto **al primer día** del alquiler. Odoo
          renuncia a propósito a buscar el mínimo de todo el periodo por rendimiento. Nota:
          el PRP §5.3 sí exige el mínimo, así que en escenarios con entradas y salidas
          previstas dentro del periodo este número puede ser optimista.
        - `_get_virtual_unavailable_qty_in_rent` **suma de vuelta** lo que el previsto ya
          había descontado por movimientos de alquiler planificados, para no restarlo dos
          veces con `_get_unavailable_qty`.
        """
        if desde <= fields.Datetime.now():
            return producto.with_context(
                from_date=desde, to_date=hasta, warehouse_id=almacen.id,
            ).qty_available

        rentable = producto.with_context(
            from_date=False, to_date=desde, warehouse_id=almacen.id,
        ).virtual_available
        rentable += producto._get_virtual_unavailable_qty_in_rent(
            pivot_date=desde,
            ignored_soline_id=ignorar_linea and ignorar_linea.id,
            warehouse_id=almacen.id,
        )
        return rentable

    # ------------------------------------------------------------------
    # Material comprometido para prestar — lo único que el nativo no sabe
    # ------------------------------------------------------------------

    def _prestado_a_terceros(self, producto, almacen, desde, hasta, ignorar_prestamos=None):
        """Pico de material que `almacen` tiene comprometido para prestar en el intervalo.

        🔴 Es imprescindible y es fácil de olvidar. Si el material que un almacén ha
        reservado para prestar al otro no cuenta como comprometido en el suyo, lo venderá
        otra vez y se reproduce exactamente el problema que este módulo viene a resolver,
        un nivel más arriba. **Una reserva de préstamo pesa igual que un pedido propio.**

        Solo cuentan los estados de `ESTADOS_COMPROMETEN`: a partir de `in_transit` la
        salida ya está validada, el material ya no está en el almacén y el descuento lo
        refleja el propio stock.

        Las cantidades se toman tal cual, sin convertir de unidad de medida: es lo mismo
        que hace `_get_rented_quantities` con `product_uom_qty`. Las líneas de préstamo se
        crean en la unidad de referencia del producto para que ambos casen. El caso 7 del
        §12 (artículos en docenas) queda pendiente y hay que resolverlo a la vez en los dos
        sitios, no solo aquí.
        """
        dominio = [
            ('product_id', '=', producto.id),
            ('warehouse_src_id', '=', almacen.id),
            ('state', 'in', ESTADOS_COMPROMETEN),
            ('date_from', '<=', hasta),
            ('date_to', '>=', desde),
        ]
        if ignorar_prestamos:
            dominio.append(('loan_id', 'not in', ignorar_prestamos.ids))

        # `sudo()` acotado a esta lectura. Un usuario de la compañía receptora tiene que
        # ver reflejado que la prestamista ya tiene material comprometido, aunque la regla
        # de registro le oculte ese préstamo concreto. Sin esto el cálculo daría distinto
        # según quién lo ejecutase, que es la peor clase de error posible aquí.
        lineas = self.env['enteza.stock.loan.line'].sudo().search(dominio)
        if not lineas:
            return 0.0

        # Mismo barrido que `_get_unavailable_qty`: se acumula el saldo por eventos y se
        # mide el pico dentro del intervalo consultado.
        movimientos = defaultdict(float)
        for linea in lineas:
            cantidad = linea._qty_comprometida()
            movimientos[linea.date_from] += cantidad
            movimientos[linea.date_to] -= cantidad

        fechas = sorted(movimientos)
        acumulado = 0.0
        indice = 0

        # 🔴 Primero hay que llegar al nivel que YA está vigente cuando empieza el intervalo.
        # Un préstamo que arranca antes de `desde` y acaba después de `hasta` no tiene ningún
        # evento dentro del intervalo: si solo se midiera en los eventos interiores, contaría
        # como cero y la prestamista volvería a vender material ya comprometido, que es
        # exactamente lo que este método existe para impedir.
        #
        # El nativo resuelve esto mismo por otra vía, y es el detalle que se perdió al
        # replicar su barrido: `_get_rented_quantities(mandatory_dates)` mete `from_date` y
        # `to_date` en la lista de fechas de interés
        # (`sorted(set(rented_quantities) | set(mandatory_dates))`), así que en su bucle
        # SIEMPRE hay un evento en `from_date` donde medir el nivel arrastrado. Aquí se hace
        # explícito con este primer recorrido; el resultado es el mismo.
        #
        # Los eventos que caen justo en `desde` entran aquí: los intervalos se tratan como
        # semiabiertos `[date_from, date_to)`, así que un préstamo que termina en `desde`
        # libera el material y otro que empieza en `desde` ya lo compromete.
        while indice < len(fechas) and fechas[indice] <= desde:
            acumulado += movimientos[fechas[indice]]
            indice += 1

        maximo = acumulado

        # A partir de ahí, cada cambio dentro del intervalo puede elevar el pico.
        while indice < len(fechas) and fechas[indice] <= hasta:
            acumulado += movimientos[fechas[indice]]
            maximo = max(maximo, acumulado)
            indice += 1

        return maximo
