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
"""
import math

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class SaleOrder(models.Model):
    _inherit = 'sale.order'

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
        """
        existente = self.sudo().search([
            ('partner_id', '=', partner.id),
            ('enteza_portal_state', '=', 'composing'),
        ], limit=1, order='id desc')
        if existente:
            return existente

        almacen = partner.enteza_portal_warehouse_id
        if not almacen:
            almacen = self.env['stock.warehouse'].sudo().search([], limit=1)

        return self.sudo().with_context(in_rental_app=True).create({
            'partner_id': partner.id,
            'company_id': almacen.company_id.id if almacen else self.env.company.id,
            'warehouse_id': almacen.id if almacen else False,
            'enteza_portal_state': 'composing',
        })

    def action_enteza_portal_repetir(self):
        """Solicitud nueva copiando las líneas de un pedido pasado (PRP §9.4).

        Cantidades incluidas, fechas vacías: el cliente solo tiene que revisarlas y enviar.
        Solo copia material físico de alquiler — los servicios (fianza, portes...) se
        renegocian aparte en cada evento.
        """
        self.ensure_one()
        lineas_copiables = self.order_line.filtered(
            lambda l: l.product_id and l.product_id.rent_ok and l.product_id.type == 'consu'
        )
        return self.sudo().with_context(in_rental_app=True).create({
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'warehouse_id': self.warehouse_id.id,
            'enteza_portal_state': 'composing',
            'order_line': [
                (0, 0, {
                    'product_id': linea.product_id.id,
                    'product_uom_qty': linea.product_uom_qty,
                    'product_uom_id': linea.product_uom_id.id,
                })
                for linea in lineas_copiables
            ],
        })

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
    # Cabecera (PRP §8.2 /cabecera, §8.3)
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

    def _enteza_portal_payload_cabecera(self):
        self.ensure_one()
        almacenes = self.env['stock.warehouse'].sudo().search([])
        moneda = self.currency_id or self.company_id.currency_id
        return {
            'id': self.id,
            'ref': self.enteza_portal_ref or False,
            'state': self.enteza_portal_state,
            'write_date': fields.Datetime.to_string(self.write_date),
            'event_date': fields.Date.to_string(self.event_date) if self.event_date else False,
            'pickup_date': self._enteza_portal_fecha_local(self.rental_start_date),
            'return_date': self._enteza_portal_fecha_local(self.rental_return_date),
            'warehouse_id': self.warehouse_id.id or False,
            'warehouses': [{'id': a.id, 'name': a.name} for a in almacenes],
            'semaforo_activo': self.company_id.enteza_portal_semaforo,
            'dias_minimos': self.company_id.enteza_portal_dias_minimos,
            'customer_note': self.enteza_portal_customer_note or '',
            'currency': {
                'symbol': moneda.symbol,
                'position': moneda.position,
                'decimals': moneda.decimal_places,
            },
        }

    def _enteza_portal_actualizar_cabecera(self, vals):
        """Escribe fecha de evento, entrega, retirada y almacén (PRP §8.2).

        `rental_custom` ya calcula `rental_start_date`/`rental_return_date` a partir de
        `event_date` mediante un `onchange` del cliente web de backend, que aquí no se
        dispara: el portal manda las tres fechas explícitas y se escriben tal cual.
        """
        self.ensure_one()
        self._enteza_portal_check_composing()

        vals_pedido = {}
        if 'event_date' in vals:
            vals_pedido['event_date'] = vals['event_date'] or False
        if vals.get('pickup_date'):
            vals_pedido['rental_start_date'] = vals['pickup_date']
        if vals.get('return_date'):
            vals_pedido['rental_return_date'] = vals['return_date']
        if vals.get('warehouse_id'):
            almacen = self.env['stock.warehouse'].sudo().browse(vals['warehouse_id'])
            if almacen.exists():
                vals_pedido['warehouse_id'] = almacen.id
                vals_pedido['company_id'] = almacen.company_id.id

        if vals_pedido:
            self.write(vals_pedido)
        return self._enteza_portal_payload_cabecera()

    # ------------------------------------------------------------------
    # Catálogo (PRP §8.3)
    # ------------------------------------------------------------------

    def _enteza_portal_productos_habituales(self):
        """Ids de producto que el cliente ya alquiló alguna vez (PRP §9.4)."""
        self.ensure_one()
        lineas = self.env['sale.order.line'].sudo().search_read(
            domain=[
                ('order_id.partner_id', 'child_of', self.partner_id.commercial_partner_id.id),
                ('order_id.state', '=', 'sale'),
                ('product_id', '!=', False),
            ],
            fields=['product_id'],
        )
        return {linea['product_id'][0] for linea in lineas if linea['product_id']}

    def _enteza_portal_payload_catalogo(self):
        """Catálogo completo servido de una vez (PRP §2.3, §8.3): se filtra en el navegador.

        🔴 `type='consu'` además de `rent_ok`: hay artículos de servicio marcados como
        alquilables (fianza, portes, precio por plaza...) que no son material de camión.
        """
        self.ensure_one()
        productos = self.env['product.product'].sudo().search([
            ('rent_ok', '=', True),
            ('type', '=', 'consu'),
            ('enteza_portal_ok', '=', True),
            ('active', '=', True),
        ])

        habituales = self._enteza_portal_productos_habituales()
        lineas_por_producto = {linea.product_id.id: linea for linea in self.order_line}

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
    # Líneas (PRP §8.2 /lineas)
    # ------------------------------------------------------------------

    def _enteza_portal_actualizar_lineas(self, changes):
        """Altas/bajas/cambios de cantidad en una sola transacción (PRP §8.2).

        :param changes: lista de `{'product_id': int, 'qty': float}`
        """
        self.ensure_one()
        self._enteza_portal_check_composing()

        Product = self.env['product.product'].sudo()
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        lineas_por_producto = {linea.product_id.id: linea for linea in self.order_line}

        avisos = []
        lineas_afectadas = []
        for cambio in changes:
            producto = Product.browse(cambio.get('product_id'))
            if not producto.exists():
                continue
            qty = float(cambio.get('qty') or 0.0)
            if qty < 0:
                qty = 0.0

            linea = lineas_por_producto.get(producto.id)

            if float_compare(qty, 0.0, precision_digits=precision) <= 0:
                if linea:
                    linea.unlink()
                    lineas_por_producto.pop(producto.id, None)
                continue

            if linea:
                linea.write({'product_uom_qty': qty})
            else:
                linea = self.env['sale.order.line'].with_context(
                    in_rental_app=True
                ).create({
                    'order_id': self.id,
                    'product_id': producto.id,
                    'product_uom_qty': qty,
                    'product_uom_id': producto.uom_id.id,
                })
                lineas_por_producto[producto.id] = linea

            lineas_afectadas.append(linea.id)

            aviso = self._enteza_portal_check_multiplo(producto, qty)
            if aviso:
                avisos.append(aviso)

        return {
            'ok': True,
            'lines_updated': lineas_afectadas,
            'warnings': avisos,
            'lines': self._enteza_portal_payload_lineas(),
            'totals': self._enteza_portal_payload_totales(),
            'write_date': fields.Datetime.to_string(self.write_date),
        }

    # ------------------------------------------------------------------
    # Disponibilidad por lotes (PRP §6.2, §8.2 /disponibilidad)
    # ------------------------------------------------------------------

    def _enteza_portal_disponibilidad(self, product_ids):
        """Semáforo por lotes, máximo 50 productos por llamada (PRP §6.2).

        Nunca devuelve la cantidad libre: solo el color (PRP §6.3). Si el semáforo está
        desactivado, o faltan fechas/almacén, se devuelve `grey` para todo sin consultar el
        motor de disponibilidad.
        """
        self.ensure_one()
        product_ids = list(product_ids)[:50]

        if not self.company_id.enteza_portal_semaforo:
            return {pid: 'grey' for pid in product_ids}
        if not (self.warehouse_id and self.rental_start_date and self.rental_return_date):
            return {pid: 'grey' for pid in product_ids}

        Product = self.env['product.product'].sudo()
        almacen = self.warehouse_id
        desde, hasta = self.rental_start_date, self.rental_return_date
        lineas_por_producto = {linea.product_id.id: linea for linea in self.order_line}

        resultado = {}
        for pid in product_ids:
            producto = Product.browse(pid)
            if not producto.exists():
                resultado[pid] = 'grey'
                continue
            linea = lineas_por_producto.get(pid)
            qty = linea.product_uom_qty if linea else 0.0
            resultado[pid] = producto._enteza_portal_semaforo(
                qty, desde, hasta, almacen, ignorar_linea=linea)
        return resultado

    # ------------------------------------------------------------------
    # Envío (PRP §4.1) — el único punto crítico de concurrencia
    # ------------------------------------------------------------------

    def action_enteza_portal_submit(self, customer_note=None):
        """Cierra la composición y avisa al comercial. Idempotente.

        Un doble clic del cliente no debe duplicar ni la referencia ni el aviso: si la
        solicitud ya no está en `composing`, se devuelve el estado actual sin repetir nada.
        """
        self.ensure_one()
        if self.enteza_portal_state != 'composing':
            return self._enteza_portal_payload_cabecera()

        if not (self.event_date and self.rental_start_date and self.rental_return_date):
            raise UserError(_(
                "Faltan datos del evento: indica la fecha del evento, la de entrega y la de "
                "retirada antes de enviar la solicitud."))
        if not self.warehouse_id:
            raise UserError(_("Indica desde qué almacén quieres que se sirva el material."))

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
            'enteza_portal_customer_note': customer_note or self.enteza_portal_customer_note,
            'enteza_portal_submitted_on': fields.Datetime.now(),
            'enteza_portal_state': 'submitted',
        })

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
    # Lado del comercial (PRP §10)
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
        «Enviar por correo» (PRP §10 punto 4). Esto solo deja constancia de en qué punto
        está el diálogo con el cliente, para que el portal le muestre el diff en vez de la
        pantalla de edición.
        """
        self.ensure_one()
        if self.enteza_portal_state != 'reviewing':
            raise UserError(_(
                "Solo se puede marcar como contrapropuesta una solicitud en revisión."))
        self.enteza_portal_state = 'counter'

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
