# Copyright 2019 Tecnativa - Ernesto Tejeda
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta

from ..wizard.rental_missing_wizard import missing_line_sort_key


class SaleOrder(models.Model):
    _inherit = "sale.order"

    rental_billable_days = fields.Float(
        string="Días facturables",
        default=1.0,
        digits=(16, 2),
        tracking=True,
        help="Días usados para calcular el precio del alquiler. No modifican las fechas del "
             "periodo, la disponibilidad ni los albaranes.",
    )
    event_date = fields.Date(
        string="Fecha Evento",
    )
    place_number = fields.Integer(
        string="Número Plazas",
    )

    picking_id = fields.Many2one('stock.picking', string="Stock Picking", readonly=True, copy=False)

    rental_order_id = fields.Many2one(
        "sale.order",
        string="Pedido de alquiler de origen",
        copy=False,
        help="Este pedido factura material de alquiler no devuelto de este otro pedido.",
    )
    missing_from_rental_location = fields.Boolean(
        string="Faltas desde Alquiler",
        copy=False,
        # Entre que el servidor carga este código y que Actualizar crea la columna, cualquier
        # lectura de pedidos la pediría por prefetch y fallaría (UndefinedColumn).
        prefetch=False,
        readonly=True,
        help="Venta de material no devuelto cuyas unidades siguen en la ubicación de "
             "Alquiler: el albarán de salida sale de ahí y no de Stock.",
    )
    missing_auto_validate = fields.Boolean(
        string="Baja automática de faltas",
        copy=False,
        readonly=True,
        # Mismo motivo que `missing_from_rental_location`.
        prefetch=False,
        help="Pedido de faltas creado desde el pedido de alquiler: al confirmarlo, su "
             "albarán de salida se valida solo y las unidades quedan dadas de baja.",
    )
    missing_from_order_allowed = fields.Boolean(
        compute="_compute_missing_from_order_allowed",
        help="Las faltas se registran desde el pedido cuando no tiene albaranes abiertos. "
             "Si los tiene, se usa «Facturar las Faltas» en la recogida.",
    )
    compensation_order_ids = fields.One2many(
        "sale.order",
        "rental_order_id",
        string="Ventas por material no devuelto",
        # Sin los cancelados (19.0.1.16.1): el aviso del formulario seguía mostrando un
        # pedido de faltas anulado (41255027 con S00379, 2026-10-07). El enlace
        # `rental_order_id` del cancelado se conserva; solo deja de contar aquí.
        domain=[("state", "!=", "cancel")],
        help="Pedidos de venta que facturan material de este alquiler que no se devolvió.",
    )

    @api.depends("is_rental_order", "state", "picking_ids.state")
    def _compute_missing_from_order_allowed(self):
        for order in self:
            order.missing_from_order_allowed = (
                order.is_rental_order
                and order.state == "sale"
                and not order.picking_ids.filtered(
                    lambda p: p.state not in ("done", "cancel")
                )
            )

    # ------------------------------------------------------------------
    # Faltas: piezas comunes a los dos caminos (albarán y pedido)
    # ------------------------------------------------------------------

    @api.model
    def _prepare_missing_line_vals(self, product, qty, uom):
        return (0, 0, {
            "product_id": product.id,
            "product_uom_qty": qty,
            "product_uom_id": uom.id,
            # Sin `price_unit`: lo calcula Odoo con la tarifa del cliente (2026-09-28). Sin
            # tarifas activas, o con una tarifa sin reglas, sale el mismo precio de venta del
            # producto que antes se forzaba aquí. Con la tarifa especial de una compañía del
            # grupo, sale el precio intercompañía.
            #
            # El producto es alquilable (rent_ok) y sale_renting marca la línea como alquiler
            # por defecto en cuanto lo detecta, arrastrando al pedido entero a is_rental_order.
            # Esto es una venta normal de material perdido, no un alquiler.
            "is_rental": False,
        })

    def _prepare_missing_sale_order_vals(self, partner, company, origin, order_lines,
                                         from_rental_location):
        """Cabecera del pedido de faltas. `self` es el alquiler de origen (puede ir vacío)."""
        return {
            "partner_id": partner.id,
            "company_id": company.id,
            "origin": origin,
            "order_line": order_lines,
            "rental_order_id": self.id,
            # Vacío si la compañía no lo tiene configurado: Odoo usa entonces su diario de
            # ventas por defecto, que en Enteza es el de alquiler (2026-10-03).
            "journal_id": company.rental_missing_journal_id.id,
            # Al confirmar, el albarán de salida sale de Alquiler y no de Stock (ver
            # `stock_rule.py`): las unidades perdidas dejan de figurar en existencias al
            # validarlo. Antes salía de Stock y había que cancelarlo a mano (12/08/2026).
            "missing_from_rental_location": from_rental_location,
            # Forzado explícito: el botón se pulsa desde la app de Alquiler, y ese contexto
            # trae un `default_is_rental_order` ambiental que, si no se anula aquí, cuela el
            # pedido en la app de Alquiler aunque ninguna línea sea de alquiler
            # (is_rental=False en todas). No basta con las líneas, hay que fijarlo también en
            # la cabecera.
            "is_rental_order": False,
            # No es un pedido de alquiler, así que este campo queda libre para anotar la fecha
            # del evento de origen: sirve de dimensión de periodo en los informes de pérdidas.
            "event_date": self.event_date,
        }

    # ------------------------------------------------------------------
    # Faltas desde el pedido (sin albarán de recogida, 19.0.1.16.0)
    # ------------------------------------------------------------------

    def action_open_missing_wizard(self):
        """Abre «Registrar faltas». Es el camino cuando el alquiler no tiene albaranes:
        con «Traslado de alquiler» apagado, o con los albaranes ya cancelados.
        """
        self.ensure_one()
        if not self.missing_from_order_allowed:
            raise UserError(_(
                "El pedido %s tiene albaranes abiertos o no es un alquiler confirmado. "
                "Las faltas se facturan desde su albarán de recogida, con «Facturar las "
                "Faltas».", self.name,
            ))
        lines = self.order_line.filtered(
            lambda l: l.is_rental and l.product_id.type == "consu"
        ).sorted(missing_line_sort_key)
        wizard = self.env["rental.missing.wizard"].create({
            "order_id": self.id,
            "line_ids": [(0, 0, {"sale_line_id": line.id}) for line in lines],
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Registrar faltas"),
            "res_model": "rental.missing.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def _mark_rental_returned(self):
        """Deja todas las líneas de alquiler recogidas y devueltas: el pedido pasa a Devuelto.

        Lo perdido cuenta como «devuelto» y queda anotado en `qty_lost`, igual que en el
        camino del albarán (`stock_picking._mark_rental_line_lost`). Con «Traslado de
        alquiler» apagado, `sale_stock_renting` crea por este `write` los movimientos Stock →
        Alquiler → Stock, que se compensan; la baja real la hace el pedido de faltas.
        """
        for line in self.order_line.filtered("is_rental"):
            vals = {}
            if line.qty_delivered < line.product_uom_qty:
                vals["qty_delivered"] = line.product_uom_qty
            if line.qty_returned < line.product_uom_qty:
                vals["qty_returned"] = line.product_uom_qty
            if vals:
                line.write(vals)

    def _validate_missing_pickings(self):
        """Valida la salida de los pedidos de faltas creados desde el pedido (decisión b).

        `sudo()` acotado a estos albaranes: quien confirma la venta de faltas suele ser de
        ventas, sin permisos de almacén, y la baja tiene que quedar hecha igualmente.
        """
        for order in self:
            pickings = order.sudo().picking_ids.filtered(
                lambda p: p.state not in ("done", "cancel")
                and p.picking_type_code == "outgoing"
            )
            for picking in pickings:
                picking = picking.with_company(picking.company_id)
                for move in picking.move_ids.filtered(
                    lambda m: m.state not in ("done", "cancel")
                ):
                    move.quantity = move.product_uom_qty
                    move.picked = True
                picking._action_done()
            if pickings:
                order.message_post(body=_(
                    "Baja de material hecha al confirmar: %s.",
                    ", ".join(pickings.mapped("name")),
                ))

    @api.onchange("event_date")
    def event_date_change(self):
        if self.event_date:
            self.rental_start_date = self.event_date - timedelta(days=1)
            self.rental_return_date = self.event_date + timedelta(days=1)

    @api.constrains("rental_billable_days", "is_rental_order")
    def _check_rental_billable_days(self):
        for order in self:
            if order.is_rental_order and order.rental_billable_days <= 0:
                raise ValidationError(_("Los días facturables deben ser mayores que cero."))

    @api.onchange("rental_billable_days")
    def _onchange_rental_billable_days(self):
        for order in self.filtered("is_rental_order"):
            if order.rental_billable_days > 0:
                order._recompute_rental_prices()

    def write(self, vals):
        result = super().write(vals)
        if "rental_billable_days" in vals:
            self.filtered(
                lambda order: order.is_rental_order
                and order.rental_billable_days > 0
                and order.state in ("draft", "sent")
            )._recompute_rental_prices()
        return result

    def action_open_rental_order_rename_wizard(self):
        self.ensure_one()
        if not self.is_rental_order or self.state not in ("draft", "sent"):
            raise UserError(_("El número solo puede modificarse antes de confirmar el pedido."))
        return {
            "name": _("Cambiar número de presupuesto"),
            "type": "ir.actions.act_window",
            "res_model": "rental.order.rename.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_order_id": self.id,
                "default_name": self.name,
            },
        }

    def action_confirm(self):
        """No deja confirmar un alquiler sin fecha de evento.

        La vista de alquiler ya la pide como obligatoria, pero eso sólo cubre la interfaz: un
        pedido creado por RPC, por importación o desde el formulario de ventas se colaría sin
        ella. Se valida al CONFIRMAR y no al guardar para no estorbar mientras se prepara un
        presupuesto, que es cuando puede no conocerse todavía la fecha.

        Sin este dato, la factura sale sin fecha de evento y el pedido no aparece en el
        calendario. Motivo por el que se añadió (2026-08-03): dos pedidos hechos en Odoo 19
        (S00014 y S00016) se confirmaron y facturaron sin rellenarla.
        """
        sin_fecha = self.filtered(lambda o: o.is_rental_order and not o.event_date)
        if sin_fecha:
            raise ValidationError(
                _(
                    "Falta la fecha del evento en: %s\n\n"
                    "En los pedidos de alquiler es obligatoria: sin ella la factura sale sin "
                    "fecha de evento y el pedido no aparece en el calendario.",
                    ", ".join(sin_fecha.mapped("name")),
                )
            )

        # Confirmar es el flujo nativo de Odoo 19, sin excepciones: todo pedido genera los
        # documentos de almacén que le correspondan.
        #
        # Aquí hubo un `skip_delivery_creation` que troceaba el recordset para que los pedidos
        # de faltas no generasen albarán de salida, y **rompía el sistema entero**: combinaba
        # los dos super() con `... and result`, de modo que cuando la cadena de herencia
        # devolvía una ACCIÓN en vez de True —`enteza_prestamo_intercompania` devuelve el
        # diálogo de "falta material" en cuanto una línea tiene déficit— el `and` la reducía a
        # True. El diálogo no llegaba al navegador, el pedido se quedaba en presupuesto sin
        # mensaje alguno y, al no confirmarse, no se generaba ningún movimiento de almacén.
        #
        # Regla que deja el incidente: el valor que devuelve `action_confirm` es parte del
        # contrato —puede ser un `dict` de acción— y se propaga TAL CUAL. Nada de combinarlo
        # con `and`/`or` ni de sustituirlo por un booleano propio.
        result = super().action_confirm()
        # La baja automática solo con la confirmación hecha (`True`): si la cadena devolvió un
        # diálogo, el pedido aún no está confirmado y no hay albarán que validar.
        if result is True:
            self.filtered(
                lambda o: o.missing_auto_validate and o.state == "sale"
            )._validate_missing_pickings()
        return result

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    event_date = fields.Date(
        related="order_id.event_date",
    )

    qty_lost = fields.Float(
        string="No devueltas (facturadas)",
        copy=False,
        digits="Product Unit",
        help="Unidades que no se devolvieron y se facturaron en otro pedido de venta en vez "
             "de contarse como una devolución real. Ya están incluidas en «Devueltas» para "
             "que el pedido de alquiler pueda cerrarse como devuelto: este número es sólo la "
             "anotación de cuántas de esas unidades son en realidad una pérdida facturada.",
    )

    def _get_rental_order_line_description(self):
        """No repetir el periodo común del pedido en cada línea de alquiler."""
        self.ensure_one()
        return ""

    def _get_pricelist_price(self):
        """Precio de alquiler calculado con los días facturables del pedido.

        La disponibilidad y los albaranes siguen usando las fechas reales. Sólo para el precio,
        se obtiene la tarifa nativa equivalente a un día de alquiler y se multiplica por el
        número decimal que el comercial haya indicado (por ejemplo, 1,50 días).
        """
        self.ensure_one()
        if self.is_rental and self.order_id.rental_billable_days > 0:
            self.order_id._rental_set_dates()
            start_date = self.start_date
            if start_date:
                daily_price = self.order_id.pricelist_id._get_product_price(
                    self.product_id.with_context(**self._get_product_price_context()),
                    self.product_uom_qty or 1.0,
                    currency=self.currency_id,
                    uom=self.product_uom_id,
                    date=self.order_id.date_order or fields.Date.today(),
                    start_date=start_date,
                    end_date=start_date + timedelta(days=1),
                )
                return daily_price * self.order_id.rental_billable_days
        return super()._get_pricelist_price()

    product_categ_id = fields.Many2one(
        related="product_id.categ_id",
        string="Categoria",
        store=True
    )

    total_stock = fields.Float(string='Stock Total', compute='_compute_total_availability', store=False)
    total_rented = fields.Float(string='Total Alquilado', compute='_compute_total_availability', store=False)
    total_available = fields.Float(string='Total Disponible', compute='_compute_total_availability', store=False)

    @api.depends('product_id', 'reservation_begin', 'return_date', 'order_id.warehouse_id')
    def _compute_total_availability(self):
        """Delega en el motor nativo de disponibilidad (`sale_stock_renting`), en vez de
        sumar `stock.quant` y líneas a mano (2026-08-08, PRP v2 D4).

        El cálculo manual anterior sumaba TODOS los `stock.quant` internos sin filtrar por
        almacén ni compañía, y TODAS las líneas `state='sale'` del sistema entero: mezclaba
        Vimaple y Stileum en una sola cifra. Además, cuando `is_rental` era `False` -una
        línea de servicio (fianza, portes) dentro de un pedido de alquiler- el `if` no
        entraba nunca y los tres campos se quedaban SIN asignar: un campo calculado no
        almacenado sin asignar lanza `ValueError` al leerlo. Verificado por RPC el
        2026-08-08: 2.008 líneas de pedidos de alquiler reales tienen `is_rental=False`
        (son servicios), así que no era un caso de laboratorio.

        Los tres campos se asignan SIEMPRE, incluso a 0.0, para que ese `ValueError` no
        pueda volver a producirse.
        """
        for line in self:
            if line.is_rental and line.product_id and line.reservation_begin and line.return_date:
                almacen = line.order_id.warehouse_id
                availability = self.get_total_availability(
                    line.product_id.id, line.reservation_begin, line.return_date,
                    warehouse_id=almacen.id if almacen else False,
                    ignored_soline_id=line.id if line.state == 'draft' else False,
                )
                line.total_stock = availability['total_stock']
                line.total_rented = availability['total_rented']
                line.total_available = availability['total_available']
            else:
                line.total_stock = 0.0
                line.total_rented = 0.0
                line.total_available = 0.0

    @api.model
    def get_total_availability(self, product_id, start_date, end_date, warehouse_id=False,
                                ignored_soline_id=False):
        """Réplica del cálculo de `enteza_portal_pedidos.product.product._enteza_portal_disponible`
        (mismo patrón, ya documentado y verificado contra `enteza26` el 2026-08-02 en
        `enteza_prestamo_intercompania`): usa `_get_unavailable_qty` y
        `_get_virtual_unavailable_qty_in_rent`, ambos de `sale_stock_renting`, en vez de
        reimplementar la disponibilidad a mano.

        Se duplica aquí en vez de llamar al método del otro módulo porque
        `enteza_portal_pedidos` DEPENDE de `rental_custom` (no al revés, PRP original §2.5):
        invertir esa dependencia para reutilizar código habría sido un cambio de alcance
        mayor que el propio arreglo.

        :param warehouse_id: sin él (llamada desde el widget `QtyAtDate`, que no tiene un
            pedido concreto detrás) se calcula sin restringir por almacén, igual que hacía
            el cálculo manual anterior.
        :param ignored_soline_id: la propia línea que se está mirando, para que no compita
            consigo misma. Solo tiene efecto si esa línea sigue en borrador -en cuanto se
            confirma, ya hay un movimiento de stock real que `virtual_available` descuenta,
            y sumarla dos veces fue un bug ya cazado una vez en este repositorio (ver
            docstring de `_enteza_portal_disponible`).
        """
        product = self.env['product.product'].browse(product_id)
        contexto = {'from_date': start_date, 'to_date': end_date}
        if warehouse_id:
            contexto['warehouse_id'] = warehouse_id

        ahora = fields.Datetime.now()
        if start_date and start_date <= ahora:
            total_stock = product.with_context(**contexto).qty_available
        else:
            contexto_virtual = dict(contexto, from_date=False, to_date=start_date)
            total_stock = product.with_context(**contexto_virtual).virtual_available
            total_stock += product._get_virtual_unavailable_qty_in_rent(
                pivot_date=start_date,
                ignored_soline_id=ignored_soline_id,
                warehouse_id=warehouse_id,
            )

        total_rented = product._get_unavailable_qty(
            start_date, end_date,
            ignored_soline_id=ignored_soline_id,
            warehouse_id=warehouse_id,
        )
        total_available = max(total_stock - total_rented, 0.0)

        return {
            'product_id': product.display_name,
            'total_stock': total_stock,
            'total_rented': total_rented,
            'total_available': total_available,
        }

    @api.model
    def get_availability_data(self, product_id, start_date, end_date):
        """Llamado por RPC desde `rental_availability_popup.js` (widget `QtyAtDate` del
        formulario de línea de pedido). Firma sin `warehouse_id`: se mantiene así a
        propósito porque ese widget pregunta "en todos los almacenes", no en uno concreto.
        """
        return self.get_total_availability(product_id, start_date, end_date)

