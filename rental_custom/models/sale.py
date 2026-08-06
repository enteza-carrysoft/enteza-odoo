# Copyright 2019 Tecnativa - Ernesto Tejeda
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
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
        return super().action_confirm()

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    event_date = fields.Date(
        related="order_id.event_date",
    )

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

    @api.depends('product_id', 'reservation_begin', 'return_date')
    def _compute_total_availability(self):
        for line in self:
            if line.is_rental:
                availability = self.get_total_availability(line.product_id.id, line.reservation_begin, line.return_date)
                line.total_stock = availability['total_stock']
                line.total_rented = availability['total_rented']
                line.total_available = availability['total_available']

    @api.model
    def get_total_availability(self, product_id, start_date, end_date):
        product = self.env['product.product'].browse(product_id)

        total_stock = sum(self.env['stock.quant'].search([
            ('product_id', '=', product_id),
            ('location_id.usage', '=', 'internal')
        ]).mapped('quantity'))

        total_rented = sum(self.env['sale.order.line'].search([
            ('product_id', '=', product_id),
            ('is_rental', '=', True),
            ('reservation_begin', '<=', end_date),
            ('return_date', '>=', start_date),
            ('state', '=', 'sale')
        ]).mapped('product_uom_qty'))

        total_available = total_stock - total_rented

        return {
            'product_id': product.display_name,
            'total_stock': total_stock,
            'total_rented': total_rented,
            'total_available': total_available,
        }

    @api.model
    def get_availability_data(self, product_id, start_date, end_date):
        availability_data = self.get_total_availability(product_id, start_date, end_date)
        return availability_data

