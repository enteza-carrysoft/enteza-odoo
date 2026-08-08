"""Solicitud de pedido desde el portal — la solicitud ES un `sale.order` (PRP §2.2).

Nada de esto crea un modelo paralelo: un `sale.order` en `draft` con `is_rental_order=True`
ya es, literalmente, un presupuesto de alquiler. Lo único que añade este módulo es un campo
de estado del canal portal y una foto de lo que el cliente pidió, para poder enseñarle el
diff cuando el comercial contrapropone (PRP §11).

Todos los métodos `_enteza_portal_*` asumen que quien los llama (el controlador, tras
comprobar la propiedad del pedido) ya ha hecho `.sudo()` sobre el recordset de entrada: el
grupo Portal no tiene acceso de escritura sobre `sale.order` ni de lectura sobre
`product.product` (verificado por RPC, PRP §8.2), así que sin ese sudo previo estos métodos
no podrían ni leer el catálogo.

🔴 **PRP v2 (2026-08-08, `PRP-PORTAL-PEDIDOS-V2-REPARACION.md`)**: este fichero incorpora la
reparación de los tres síntomas reportados (repintado al teclear, fallo al grabar, fallo al
enviar) y las cuatro decisiones D1-D4 tomadas con el usuario. El cambio de fondo es el
guardado: de escritura incremental por línea con bloqueo optimista por `write_date`
(inviable: crear una línea puede tocar la cabecera vía `rental_custom._get_pricelist_price`
→ `_rental_set_dates`, moviendo el candado que la propia petición usa) a **guardado
idempotente del cesto completo** en `_enteza_portal_guardar`.
"""
import math
from datetime import datetime, time, timedelta

import pytz
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # Hora de negocio para las fechas derivadas de `event_date` (D2) y para los ajustes
    # manuales del cliente: nunca se deja que Odoo complete un `Datetime` con 00:00 UTC
    # (PRP v2 §5.9f — con esa hora, la entrega "significa" las 02:00 en España y no cuadra
    # con nada real).
    _ENTEZA_PORTAL_HORA_ENTREGA = time(8, 0)
    _ENTEZA_PORTAL_HORA_RETIRADA = time(20, 0)

    enteza_portal_ref = fields.Char(
        string="Referencia de solicitud", copy=False, index=True, readonly=True,
        help="Referencia visible para el cliente. Se asigna al enviar la solicitud desde "
             "el portal. No sustituye al número de presupuesto.")

    enteza_portal_state = fields.Selection(
        selection=[
            ('none', "No es del portal"),
            ('composing', "El cliente la está montando"),
            ('submitted', "Enviada por el cliente"),
            ('reviewing', "En revisión del comercial"),
            ('counter', "Contrapropuesta enviada"),
            ('closed', "Cerrada"),
        ],
        string="Estado en el portal", default='none', copy=False, index=True, tracking=True)

    enteza_portal_snapshot = fields.Json(
        string="Solicitud original del cliente", copy=False, readonly=True,
        help="Foto de las líneas tal como las envió el cliente. Se usa para mostrarle el "
             "diff cuando el comercial contrapropone.")

    enteza_portal_customer_note = fields.Text(
        string="Comentario del cliente", copy=False, tracking=True)

    enteza_portal_submitted_on = fields.Datetime(
        string="Enviada el", copy=False, readonly=True)

    enteza_portal_line_count = fields.Integer(
        string="Líneas", compute='_compute_enteza_portal_line_count', store=True,
        help="Nº de líneas con producto, para verlo de un vistazo en la lista de "
             "solicitudes sin tener que abrir el pedido.")

    _enteza_portal_ref_uniq = models.UniqueIndex(
        '(enteza_portal_ref) WHERE enteza_portal_ref IS NOT NULL')

    @api.depends('order_line.product_id')
    def _compute_enteza_portal_line_count(self):
        for pedido in self:
            pedido.enteza_portal_line_count = len(
                pedido.order_line.filtered('product_id'))

    # ------------------------------------------------------------------
    # Creación / recuperación de la solicitud en curso (PRP §5, §8.1)
    # ------------------------------------------------------------------

    @api.model
    def _enteza_portal_get_or_create(self, partner):
        """Solicitud en `composing` de `partner`, o crea una nueva si no existe.

        Una sola solicitud en composición por cliente a la vez (PRP §5): si ya existe se
        devuelve la misma en vez de crear otra. `partner` siempre es
        `request.env.user.partner_id` — el propio usuario logado —, así que no hay
        comprobación de propiedad que hacer: por construcción no puede pedirse la de otro.

        🔴 D3 (PRP v2): el almacén NO se elige desde el portal, es siempre
        `partner.enteza_portal_warehouse_id`. El controlador comprueba que existe ANTES de
        llamar aquí (`controllers/portal.py`); este método no tiene fallback a "cualquier
        almacén" — asignar uno arbitrario entre Sevilla (Vimaple) y Jerez (Stileum) sería
        peor que no crear nada, porque cambia de sociedad sin que nadie lo decida.
        """
        existente = self.sudo().search([
            ('partner_id', '=', partner.id),
            ('enteza_portal_state', '=', 'composing'),
        ], limit=1, order='id desc')
        if existente:
            return existente

        almacen = partner.enteza_portal_warehouse_id
        vals = self._enteza_portal_vals_nueva_solicitud(partner, almacen)
        return self.sudo().with_context(in_rental_app=True).create(vals)

    def _enteza_portal_vals_nueva_solicitud(self, partner, almacen):
        """Valores comunes para crear una solicitud nueva (PRP v2 D1, D3).

        🔴 D1: si el cliente no tiene comercial propio (`partner.user_id`), se asigna el
        comercial por defecto de la compañía (`res.company.enteza_portal_user_id`).
        Verificado por RPC el 2026-08-08: el único cliente con portal (`AGRIPINA`) no tiene
        comercial. Sin este campo, el aviso de la solicitud se lo habría mandado a sí mismo
        -el pedido se crea con `sudo()`, pero `sudo()` mantiene el `uid`: `self.env.user`
        sigue siendo el usuario del portal.
        """
        comercial = partner.user_id or almacen.company_id.enteza_portal_user_id
        vals = {
            'partner_id': partner.id,
            'company_id': almacen.company_id.id,
            'warehouse_id': almacen.id,
            'enteza_portal_state': 'composing',
        }
        if comercial:
            vals['user_id'] = comercial.id
        return vals

    def action_enteza_portal_repetir(self):
        """Solicitud nueva copiando las líneas de un pedido pasado (PRP §9.4).

        Cantidades incluidas, fechas vacías: el cliente solo tiene que revisarlas y enviar.
        Solo copia material físico de alquiler — los servicios (fianza, portes...) se
        renegocian aparte en cada evento.

        🔴 PRP v2 §5.7 / F3: si el cliente ya tiene una solicitud en `composing`, NO se crea
        otra (rompía la invariante "una sola solicitud en composición" — la anterior quedaba
        huérfana e invisible). Se reutiliza esa misma, reemplazando sus líneas por las del
        pedido de origen. El aviso de que esto reemplaza el contenido actual lo hace la
        interfaz antes de llamar aquí (confirmación en el navegador).
        """
        self.ensure_one()
        lineas_copiables = self.order_line.filtered(
            lambda l: l.product_id and l.product_id.rent_ok and l.product_id.type == 'consu'
        )

        destino = self.sudo().search([
            ('partner_id', '=', self.partner_id.id),
            ('enteza_portal_state', '=', 'composing'),
        ], limit=1, order='id desc')

        if not destino:
            almacen = self.partner_id.enteza_portal_warehouse_id or self.warehouse_id
            vals = self._enteza_portal_vals_nueva_solicitud(self.partner_id, almacen)
            destino = self.sudo().with_context(in_rental_app=True).create(vals)
        else:
            destino.order_line.filtered(lambda l: l.product_id).sudo().unlink()

        for linea in lineas_copiables:
            self.env['sale.order.line'].sudo().with_context(in_rental_app=True).create({
                'order_id': destino.id,
                'product_id': linea.product_id.id,
                'product_uom_qty': linea.product_uom_qty,
                'product_uom_id': linea.product_uom_id.id,
                'is_rental': True,
            })
        return destino

    # ------------------------------------------------------------------
    # Guardas de estado
    # ------------------------------------------------------------------

    def _enteza_portal_check_composing(self):
        self.ensure_one()
        if self.enteza_portal_state != 'composing':
            raise UserError(_(
                "Esta solicitud ya no se puede editar (estado actual: %s).",
                dict(self._fields['enteza_portal_state'].selection).get(
                    self.enteza_portal_state),
            ))

    # ------------------------------------------------------------------
    # Cabecera (PRP §8.2 /cabecera, §8.3) — D2, D3
    # ------------------------------------------------------------------

    def _enteza_portal_fecha_local(self, valor):
        """UTC de Odoo → fecha local del usuario (PRP §14#16).

        Los `Datetime` de Odoo están en UTC; España va +2 en verano. Recortar la hora sobre
        el valor UTC da el día equivocado de madrugada — ya mordió una vez en este proyecto,
        con pedidos que se veían un día tarde.
        """
        if not valor:
            return False
        return fields.Datetime.context_timestamp(self, valor).date().isoformat()

    def _enteza_portal_fecha_negocio(self, fecha, hora):
        """`date` + hora de negocio en la zona del usuario → `Datetime` UTC para escribir.

        Sustituye a dejar que Odoo complete un `<input type="date">` con `00:00 UTC`
        (PRP v2 §5.9f): esa hora no significa nada de verdad -en España cuadraba de
        milagro-, y la hora de entrega/retirada es información real para el almacén.
        """
        tz = pytz.timezone(self.env.user.tz or 'Europe/Madrid')
        local = tz.localize(datetime.combine(fecha, hora))
        return fields.Datetime.to_string(local.astimezone(pytz.UTC).replace(tzinfo=None))

    def _enteza_portal_payload_cabecera(self):
        self.ensure_one()
        moneda = self.currency_id or self.company_id.currency_id
        return {
            'id': self.id,
            'ref': self.enteza_portal_ref or False,
            'state': self.enteza_portal_state,
            'event_date': fields.Date.to_string(self.event_date) if self.event_date else False,
            'pickup_date': self._enteza_portal_fecha_local(self.rental_start_date),
            'return_date': self._enteza_portal_fecha_local(self.rental_return_date),
            'warehouse_name': self.warehouse_id.name or '',
            'semaforo_activo': self.company_id.enteza_portal_semaforo,
            'dias_minimos': self.company_id.enteza_portal_dias_minimos,
            'customer_note': self.enteza_portal_customer_note or '',
            'currency': {
                'symbol': moneda.symbol,
                'position': moneda.position,
                'decimals': moneda.decimal_places,
            },
        }

    def _enteza_portal_escribir_header(self, header):
        """Valida y escribe la cabecera. Devuelve una lista de avisos que NO bloquean
        (p.ej. antelación mínima insuficiente) — el primer problema que SÍ bloquea se lanza
        como `UserError` (PRP v2 §7.3: un error cada vez, no un muro).

        🔴 D2: el cliente indica solo `event_date`. Entrega y retirada se DERIVAN en el
        servidor (evento ∓ 1 día, mismo criterio que `rental_custom.event_date_change` en
        el backend) salvo que el cliente las haya ajustado a mano («ajustar» en la
        interfaz), en cuyo caso `header` trae `pickup_date`/`return_date` explícitos.
        """
        self.ensure_one()
        avisos = []

        if 'event_date' not in header:
            return avisos

        event_date_str = header.get('event_date')
        if not event_date_str:
            self.write({'event_date': False})
            return avisos

        event_date = fields.Date.from_string(event_date_str)

        pickup_override = header.get('pickup_date')
        return_override = header.get('return_date')
        pickup_date_obj = (
            fields.Date.from_string(pickup_override) if pickup_override
            else event_date - timedelta(days=1)
        )
        return_date_obj = (
            fields.Date.from_string(return_override) if return_override
            else event_date + timedelta(days=1)
        )

        if pickup_date_obj > return_date_obj:
            raise UserError(_(
                "La fecha de entrega no puede ser posterior a la de retirada."))
        if not (pickup_date_obj <= event_date <= return_date_obj):
            raise UserError(_(
                "La fecha del evento tiene que estar entre la entrega y la retirada."))

        self.write({
            'event_date': event_date,
            'rental_start_date': self._enteza_portal_fecha_negocio(
                pickup_date_obj, self._ENTEZA_PORTAL_HORA_ENTREGA),
            'rental_return_date': self._enteza_portal_fecha_negocio(
                return_date_obj, self._ENTEZA_PORTAL_HORA_RETIRADA),
        })

        dias_minimos = self.company_id.enteza_portal_dias_minimos
        if dias_minimos:
            antelacion = (pickup_date_obj - fields.Date.context_today(self)).days
            if antelacion < dias_minimos:
                avisos.append(_(
                    "Pides el material con %(dias)s día(s) de antelación; lo habitual son "
                    "al menos %(minimos)s. Puede que no dé tiempo a prepararlo — el "
                    "comercial lo revisará igualmente.",
                    dias=max(antelacion, 0), minimos=dias_minimos))

        return avisos

    # ------------------------------------------------------------------
    # Catálogo (PRP §8.3)
    # ------------------------------------------------------------------

    def _enteza_portal_productos_habituales(self):
        """Ids de producto que el cliente ya alquiló alguna vez, en los últimos 24 meses
        (PRP §9.4; PRP v2 §5.9g: antes era un `search_read` sin límite de TODO el histórico
        en cada carga del catálogo).
        """
        self.ensure_one()
        desde = fields.Date.to_string(fields.Date.context_today(self) - relativedelta(months=24))
        grupos = self.env['sale.order.line'].sudo().read_group(
            domain=[
                ('order_id.partner_id', 'child_of', self.partner_id.commercial_partner_id.id),
                ('order_id.state', '=', 'sale'),
                ('order_id.date_order', '>=', desde),
                ('product_id', '!=', False),
            ],
            fields=['product_id'],
            groupby=['product_id'],
        )
        return {grupo['product_id'][0] for grupo in grupos if grupo['product_id']}

    def _enteza_portal_catalogo_valido(self):
        """Productos que el portal sirve de verdad (PRP §8.3): recordset, no ids sueltos,
        para poder usarse tanto en el payload como en la reconciliación de líneas.

        🔴 `type='consu'` además de `rent_ok`: hay artículos de servicio marcados como
        alquilables (fianza, portes, precio por plaza...) que no son material de camión.
        """
        self.ensure_one()
        return self.env['product.product'].sudo().search([
            ('rent_ok', '=', True),
            ('type', '=', 'consu'),
            ('enteza_portal_ok', '=', True),
            ('active', '=', True),
        ])

    def _enteza_portal_payload_catalogo(self):
        """Catálogo completo servido de una vez (PRP §2.3, §8.3): se filtra en el navegador."""
        self.ensure_one()
        productos = self._enteza_portal_catalogo_valido()

        habituales = self._enteza_portal_productos_habituales()

        categorias = {}
        etiquetas_usadas = set()
        filas_producto = []
        for producto in productos:
            if producto.categ_id:
                categorias[producto.categ_id.id] = producto.categ_id.name
            # Solo etiquetas con dimensión asignada y visibles al cliente (§4.4): las
            # internas («revisar», «lote 2019») no tienen `enteza_facet_id` o no tienen
            # `visible_to_customers`, y por eso no llegan aquí.
            etiquetas_visibles = producto.product_tag_ids.filtered(
                lambda tag: tag.visible_to_customers and tag.enteza_facet_id
            )
            etiquetas_usadas.update(etiquetas_visibles.ids)
            filas_producto.append({
                'id': producto.id,
                'code': producto.default_code or '',
                'name': producto.display_name,
                'category_id': producto.categ_id.id or False,
                'tag_ids': etiquetas_visibles.ids,
                'uom': producto.uom_id.name,
                'box': producto.enteza_units_per_box or 0,
                'price': producto.lst_price,
                'habitual': producto.id in habituales,
            })

        # Solo las facetas que, tras aplicar visibilidad, se quedan con algún valor
        # realmente usado por el catálogo servido: un desplegable vacío es ruido (§8.3).
        facetas_payload = []
        for faceta in self.env['enteza.product.facet'].sudo().search(
                [('portal_visible', '=', True)]):
            tags = faceta.tag_ids.filtered(
                lambda tag: tag.visible_to_customers and tag.id in etiquetas_usadas
            )
            if not tags:
                continue
            facetas_payload.append({
                'id': faceta.id,
                'name': faceta.name,
                'multi': faceta.multi,
                'tags': [{'id': tag.id, 'name': tag.name} for tag in tags],
            })

        return {
            'order': self._enteza_portal_payload_cabecera(),
            'categories': [{'id': cid, 'name': nombre} for cid, nombre in categorias.items()],
            'facets': facetas_payload,
            'products': filas_producto,
            'lines': self._enteza_portal_payload_lineas(),
            'totals': self._enteza_portal_payload_totales(),
        }

    def _enteza_portal_payload_lineas(self):
        self.ensure_one()
        return [{
            'line_id': linea.id,
            'product_id': linea.product_id.id,
            'qty': linea.product_uom_qty,
            'subtotal': linea.price_subtotal,
        } for linea in self.order_line if linea.product_id]

    def _enteza_portal_payload_totales(self):
        self.ensure_one()
        return {
            'untaxed': self.amount_untaxed,
            'tax': self.amount_tax,
            'total': self.amount_total,
        }

    # ------------------------------------------------------------------
    # Cajas y múltiplos (PRP §7)
    # ------------------------------------------------------------------

    def _enteza_portal_check_multiplo(self, producto, qty):
        """`None` si `qty` es válida para el packaging de `producto`; si no, los dos
        redondeos propuestos. Sin packaging (`enteza_units_per_box == 0`), cualquier
        cantidad es válida: no se le aplica ninguna restricción de múltiplo (PRP §2.6).
        """
        multiplo = producto.enteza_units_per_box or 0.0
        if not multiplo or qty <= 0:
            return None
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        n_cajas_cercano = round(qty / multiplo)
        if float_compare(n_cajas_cercano * multiplo, qty, precision_digits=precision) == 0:
            return None
        return {
            'product_id': producto.id,
            'product_name': producto.display_name,
            'qty': qty,
            'box': multiplo,
            'round_down': math.floor(qty / multiplo) * multiplo,
            'round_up': math.ceil(qty / multiplo) * multiplo,
        }

    # ------------------------------------------------------------------
    # Guardado idempotente del cesto completo (PRP v2 §2.2, §9) — F1
    # ------------------------------------------------------------------

    def _enteza_portal_reconciliar_lineas(self, lines, warnings):
        """Reconcilia el cesto COMPLETO contra las líneas existentes: crea, actualiza y
        BORRA lo que ya no esté en `lines` (PRP v2 §9) — `lines` es el estado entero, no un
        delta. Ignora en silencio productos que no cumplan el filtro del catálogo servido
        (nunca se acepta un producto que el portal no serviría) y lo anota en `warnings`.

        :param warnings: lista donde se acumulan avisos que NO bloquean (se modifica in situ).
        :return: avisos de múltiplo de caja, uno por producto con la cantidad mal redondeada.
        """
        self.ensure_one()
        Product = self.env['product.product'].sudo()
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        lineas_por_producto = {l.product_id.id: l for l in self.order_line if l.product_id}
        catalogo_valido_ids = set(self._enteza_portal_catalogo_valido().ids)

        cesto = {}
        ignorados = False
        for item in lines:
            pid = item.get('product_id')
            qty = float(item.get('qty') or 0.0)
            if not pid or qty <= 0:
                continue
            if pid not in catalogo_valido_ids:
                ignorados = True
                continue
            cesto[pid] = qty

        if ignorados:
            warnings.append(_(
                "Algunos artículos de tu cesto ya no están disponibles en el portal y no "
                "se han guardado."))

        for pid in list(lineas_por_producto):
            if pid not in cesto:
                lineas_por_producto.pop(pid).unlink()

        box_warnings = []
        for pid, qty in cesto.items():
            linea = lineas_por_producto.get(pid)
            if linea:
                if float_compare(linea.product_uom_qty, qty, precision_digits=precision) != 0:
                    linea.write({'product_uom_qty': qty})
            else:
                producto = Product.browse(pid)
                linea = self.env['sale.order.line'].sudo().with_context(
                    in_rental_app=True
                ).create({
                    'order_id': self.id,
                    'product_id': pid,
                    'product_uom_qty': qty,
                    'product_uom_id': producto.uom_id.id,
                    # El portal solo sirve productos `rent_ok`, así que este valor siempre
                    # es correcto — no se depende de que `in_rental_app` fije un default en
                    # la línea, porque verificado por RPC el 2026-08-08 no lo hace.
                    'is_rental': True,
                })
                lineas_por_producto[pid] = linea

            aviso = self._enteza_portal_check_multiplo(linea.product_id, qty)
            if aviso:
                box_warnings.append(aviso)

        return box_warnings

    def _enteza_portal_guardar(self, header=None, lines=None, customer_note=None):
        """Guardado idempotente del cesto completo. **El método central de F1.**

        Sustituye a los antiguos `_enteza_portal_actualizar_cabecera` /
        `_enteza_portal_actualizar_lineas`, que escribían incrementalmente y arbitraban la
        escritura con un bloqueo optimista por `write_date` que la propia maquinaria de
        alquiler invalidaba sola: crear una línea de alquiler dispara
        `rental_custom.SaleOrderLine._get_pricelist_price` → `order_id._rental_set_dates()`,
        que puede escribir en la cabecera y mover el `write_date` que la misma petición
        estaba usando como candado.

        Llamar dos veces con el mismo cesto dos veces deja el mismo resultado: es la
        propiedad que hace segura la reconexión tras un fallo de red o un doble clic — el
        bloqueo optimista sobra porque ya no hace falta detectar una carrera, todo el estado
        se reconcilia en cada llamada.

        :return: payload autoritativo `{order, lines, totals, warnings, box_warnings}`.
        """
        self.ensure_one()
        self._enteza_portal_check_composing()

        warnings = []
        if header:
            warnings += self._enteza_portal_escribir_header(header)
        if customer_note is not None:
            self.enteza_portal_customer_note = customer_note

        box_warnings = []
        if lines is not None:
            box_warnings = self._enteza_portal_reconciliar_lineas(lines, warnings)

        return {
            'order': self._enteza_portal_payload_cabecera(),
            'lines': self._enteza_portal_payload_lineas(),
            'totals': self._enteza_portal_payload_totales(),
            'warnings': warnings,
            'box_warnings': box_warnings,
        }

    # ------------------------------------------------------------------
    # Disponibilidad por lotes (PRP §6.2, §8.2 /disponibilidad)
    # ------------------------------------------------------------------

    def _enteza_portal_disponibilidad(self, items):
        """Semáforo por lotes, máximo 50 productos por llamada (PRP §6.2).

        🔴 PRP v2: recibe `items = [{product_id, qty}]` -la cantidad tecleada por producto-
        en vez de leerla de la línea en base de datos: con guardado diferido (F1), esa
        cantidad puede no estar escrita todavía cuando el cliente pide el semáforo.

        Nunca devuelve la cantidad libre: solo el color. Si el semáforo está desactivado, o
        faltan fechas/almacén, se devuelve `grey` para todo sin consultar el motor de
        disponibilidad.
        """
        self.ensure_one()
        items = list(items)[:50]

        if not self.company_id.enteza_portal_semaforo:
            return {item.get('product_id'): 'grey' for item in items}
        if not (self.warehouse_id and self.rental_start_date and self.rental_return_date):
            return {item.get('product_id'): 'grey' for item in items}

        Product = self.env['product.product'].sudo()
        almacen = self.warehouse_id
        desde, hasta = self.rental_start_date, self.rental_return_date
        lineas_por_producto = {l.product_id.id: l for l in self.order_line}

        resultado = {}
        for item in items:
            pid = item.get('product_id')
            producto = Product.browse(pid)
            if not producto.exists():
                resultado[pid] = 'grey'
                continue
            qty = float(item.get('qty') or 0.0)
            linea = lineas_por_producto.get(pid)
            resultado[pid] = producto._enteza_portal_semaforo(
                qty, desde, hasta, almacen, ignorar_linea=linea)
        return resultado

    # ------------------------------------------------------------------
    # Envío (PRP §4.1) — guardado + envío atómicos (PRP v2 §2.2, §5.4)
    # ------------------------------------------------------------------

    def action_enteza_portal_submit(self, header=None, lines=None, customer_note=None):
        """Guarda el cesto completo y envía, en una sola transacción. Idempotente: un
        doble clic del cliente no debe duplicar ni la referencia ni el aviso — si la
        solicitud ya no está en `composing`, se devuelve el estado actual sin repetir nada.

        🔴 PRP v2: recibe el cesto (antes solo `customer_note`) precisamente para eliminar
        la carrera entre "guardar" y "enviar" del diseño anterior: ya no hay una escritura
        previa cuyo resultado (`write_date`) el envío tenga que validar contra sí mismo.
        """
        self.ensure_one()
        if self.enteza_portal_state != 'composing':
            return self._enteza_portal_payload_cabecera()

        self._enteza_portal_guardar(header=header, lines=lines, customer_note=customer_note)

        if not (self.event_date and self.rental_start_date and self.rental_return_date):
            raise UserError(_(
                "Faltan datos del evento: indica la fecha del evento antes de enviar la "
                "solicitud."))
        if not self.warehouse_id:
            raise UserError(_(
                "No tienes un almacén asignado para servirte. Contacta con tu comercial "
                "antes de continuar."))

        lineas = self.order_line.filtered(lambda l: l.product_id and l.product_uom_qty > 0)
        if not lineas:
            raise UserError(_(
                "La solicitud está vacía: indica alguna cantidad antes de enviarla."))

        violaciones = [
            aviso for linea in lineas
            for aviso in [self._enteza_portal_check_multiplo(
                linea.product_id, linea.product_uom_qty)]
            if aviso
        ]
        if violaciones:
            detalle = '\n'.join(
                _("· %(nombre)s: pediste %(qty)g, la caja son %(box)g uds. — "
                  "propuestas: %(abajo)g o %(arriba)g",
                  nombre=v['product_name'], qty=v['qty'], box=v['box'],
                  abajo=v['round_down'], arriba=v['round_up'])
                for v in violaciones
            )
            raise UserError(_(
                "Hay artículos cuya cantidad no es múltiplo de caja completa. Ajusta la "
                "cantidad antes de enviar:\n\n%s", detalle))

        semaforo_activo = self.company_id.enteza_portal_semaforo
        almacen, desde, hasta = self.warehouse_id, self.rental_start_date, self.rental_return_date
        lineas_rojas = []
        for linea in lineas:
            color = (
                linea.product_id._enteza_portal_semaforo(
                    linea.product_uom_qty, desde, hasta, almacen, ignorar_linea=linea)
                if semaforo_activo else 'grey'
            )
            linea.write({
                'enteza_portal_availability': color,
                'enteza_portal_availability_date': fields.Datetime.now(),
            })
            if color == 'red':
                lineas_rojas.append(linea.product_id.display_name)

        referencia = self.env['ir.sequence'].sudo().next_by_code('enteza.portal.pedido')
        snapshot = {
            'submitted_on': fields.Datetime.to_string(fields.Datetime.now()),
            'event_date': fields.Date.to_string(self.event_date),
            'pickup_date': fields.Datetime.to_string(self.rental_start_date),
            'return_date': fields.Datetime.to_string(self.rental_return_date),
            'warehouse_id': self.warehouse_id.id,
            'lines': [{
                'product_id': linea.product_id.id,
                'product_name': linea.product_id.display_name,
                'qty': linea.product_uom_qty,
            } for linea in lineas],
        }

        self.write({
            'enteza_portal_ref': referencia,
            'enteza_portal_snapshot': snapshot,
            'enteza_portal_submitted_on': fields.Datetime.now(),
            'enteza_portal_state': 'submitted',
        })

        # Sin esto, ninguna respuesta del comercial en el chatter llega al cliente: no
        # queda como seguidor de su propio pedido (PRP v2 §5.9j / §8.2).
        self.message_subscribe(partner_ids=self.partner_id.ids)

        resumen = _(
            "Solicitud %(ref)s enviada desde el portal por %(cliente)s.\n"
            "%(n)s líneas · evento %(evento)s · entrega %(entrega)s · retirada %(retirada)s",
            ref=referencia, cliente=self.partner_id.display_name, n=len(lineas),
            evento=self.event_date, entrega=self.rental_start_date,
            retirada=self.rental_return_date,
        )
        if lineas_rojas:
            resumen += _("\n\nSin disponibilidad en: %s", ', '.join(lineas_rojas))
        self.message_post(body=resumen, subtype_xmlid='mail.mt_comment')

        if self.user_id:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_("Revisar solicitud de pedido %s", referencia),
                note=resumen,
                user_id=self.user_id.id,
            )
            if self.company_id.enteza_portal_aviso_email:
                plantilla = self.env.ref(
                    'enteza_portal_pedidos.mail_template_portal_solicitud_comercial',
                    raise_if_not_found=False)
                if plantilla:
                    plantilla.send_mail(self.id, force_send=False)

        return self._enteza_portal_payload_cabecera()

    def action_enteza_portal_cancel(self):
        """Cancela una solicitud mientras el cliente aún la está montando (PRP §5)."""
        self.ensure_one()
        if self.enteza_portal_state != 'composing':
            raise UserError(_(
                "Solo se puede cancelar una solicitud mientras se está montando."))
        self.action_cancel()
        self.enteza_portal_state = 'closed'
        return {'ok': True}

    # ------------------------------------------------------------------
    # Lado del comercial (PRP §10) — F4
    # ------------------------------------------------------------------

    def action_enteza_portal_tomar(self):
        """«Tomar la solicitud»: `submitted` → `reviewing`, se asigna si no hay comercial."""
        self.ensure_one()
        if self.enteza_portal_state != 'submitted':
            raise UserError(_("Solo se puede tomar una solicitud recién enviada."))
        vals = {'enteza_portal_state': 'reviewing'}
        if not self.user_id:
            vals['user_id'] = self.env.user.id
        self.write(vals)

    def action_enteza_portal_marcar_contrapropuesta(self):
        """«Marcar como contrapropuesta»: `reviewing` → `counter`.

        No envía nada por sí sola: el comercial ajusta las cantidades y usa el botón nativo
        «Enviar por correo» (PRP §10 punto 4) para el presupuesto en sí. Esto deja
        constancia de en qué punto está el diálogo, para que el portal le muestre el diff en
        vez de la pantalla de edición, y avisa al cliente por correo (PRP v2 §8.2) de que
        hay una propuesta esperándole — si no, no tiene forma de enterarse.
        """
        self.ensure_one()
        if self.enteza_portal_state != 'reviewing':
            raise UserError(_(
                "Solo se puede marcar como contrapropuesta una solicitud en revisión."))
        self.enteza_portal_state = 'counter'
        if self.company_id.enteza_portal_aviso_email:
            plantilla = self.env.ref(
                'enteza_portal_pedidos.mail_template_portal_contrapropuesta',
                raise_if_not_found=False)
            if plantilla:
                plantilla.send_mail(self.id, force_send=False)

    def action_enteza_portal_devolver(self, motivo=None):
        """«Devolver al cliente» (PRP v2 §8.1, botón nuevo en `views/sale_order_views.xml`):
        único camino de vuelta a `composing` desde fuera del propio cliente. Sin esto, una
        solicitud mal formada se quedaba atascada en el backend sin que el comercial
        pudiera devolvérsela al cliente para que la corrigiera él mismo.
        """
        self.ensure_one()
        if self.enteza_portal_state not in ('submitted', 'reviewing', 'counter'):
            raise UserError(_(
                "Solo se puede devolver al cliente una solicitud enviada, en revisión o "
                "con contrapropuesta."))
        self.enteza_portal_state = 'composing'

        resumen = _("Solicitud devuelta al cliente para que la edite.")
        if self.state == 'sent':
            resumen += "\n\n" + str(_(
                "⚠ El presupuesto ya se había enviado al cliente por el canal nativo de "
                "Ventas: puede que esté viendo una versión distinta a la que ahora vuelve "
                "a editar."))
        if motivo:
            resumen += "\n\n" + motivo
        self.message_post(body=resumen, subtype_xmlid='mail.mt_comment')

        if self.company_id.enteza_portal_aviso_email:
            plantilla = self.env.ref(
                'enteza_portal_pedidos.mail_template_portal_devuelta',
                raise_if_not_found=False)
            if plantilla:
                plantilla.send_mail(self.id, force_send=False)

    def action_confirm(self):
        """Al confirmarse (aceptación directa o tras contrapropuesta), la solicitud del
        portal se da por cerrada: ya es un pedido, y el ciclo de revisión ha terminado.
        """
        resultado = super().action_confirm()
        self.filtered(
            lambda o: o.enteza_portal_state not in ('none', 'closed')
        ).write({'enteza_portal_state': 'closed'})
        return resultado

    def _action_cancel(self):
        """Si se cancela un pedido que venía de una solicitud del portal aún abierta, se
        cierra también la solicitud: no debe quedar «en revisión» algo que ya no existe.
        """
        resultado = super()._action_cancel()
        self.filtered(
            lambda o: o.enteza_portal_state not in ('none', 'closed')
        ).write({'enteza_portal_state': 'closed'})
        return resultado

    # ------------------------------------------------------------------
    # Diálogo cliente ↔ comercial (PRP v2 §8) — F4
    # ------------------------------------------------------------------

    def _enteza_portal_mensajes(self):
        """Mensajes visibles para el cliente en el portal (PRP v2 §8.3).

        🔴 Filtra `subtype_id.internal`: sin este filtro el cliente vería las notas
        internas que el comercial escribe en el chatter, pensadas solo para uso interno. Es
        el fallo de seguridad más fácil de cometer aquí — lleva test obligatorio
        (`test_mensajes_portal_no_filtran_notas_internas`).
        """
        self.ensure_one()
        mensajes = self.message_ids.filtered(
            lambda m: m.message_type == 'comment'
            and not (m.subtype_id and m.subtype_id.internal)
        ).sorted(key=lambda m: m.date or fields.Datetime.now(), reverse=True)
        return [{
            'id': mensaje.id,
            'author': mensaje.author_id.display_name or mensaje.email_from or _("Enteza"),
            'date': fields.Datetime.to_string(mensaje.date) if mensaje.date else False,
            'body': mensaje.body,
            'is_customer': mensaje.author_id == self.partner_id,
        } for mensaje in mensajes]

    def action_enteza_portal_mensaje(self, body):
        """El cliente escribe al comercial desde el resumen de su solicitud."""
        self.ensure_one()
        if not body or not body.strip():
            raise UserError(_("Escribe algo antes de enviarlo."))
        self.message_post(
            body=body, message_type='comment', subtype_xmlid='mail.mt_comment',
            author_id=self.partner_id.id,
        )
        if self.user_id:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_(
                    "Mensaje del cliente en %s", self.enteza_portal_ref or self.name),
                user_id=self.user_id.id,
            )

    def action_enteza_portal_pedir_cambios(self, body):
        """`counter` → `reviewing`: el cliente no está de acuerdo con la contrapropuesta y
        pide que se revise otra vez.
        """
        self.ensure_one()
        if self.enteza_portal_state != 'counter':
            raise UserError(_("Solo se pueden pedir cambios sobre una contrapropuesta."))
        if not body or not body.strip():
            raise UserError(_("Cuéntanos qué quieres cambiar antes de enviarlo."))
        self.message_post(
            body=body, message_type='comment', subtype_xmlid='mail.mt_comment',
            author_id=self.partner_id.id,
        )
        self.enteza_portal_state = 'reviewing'
        if self.user_id:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_(
                    "%(cliente)s pide cambios en %(ref)s",
                    cliente=self.partner_id.display_name,
                    ref=self.enteza_portal_ref or self.name),
                note=body,
                user_id=self.user_id.id,
            )

    def action_enteza_portal_aceptar(self):
        """El cliente acepta la contrapropuesta. NO confirma el pedido — el cierre real
        sigue siendo la firma nativa del presupuesto (`/my/quotes/<id>`, «Aceptar y
        firmar»): esto solo avisa al comercial de que puede prepararlo para firma.
        """
        self.ensure_one()
        if self.enteza_portal_state != 'counter':
            raise UserError(_("Solo se puede aceptar una contrapropuesta."))
        self.message_post(
            body=_(
                "El cliente ha aceptado la propuesta. Pendiente de que firme el "
                "presupuesto."),
            subtype_xmlid='mail.mt_comment')
        if self.user_id:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_(
                    "%(cliente)s ha aceptado la propuesta de %(ref)s",
                    cliente=self.partner_id.display_name,
                    ref=self.enteza_portal_ref or self.name),
                user_id=self.user_id.id,
            )

    # ------------------------------------------------------------------
    # Trazabilidad para el portal (PRP §11)
    # ------------------------------------------------------------------

    def _enteza_portal_diff_contrapropuesta(self):
        """Compara el snapshot original con las líneas actuales.

        Filas para la tabla «Artículo · Solicitaste · Te proponemos» de §11, marcando lo
        cambiado, lo quitado y lo añadido. Se usa solo cuando `enteza_portal_state ==
        'counter'`; se renderiza en QWeb del lado servidor, no en OWL: es estático.
        """
        self.ensure_one()
        snapshot = self.enteza_portal_snapshot or {}
        pedido_original = {
            linea['product_id']: linea for linea in snapshot.get('lines', [])
        }
        propuesta_actual = {
            linea.product_id.id: linea for linea in self.order_line if linea.product_id
        }

        filas = []
        for product_id, original in pedido_original.items():
            actual = propuesta_actual.get(product_id)
            qty_actual = actual.product_uom_qty if actual else 0.0
            if not actual:
                estado = 'removed'
            elif float_compare(qty_actual, original['qty'], precision_digits=2) != 0:
                estado = 'changed'
            else:
                estado = 'same'
            filas.append({
                'product_name': original['product_name'],
                'qty_original': original['qty'],
                'qty_actual': qty_actual,
                'state': estado,
            })

        for product_id, actual in propuesta_actual.items():
            if product_id not in pedido_original:
                filas.append({
                    'product_name': actual.product_id.display_name,
                    'qty_original': 0.0,
                    'qty_actual': actual.product_uom_qty,
                    'state': 'added',
                })
        return filas

    def _enteza_portal_timeline(self):
        """Enlaces del hilo solicitud → presupuesto → pedido → facturas (PRP §11)."""
        self.ensure_one()
        enlaces = [{
            'label': _("Presupuesto / pedido %s", self.name),
            'url': self.get_portal_url(),
            'done': True,
        }]
        for factura in self.invoice_ids.filtered(lambda m: m.state != 'cancel'):
            enlaces.append({
                'label': _("Factura %s (%s)", factura.name, factura.payment_state),
                'url': factura.get_portal_url(),
                'done': True,
            })
        return enlaces
