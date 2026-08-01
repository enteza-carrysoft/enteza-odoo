from collections import defaultdict
from datetime import date

from odoo import api, fields, models
from odoo.tools import formatLang, html2plaintext

# Estados que no cuentan como evento: un pedido cancelado no lleva material a ningún sitio.
ESTADOS_EXCLUIDOS = ('cancel',)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # ------------------------------------------------------------------
    # API para el panel (client action OWL)
    # ------------------------------------------------------------------
    # Las agregaciones se hacen en Python sobre un `search_read`, no con `_read_group`.
    # Es deliberado: el volumen es pequeño (1.153 pedidos de alquiler en total, y un mes
    # son decenas) y así el código no depende de una firma de `_read_group` que en este
    # entorno no se puede probar. Si algún día el volumen crece, este es el sitio donde
    # cambiarlo, sin tocar el JS.

    @api.model
    def _enteza_panel_dominio_base(self):
        return [
            ('is_rental_order', '=', True),
            ('state', 'not in', ESTADOS_EXCLUIDOS),
            ('event_date', '!=', False),
        ]

    @api.model
    def enteza_panel_carga_mes(self, anio, mes):
        """Carga de trabajo de cada día del mes, para colorear el calendario.

        Devuelve `{'2026-07-31': {'pedidos': 3, 'importe': 4520.5}, ...}`. Solo aparecen los
        días con al menos un pedido: el JS trata la ausencia como día vacío.
        """
        primero = date(anio, mes, 1)
        ultimo = date(anio + (mes == 12), mes % 12 + 1, 1)

        pedidos = self.search_read(
            self._enteza_panel_dominio_base() + [
                ('event_date', '>=', fields.Date.to_string(primero)),
                ('event_date', '<', fields.Date.to_string(ultimo)),
            ],
            ['event_date', 'amount_total'],
        )

        carga = defaultdict(lambda: {'pedidos': 0, 'importe': 0.0})
        for pedido in pedidos:
            # `search_read` devuelve los Date como objeto `date`, pero no en todas las rutas
            # (un override podría serializarlo). Se admiten las dos formas.
            valor = pedido['event_date']
            clave = valor if isinstance(valor, str) else fields.Date.to_string(valor)
            carga[clave]['pedidos'] += 1
            carga[clave]['importe'] += pedido['amount_total'] or 0.0
        return dict(carga)

    @api.model
    def enteza_panel_dia(self, dia):
        """Pedidos y material de un día concreto.

        `dia` llega del JS como cadena ISO (`'2026-07-31'`).
        """
        pedidos = self.search(
            self._enteza_panel_dominio_base() + [('event_date', '=', dia)],
            order='rental_start_date, name',
        )
        return {
            'pedidos': pedidos._enteza_panel_datos_pedidos(),
            'articulos': pedidos._enteza_panel_datos_articulos(),
            'totales': {
                'pedidos': len(pedidos),
                'importe': formatLang(
                    self.env,
                    sum(pedidos.mapped('amount_total')),
                    currency_obj=self.env.company.currency_id,
                ),
            },
        }

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
                # coinciden en los 1.153 pedidos, así que la columna saldrá vacía hasta que
                # se informen direcciones de entrega propias.
                'lugar': (
                    pedido.partner_shipping_id.display_name
                    if pedido.partner_shipping_id != pedido.partner_id
                    else ''
                ),
                'hora': self._enteza_panel_hora(pedido.rental_start_date),
                'estado': etiquetas_estado.get(pedido.rental_status, ''),
                'estado_tecnico': pedido.rental_status or '',
                'importe': formatLang(
                    self.env, pedido.amount_total, currency_obj=pedido.currency_id
                ),
                'notas': html2plaintext(pedido.note or '').strip(),
            })
        return filas

    def _enteza_panel_datos_articulos(self):
        """Líneas de todos los pedidos del día, agrupadas por artículo.

        Se excluyen las líneas de sección y de nota (`display_type`), que no son material.
        """
        lineas = self.mapped('order_line').filtered(
            lambda linea: not linea.display_type and linea.product_id
        )

        acumulado = defaultdict(float)
        for linea in lineas:
            acumulado[linea.product_id] += linea.product_uom_qty

        filas = []
        for producto, unidades in acumulado.items():
            filas.append({
                'id': producto.id,
                'articulo': producto.display_name or '',
                'categoria': producto.categ_id.display_name or '',
                'unidades': unidades,
                # Saldrá 0 mientras el inventario esté sin cargar en `enteza26`. No es un
                # fallo del panel: `stock.quant` está vacío.
                'existencias': producto.qty_available,
                'uom': producto.uom_id.display_name or '',
            })
        return sorted(filas, key=lambda fila: fila['articulo'])

    @api.model
    def _enteza_panel_hora(self, momento):
        """Hora en la zona horaria del usuario, no en UTC."""
        if not momento:
            return ''
        return fields.Datetime.context_timestamp(self, momento).strftime('%H:%M')
