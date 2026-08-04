from collections import defaultdict
from datetime import date, datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, format_date, formatLang, html2plaintext

# Estados que no cuentan como evento: un pedido cancelado no lleva material a ningún sitio.
ESTADOS_EXCLUIDOS = ('cancel',)

# Lo que está vendido de verdad. Un presupuesto (`draft`/`sent`) todavía puede no ocurrir, así
# que el panel deja elegir si cuenta o no: por defecto se ve, pero marcado y con un interruptor
# para quitarlo del material, de la sobreventa y del parte que baja al almacén.
ESTADOS_CONFIRMADOS = ('sale',)

# Los tres días distintos que tiene un mismo pedido, y el campo que representa cada uno.
#
# No son intercambiables: `rental_custom` deja la salida la víspera del evento y la
# devolución el día siguiente, y los datos de `enteza26` lo confirman — de 1.156 pedidos,
# 1.090 salen el día antes y 985 vuelven el día después. Por eso el panel deja elegir: la
# oficina pregunta "qué eventos hay el sábado" y el almacén "qué cargo hoy".
MODOS = {
    'evento': 'event_date',
    'salida': 'rental_start_date',
    'devolucion': 'rental_return_date',
}


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # ------------------------------------------------------------------
    # API para el panel (client action OWL)
    # ------------------------------------------------------------------
    # Las agregaciones se hacen en Python sobre un `search_read`, no con `_read_group`.
    # Es deliberado: el volumen es pequeño (1.159 pedidos de alquiler en total, y un mes
    # son decenas) y así el código no depende de una firma de `_read_group` que en este
    # entorno no se puede probar. Si algún día el volumen crece, este es el sitio donde
    # cambiarlo, sin tocar el JS.

    @api.model
    def _enteza_panel_modo(self, modo):
        """Modo válido. Ante cualquier cosa rara que llegue del cliente, el del evento."""
        return modo if modo in MODOS else 'evento'

    @api.model
    def _enteza_panel_a_utc(self, dia):
        """Medianoche local de `dia` como datetime naive en UTC, que es como guarda Odoo.

        Sin esta conversión, un pedido que sale a las 23:30 del sábado en Madrid caería en
        el domingo del panel.
        """
        zona = pytz.timezone(self.env.context.get('tz') or self.env.user.tz or 'UTC')
        return zona.localize(
            datetime.combine(dia, time.min)
        ).astimezone(pytz.utc).replace(tzinfo=None)

    @api.model
    def _enteza_panel_clave(self, valor):
        """Fecha (`date`, `datetime` en UTC o cadena) a la clave `'AAAA-MM-DD'` local."""
        if isinstance(valor, str):
            if len(valor) <= 10:
                return valor
            valor = fields.Datetime.from_string(valor)
        # `datetime` hereda de `date`: hay que comprobarlo primero.
        if isinstance(valor, datetime):
            return fields.Datetime.context_timestamp(self, valor).date().isoformat()
        return fields.Date.to_string(valor)

    @api.model
    def _enteza_panel_dominio(self, modo, desde, hasta, solo_confirmados=False):
        """Pedidos de alquiler vivos cuyo día según `modo` cae en `[desde, hasta)`.

        Los límites llegan como `date`. En los dos modos de almacén el campo es un Datetime
        guardado en UTC, así que hay que traducirlos: el día del usuario no empieza a la
        misma hora que el día de la base de datos.
        """
        if solo_confirmados:
            estado = ('state', 'in', ESTADOS_CONFIRMADOS)
        else:
            estado = ('state', 'not in', ESTADOS_EXCLUIDOS)
        dominio = [('is_rental_order', '=', True), estado]
        campo = MODOS[modo]
        if modo == 'evento':
            return dominio + [
                (campo, '>=', fields.Date.to_string(desde)),
                (campo, '<', fields.Date.to_string(hasta)),
            ]
        return dominio + [
            (campo, '>=', fields.Datetime.to_string(self._enteza_panel_a_utc(desde))),
            (campo, '<', fields.Datetime.to_string(self._enteza_panel_a_utc(hasta))),
        ]

    @api.model
    def enteza_panel_carga_mes(self, anio, mes, modo='evento', solo_confirmados=False):
        """Carga de trabajo de cada día del mes, para colorear el calendario.

        Devuelve `{'2026-07-31': {'pedidos': 3, 'importe': '4.520,50 €'}, ...}`. Solo aparecen
        los días con al menos un pedido: el JS trata la ausencia como día vacío. El importe se
        usa en el tooltip de la celda, para poder comparar un sábado con otro sin abrirlos.
        """
        modo = self._enteza_panel_modo(modo)
        primero = date(anio, mes, 1)
        siguiente = date(anio + (mes == 12), mes % 12 + 1, 1)
        campo = MODOS[modo]

        pedidos = self.search_read(
            self._enteza_panel_dominio(modo, primero, siguiente, solo_confirmados),
            [campo, 'amount_total'],
        )

        carga = defaultdict(lambda: {'pedidos': 0, 'importe': 0.0})
        for pedido in pedidos:
            clave = self._enteza_panel_clave(pedido[campo])
            carga[clave]['pedidos'] += 1
            carga[clave]['importe'] += pedido['amount_total'] or 0.0

        moneda = self.env.company.currency_id
        return {
            clave: {
                'pedidos': dato['pedidos'],
                'importe': formatLang(self.env, dato['importe'], currency_obj=moneda),
            }
            for clave, dato in carga.items()
        }

    @api.model
    def _enteza_panel_pedidos(self, dia, modo, solo_confirmados=False):
        """Pedidos de un día concreto. `dia` llega del JS como cadena (`'2026-07-31'`)."""
        jornada = fields.Date.to_date(dia)
        orden = 'rental_return_date, name' if modo == 'devolucion' else 'rental_start_date, name'
        return self.search(
            self._enteza_panel_dominio(
                modo, jornada, jornada + timedelta(days=1), solo_confirmados
            ),
            order=orden,
        )

    @api.model
    def _enteza_panel_contadores(self, dia, solo_confirmados=False):
        """Cuántos pedidos tocan este día por cada uno de los tres motivos.

        Los tres números casi nunca coinciden, y ahí está el valor: enseñan de un vistazo
        que el trabajo de hoy en el almacén no es el de los eventos de hoy.
        """
        jornada = fields.Date.to_date(dia)
        siguiente = jornada + timedelta(days=1)
        return {
            modo: self.search_count(
                self._enteza_panel_dominio(modo, jornada, siguiente, solo_confirmados)
            )
            for modo in MODOS
        }

    @api.model
    def enteza_panel_dia(self, dia, modo='evento', solo_confirmados=False):
        """Pedidos, material y contadores de un día concreto."""
        modo = self._enteza_panel_modo(modo)
        solo_confirmados = bool(solo_confirmados)
        pedidos = self._enteza_panel_pedidos(dia, modo, solo_confirmados)
        articulos = pedidos._enteza_panel_datos_articulos(dia)
        return {
            'pedidos': pedidos._enteza_panel_datos_pedidos(),
            'articulos': articulos,
            # Los almacenes que aparecen en el día. El JS solo enseña la columna de almacén
            # cuando hay más de uno: con un solo almacén repetiría el mismo valor en todas
            # las filas y quitaría sitio a lo que sí cambia. Se miran los pedidos y no los
            # artículos, para que la columna no aparezca y desaparezca al filtrar.
            'almacenes': sorted(pedidos.warehouse_id.mapped('display_name')),
            'totales': {
                'pedidos': len(pedidos),
                'borradores': sum(
                    1 for pedido in pedidos if pedido.state not in ESTADOS_CONFIRMADOS
                ),
                'unidades': sum(articulo['unidades'] for articulo in articulos),
                'sobreventa': sum(1 for articulo in articulos if articulo['sobreventa']),
                'importe': formatLang(
                    self.env,
                    sum(pedidos.mapped('amount_total')),
                    currency_obj=self.env.company.currency_id,
                ),
            },
            'contadores': self._enteza_panel_contadores(dia, solo_confirmados),
        }

    @api.model
    def enteza_panel_accion_lista(self, dia, modo='evento', solo_confirmados=False):
        """Los mismos pedidos en una lista normal, para filtrar, agrupar y exportar.

        El dominio lo arma Python y no el JS a propósito: en los modos de almacén hay que
        convertir los límites del día a UTC, y esa conversión no debe estar en dos sitios.
        """
        modo = self._enteza_panel_modo(modo)
        jornada = fields.Date.to_date(dia)
        return {
            'type': 'ir.actions.act_window',
            'name': _("Pedidos de %s", format_date(self.env, jornada)),
            'res_model': 'sale.order',
            'domain': self._enteza_panel_dominio(
                modo, jornada, jornada + timedelta(days=1), bool(solo_confirmados)
            ),
            'views': [(False, 'list'), (False, 'form')],
            'target': 'current',
            'context': {'in_rental_app': 1},
        }

    @api.model
    def enteza_panel_imprimir(self, dia, modo='evento', solo_sobreventa=False,
                              solo_confirmados=False):
        """Parte del día en PDF, para bajarlo al almacén en papel.

        `solo_sobreventa` y `solo_confirmados` imprimen lo que se está viendo en pantalla: si
        el panel está en «Sobre venta», el papel sale como lista de lo que hay que comprar o
        subcontratar; si está en «Solo confirmados», el papel no lleva presupuestos.
        """
        modo = self._enteza_panel_modo(modo)
        solo_confirmados = bool(solo_confirmados)
        pedidos = self._enteza_panel_pedidos(dia, modo, solo_confirmados)
        if not pedidos:
            raise UserError(_("No hay nada que imprimir para este día."))
        # `config=False` evita que a un administrador sin plantilla de informe configurada
        # le salte el asistente de diseño en vez del parte.
        return self.env.ref('enteza_panel_eventos.action_parte_dia').report_action(
            pedidos,
            data={
                'dia': dia,
                'modo': modo,
                'solo_sobreventa': bool(solo_sobreventa),
                'solo_confirmados': solo_confirmados,
            },
            config=False,
        )

    # ------------------------------------------------------------------
    # Formato de las filas
    # ------------------------------------------------------------------

    def _enteza_panel_datos_pedidos(self):
        # `fields_get` en vez de leer `_fields[...].selection` directamente: es API pública,
        # devuelve la selección ya traducida al idioma del usuario y funciona igual si algún
        # módulo convierte la selección en un callable.
        etiquetas_estado = dict(
            self.env['sale.order'].fields_get(['rental_status'])['rental_status']['selection']
        )
        filas = []
        for pedido in self:
            # Cantidad de cada artículo en este pedido. Con esto el JS puede filtrar los
            # pedidos al pinchar un artículo sin volver al servidor —son decenas de pedidos
            # como mucho y la respuesta tiene que ser inmediata— y además enseñar cuántas
            # unidades lleva cada uno, que es la pregunta que viene justo después.
            unidades = defaultdict(float)
            for linea in pedido.order_line:
                if not linea.display_type and linea.product_id:
                    unidades[str(linea.product_id.id)] += linea.product_uom_qty

            filas.append({
                'id': pedido.id,
                'nombre': pedido.name,
                'cliente': pedido.partner_id.display_name or '',
                # El lugar de entrega solo aporta si difiere del cliente. Hoy en `enteza26`
                # coinciden en los 1.159 pedidos, así que la columna saldrá vacía hasta que
                # se informen direcciones de entrega propias.
                'lugar': (
                    pedido.partner_shipping_id.display_name
                    if pedido.partner_shipping_id != pedido.partner_id
                    else ''
                ),
                'evento': self._enteza_panel_fecha(pedido.event_date),
                'inicio': self._enteza_panel_fecha(pedido.rental_start_date),
                'fin': self._enteza_panel_fecha(pedido.rental_return_date),
                'estado': etiquetas_estado.get(pedido.rental_status, ''),
                'estado_tecnico': pedido.rental_status or '',
                # Un presupuesto sin confirmar todavía puede no ocurrir. Va marcado para que
                # nadie cargue un camión con material que nadie ha vendido.
                'confirmado': pedido.state in ESTADOS_CONFIRMADOS,
                'almacen': pedido.warehouse_id.display_name or '',
                'almacen_id': pedido.warehouse_id.id or 0,
                'comercial': pedido.user_id.name or '',
                'importe': formatLang(
                    self.env, pedido.amount_total, currency_obj=pedido.currency_id
                ),
                # `note` es el campo de términos y condiciones, no una nota del evento: en
                # `enteza26` solo 2 de 1.159 pedidos lo tienen informado. Por eso no ocupa
                # una columna, sino un indicador en la fila que enseña el texto al pasar.
                'notas': html2plaintext(pedido.note or '').strip(),
                'productos': dict(unidades),
            })
        return filas

    def _enteza_panel_datos_articulos(self, dia=None):
        """Líneas de todos los pedidos del día, agrupadas por almacén y artículo.

        Se excluyen las líneas de sección y de nota (`display_type`), que no son material.

        **Se agrupa por almacén, no solo por artículo**, porque las existencias son de un
        almacén concreto: una sobreventa en Jerez no se resuelve con material que está en
        Sevilla. Medido en `enteza26`: el producto 972 tiene 80 unidades en `SEV/Stock`
        (Vimaple) y 20 en `JER/Stock` (Stileum), y `qty_available` sin acotar devuelve 100.

        `dia` (opcional, `'AAAA-MM-DD'`) es lo que necesita `_enteza_panel_prestado` para
        acotar en el tiempo lo que la otra compañía tiene comprometido prestar. Sin `dia` no
        hay columna «Prestados»: hoy no ocurre porque los dos llamadores (`enteza_panel_dia`
        y el informe) siempre lo tienen.

        Cada fila trae `faltan` y `sobreventa`: `unidades - existencias - prestado`, y si ese
        resultado es positivo. Es lo que realmente le puede faltar al comercial para el
        evento, ya descontado lo que va a llegar prestado de la otra compañía. Por eso
        **no descuenta el material que está fuera por alquileres de días contiguos**: un
        alquiler del día 1 al 3 no resta en el día 2.
        """
        lineas = self.mapped('order_line').filtered(
            lambda linea: not linea.display_type and linea.product_id
        )

        acumulado = defaultdict(float)
        for linea in lineas:
            acumulado[(linea.order_id.warehouse_id, linea.product_id)] += linea.product_uom_qty

        existencias = self._enteza_panel_existencias(acumulado)
        prestado = self._enteza_panel_prestado(acumulado, dia) if dia else {}

        filas = []
        for (almacen, producto), unidades in acumulado.items():
            disponible = existencias.get((almacen.id, producto.id), 0.0)
            prestando = prestado.get((almacen.id, producto.id), 0.0)
            faltan = unidades - disponible - prestando
            filas.append({
                # Clave estable para el `t-key` del JS y para saber qué fila está pinchada:
                # el artículo solo identifica una fila junto con su almacén.
                'clave': f"{almacen.id or 0}-{producto.id}",
                'producto_id': producto.id,
                'almacen_id': almacen.id or 0,
                'almacen': almacen.display_name or '',
                'articulo': producto.display_name or '',
                'categoria': producto.categ_id.display_name or '',
                'unidades': unidades,
                # Saldrá 0 mientras el inventario esté sin cargar en `enteza26`. No es un
                # fallo del panel: apenas hay `stock.quant` con cantidad. Mientras siga así,
                # «Sobre venta» marcará casi todo.
                'existencias': disponible,
                # Reservado, aprobado o en tránsito en `enteza_prestamo_intercompania`:
                # comprometido por la otra compañía pero que TODAVÍA no ha entrado en este
                # almacén. En cuanto entra (estado `lent`) ya es stock físico propio y ya lo
                # cuenta `existencias`; sumarlo también aquí lo duplicaría.
                'prestado': prestando,
                'faltan': faltan,
                'sobreventa': float_compare(
                    faltan, 0.0,
                    precision_rounding=producto.uom_id.rounding or 0.01,
                ) > 0,
                'uom': producto.uom_id.display_name or '',
            })
        return sorted(filas, key=lambda fila: (fila['almacen'], fila['articulo']))

    @api.model
    def _enteza_panel_prestado(self, acumulado, dia):
        """Unidades que la otra compañía tiene comprometido prestarnos ese día, por
        `(almacén, producto)`.

        Solo cuenta lo que la prestamista tiene **reservado, aprobado o en tránsito**
        (`enteza.stock.loan`): comprometido, pero que aún no ha entrado en este almacén. En
        cuanto el préstamo pasa a `lent` el material ya es stock físico propio y ya lo cuenta
        `_enteza_panel_existencias`; sumarlo también aquí lo contaría dos veces.

        Se filtra por el día igual que las existencias filtran por almacén: un préstamo cuyo
        intervalo no toca este día no es material que vaya a llegar para este evento.
        """
        jornada = fields.Date.to_date(dia)
        inicio = self._enteza_panel_a_utc(jornada)
        fin = self._enteza_panel_a_utc(jornada + timedelta(days=1))

        almacenes = self.env['stock.warehouse']
        productos = self.env['product.product']
        for almacen, producto in acumulado:
            almacenes |= almacen
            productos |= producto
        if not almacenes or not productos:
            return {}

        # `sudo()`: una compañía tiene que ver que la otra le va a prestar material aunque la
        # regla de registro le oculte el documento del préstamo en sí — igual que
        # `_prestado_a_terceros` en `enteza_prestamo_intercompania`.
        lineas = self.env['enteza.stock.loan.line'].sudo().search([
            ('product_id', 'in', productos.ids),
            ('loan_id.warehouse_dest_id', 'in', almacenes.ids),
            ('loan_id.state', 'in', ('reserved', 'approved', 'in_transit')),
            ('date_from', '<', fin),
            ('date_to', '>', inicio),
        ])

        prestado = defaultdict(float)
        for linea in lineas:
            clave = (linea.loan_id.warehouse_dest_id.id, linea.product_id.id)
            prestado[clave] += linea._qty_comprometida()
        return prestado

    @api.model
    def _enteza_panel_existencias(self, acumulado):
        """Existencias de cada `(almacén, producto)` de `acumulado`, en una lectura por almacén.

        🔴 Dos cosas que hay que hacer aquí y que `qty_available` a secas no hace:

        1. **Acotar al almacén.** La clave de contexto en la 19 es `warehouse_id`; `warehouse`
           (la de versiones anteriores) se ignora en silencio y devuelve la suma de todos.
           Comprobado contra `enteza26` con el producto 972: sin contexto 100, con
           `warehouse_id=1` 80 y con `warehouse_id=2` 20.
        2. **Dejar fuera el material que está en un evento.** `Customers/Alquiler` tiene
           `usage='internal'`, así que cuenta como existencias aunque el material esté en
           casa de un cliente. Acotar al almacén ya lo resuelve: esa ubicación cuelga de
           `Customers`, no de la vista del almacén.

        Y se lee **en bloque por almacén**, no artículo a artículo: el día más cargado de
        `enteza26` (2026-05-02, 57 pedidos) tiene 389 productos distintos.
        """
        productos_por_almacen = defaultdict(lambda: self.env['product.product'])
        for almacen, producto in acumulado:
            productos_por_almacen[almacen] |= producto

        existencias = {}
        for almacen, productos in productos_por_almacen.items():
            ambito = productos.with_context(warehouse_id=almacen.id) if almacen else productos
            for dato in ambito.read(['qty_available']):
                existencias[(almacen.id, dato['id'])] = dato['qty_available']
        return existencias

    @api.model
    def _enteza_panel_fecha(self, valor):
        """Fecha corta con el día de la semana: `'sáb 01/08'`.

        Se muestra la fecha y no la hora a propósito: los 1.156 pedidos migrados tienen la
        hora a 00:00 sin excepción, así que una columna de horas repetiría el mismo valor en
        todas las filas. La fecha sí informa, porque la salida suele ser la víspera del
        evento y la devolución el día siguiente.

        `format_date` traduce el día de la semana al idioma del usuario y convierte los
        Datetime a su zona horaria por su cuenta.
        """
        if not valor:
            return ''
        return format_date(self.env, valor, date_format='EEE dd/MM')
