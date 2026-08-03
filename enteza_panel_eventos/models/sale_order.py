from collections import defaultdict
from datetime import date, datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, format_date, formatLang, html2plaintext

# Estados que no cuentan como evento: un pedido cancelado no lleva material a ningún sitio.
ESTADOS_EXCLUIDOS = ('cancel',)

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
    # Es deliberado: el volumen es pequeño (1.156 pedidos de alquiler en total, y un mes
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
    def _enteza_panel_dominio(self, modo, desde, hasta):
        """Pedidos de alquiler vivos cuyo día según `modo` cae en `[desde, hasta)`.

        Los límites llegan como `date`. En los dos modos de almacén el campo es un Datetime
        guardado en UTC, así que hay que traducirlos: el día del usuario no empieza a la
        misma hora que el día de la base de datos.
        """
        dominio = [
            ('is_rental_order', '=', True),
            ('state', 'not in', ESTADOS_EXCLUIDOS),
        ]
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
    def enteza_panel_carga_mes(self, anio, mes, modo='evento'):
        """Carga de trabajo de cada día del mes, para colorear el calendario.

        Devuelve `{'2026-07-31': {'pedidos': 3, 'importe': 4520.5}, ...}`. Solo aparecen los
        días con al menos un pedido: el JS trata la ausencia como día vacío.
        """
        modo = self._enteza_panel_modo(modo)
        primero = date(anio, mes, 1)
        siguiente = date(anio + (mes == 12), mes % 12 + 1, 1)
        campo = MODOS[modo]

        pedidos = self.search_read(
            self._enteza_panel_dominio(modo, primero, siguiente),
            [campo, 'amount_total'],
        )

        carga = defaultdict(lambda: {'pedidos': 0, 'importe': 0.0})
        for pedido in pedidos:
            clave = self._enteza_panel_clave(pedido[campo])
            carga[clave]['pedidos'] += 1
            carga[clave]['importe'] += pedido['amount_total'] or 0.0
        return dict(carga)

    @api.model
    def _enteza_panel_pedidos(self, dia, modo):
        """Pedidos de un día concreto. `dia` llega del JS como cadena (`'2026-07-31'`)."""
        jornada = fields.Date.to_date(dia)
        orden = 'rental_return_date, name' if modo == 'devolucion' else 'rental_start_date, name'
        return self.search(
            self._enteza_panel_dominio(modo, jornada, jornada + timedelta(days=1)),
            order=orden,
        )

    @api.model
    def _enteza_panel_contadores(self, dia):
        """Cuántos pedidos tocan este día por cada uno de los tres motivos.

        Los tres números casi nunca coinciden, y ahí está el valor: enseñan de un vistazo
        que el trabajo de hoy en el almacén no es el de los eventos de hoy.
        """
        jornada = fields.Date.to_date(dia)
        siguiente = jornada + timedelta(days=1)
        return {
            modo: self.search_count(self._enteza_panel_dominio(modo, jornada, siguiente))
            for modo in MODOS
        }

    @api.model
    def enteza_panel_dia(self, dia, modo='evento'):
        """Pedidos, material y contadores de un día concreto."""
        modo = self._enteza_panel_modo(modo)
        pedidos = self._enteza_panel_pedidos(dia, modo)
        articulos = pedidos._enteza_panel_datos_articulos()
        return {
            'pedidos': pedidos._enteza_panel_datos_pedidos(),
            'articulos': articulos,
            'totales': {
                'pedidos': len(pedidos),
                'unidades': sum(articulo['unidades'] for articulo in articulos),
                'sobreventa': sum(1 for articulo in articulos if articulo['sobreventa']),
                'importe': formatLang(
                    self.env,
                    sum(pedidos.mapped('amount_total')),
                    currency_obj=self.env.company.currency_id,
                ),
            },
            'contadores': self._enteza_panel_contadores(dia),
        }

    @api.model
    def enteza_panel_accion_lista(self, dia, modo='evento'):
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
            'domain': self._enteza_panel_dominio(modo, jornada, jornada + timedelta(days=1)),
            'views': [(False, 'list'), (False, 'form')],
            'target': 'current',
            'context': {'in_rental_app': 1},
        }

    @api.model
    def enteza_panel_imprimir(self, dia, modo='evento', solo_sobreventa=False):
        """Parte del día en PDF, para bajarlo al almacén en papel.

        `solo_sobreventa` imprime lo que se está viendo en pantalla: si el panel está en
        «Sobre venta», el papel sale como lista de lo que hay que comprar o subcontratar.
        """
        modo = self._enteza_panel_modo(modo)
        pedidos = self._enteza_panel_pedidos(dia, modo)
        if not pedidos:
            raise UserError(_("No hay nada que imprimir para este día."))
        # `config=False` evita que a un administrador sin plantilla de informe configurada
        # le salte el asistente de diseño en vez del parte.
        return self.env.ref('enteza_panel_eventos.action_parte_dia').report_action(
            pedidos,
            data={'dia': dia, 'modo': modo, 'solo_sobreventa': bool(solo_sobreventa)},
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
            filas.append({
                'id': pedido.id,
                'nombre': pedido.name,
                'cliente': pedido.partner_id.display_name or '',
                # El lugar de entrega solo aporta si difiere del cliente. Hoy en `enteza26`
                # coinciden en los 1.156 pedidos, así que la columna saldrá vacía hasta que
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
                'importe': formatLang(
                    self.env, pedido.amount_total, currency_obj=pedido.currency_id
                ),
                'notas': html2plaintext(pedido.note or '').strip(),
                # Artículos que lleva el pedido. Con esto el JS puede filtrar los pedidos al
                # pinchar un artículo sin volver al servidor: son decenas de pedidos como
                # mucho, y la respuesta tiene que ser inmediata para que sirva de algo.
                'productos': pedido.order_line.filtered(
                    lambda linea: not linea.display_type and linea.product_id
                ).product_id.ids,
            })
        return filas

    def _enteza_panel_datos_articulos(self):
        """Líneas de todos los pedidos del día, agrupadas por artículo.

        Se excluyen las líneas de sección y de nota (`display_type`), que no son material.

        Cada fila trae `sobreventa`: el día compromete más unidades de las que hay en el
        almacén, así que ese material hay que comprarlo o subcontratarlo. La regla es la
        misma que usaba la aplicación anterior (unidades del día contra existencias), y por
        eso **no descuenta el material que está fuera por alquileres de días contiguos**:
        un alquiler del día 1 al 3 no resta en el día 2.
        """
        lineas = self.mapped('order_line').filtered(
            lambda linea: not linea.display_type and linea.product_id
        )

        acumulado = defaultdict(float)
        for linea in lineas:
            acumulado[linea.product_id] += linea.product_uom_qty

        filas = []
        for producto, unidades in acumulado.items():
            existencias = producto.qty_available
            filas.append({
                'id': producto.id,
                'articulo': producto.display_name or '',
                'categoria': producto.categ_id.display_name or '',
                'unidades': unidades,
                # Saldrá 0 mientras el inventario esté sin cargar en `enteza26`. No es un
                # fallo del panel: apenas hay `stock.quant` con cantidad. Mientras siga así,
                # «Sobre venta» marcará casi todo.
                'existencias': existencias,
                'sobreventa': float_compare(
                    unidades, existencias,
                    precision_rounding=producto.uom_id.rounding or 0.01,
                ) > 0,
                'uom': producto.uom_id.display_name or '',
            })
        return sorted(filas, key=lambda fila: fila['articulo'])

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
