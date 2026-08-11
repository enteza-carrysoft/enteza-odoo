# Copyright 2019 Tecnativa - Ernesto Tejeda
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta


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
    compensation_order_ids = fields.One2many(
        "sale.order",
        "rental_order_id",
        string="Ventas por material no devuelto",
        help="Pedidos de venta que facturan material de este alquiler que no se devolvió.",
    )

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
        return super().action_confirm()

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

