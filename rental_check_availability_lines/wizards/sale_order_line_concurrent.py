from odoo import _, api, exceptions, fields, models


class SaleOrderLineConcurrent(models.TransientModel):
    _name = "sale.order.line.concurrent"

    @api.model
    def _default_product_id(self):
        line_id = self.env["sale.order.line"].browse(self.env.context.get("active_id"))
        if line_id:
            return line_id.product_id.id
        return 0

    @api.model
    def _default_sale_order_id(self):
        line_id = self.env["sale.order.line"].browse(self.env.context.get("active_id"))
        if line_id:
            return line_id.order_id.id
        return 0

    @api.model
    def _default_sale_order_line_id(self):
        return self.env["sale.order.line"].browse(self.env.context.get("active_id")).id

    @api.model
    def _default_sale_order_line_partner(self):
        return self.env["sale.order.line"].browse(self.env.context.get("active_id")).partner_id

    @api.model
    def _default_sale_order_line_partner_shipping(self):
        return self.env["sale.order.line"].browse(self.env.context.get("active_id")).partner_shipping_id

    @api.model
    def _default_sale_order_line_salesman(self):
        return self.env["sale.order.line"].browse(self.env.context.get("active_id")).salesman_id

    @api.model
    def _default_sale_order_line_warehouse(self):
        return self.env["sale.order.line"].browse(self.env.context.get("active_id")).warehouses_id

    @api.model
    def _default_sale_order_start_date(self):
        return self.env["sale.order.line"].browse(self.env.context.get("active_id")).start_date

    @api.model
    def _default_sale_order_end_date(self):
        return self.env["sale.order.line"].browse(self.env.context.get("active_id")).end_date

    @api.depends("product_id")
    def _compute_qty_available(self):
        for line in self:
            line.qty_available = line.product_id.rented_product_id.with_context(
                {"location": line.warehouses_id.rental_view_location_id.id}
            ).qty_available

    @api.depends("product_id")
    def _compute_qty_available_total(self):
        for line in self:
            line.qty_available_total = line.product_id.rented_product_id.qty_available

    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product',
        default=_default_product_id,
        readonly=True,
    )
    order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Order id",
        default=_default_sale_order_id,
    )
    qty_available = fields.Float(
        string="Stock",
        compute="_compute_qty_available",
    )
    qty_available_total = fields.Float(
        string="Stock",
        compute="_compute_qty_available_total",
    )
    sale_order_line_id = fields.Many2one(
        comodel_name="sale.order.line",
        string="Sale order line",
        default=_default_sale_order_line_id,
    )
    state = fields.Selection(
        string="State",
        related="sale_order_line_id.state"
    )
    line_ids = fields.One2many(
        comodel_name="sale.order.line",
        inverse_name="order_id",
        string="Lines ids",
        domain=[("order_id", "=", order_id)],
    )
    line_concurrent_ids = fields.One2many(
        comodel_name="sale.order.line.concurrent.line",
        inverse_name="sale_order_line_concurrent_id",
        string="Sale order lines concurrent",
    )
    start_date = fields.Date(
        string='Start date',
        default=_default_sale_order_start_date,
    )
    end_date = fields.Date(
        string='End date',
        default=_default_sale_order_end_date,
    )
    product_uom_qty = fields.Float(
        string="Quantity",
        related="sale_order_line_id.product_uom_qty",
    )
    salesman_id = fields.Many2one(
        string="Salesman id",
        comodel_name='sale_order_line',
        default=_default_sale_order_line_salesman,
    )
    partner_id = fields.Many2one(
        comodel_name="sale.order.line",
        default=_default_sale_order_line_partner,
        string="Partner name",
    )
    warehouses_id = fields.Many2one(
        string="Warehouse",
        comodel_name="stock.warehouse",
        default=_default_sale_order_line_warehouse,
    )

    @api.onchange("product_id")
    def _onchange_product_id(self):
        domain = [
            ("state", "!=", "cancel"),
            ("product_id", "=", self.product_id.id),
            ("warehouses_id", "=", self.warehouses_id.id),
            "|",
            "&",
            ("start_date", "<=", self.start_date),
            ("end_date", ">=", self.start_date),
            "&",
            ("start_date", "<=", self.end_date),
            ("end_date", ">=", self.end_date),
        ]
        order_lines = self.env["sale.order.line"].search(domain)
        for line in order_lines:
            self.line_concurrent_ids += self.env['sale.order.line.concurrent.line'].new(
                {
                    "order_id": line.order_id,
                    "partner_id": line.order_id.partner_id,
                    "partner_shipping_id": line.order_id.partner_shipping_id,
                    "date_order": line.order_id.date_order,
                    "event_date": line.order_id.event_date,
                    "start_date": line.start_date,
                    "end_date": line.end_date,
                    "salesman_id": line.order_id.user_id,
                    "product_uom_qty": line.product_uom_qty,
                    "invoice_status": line.order_id.invoice_status,
                    "amount_total": line.order_id.amount_total,
                }
            )

    def confirm(self):
        return {'type': 'ir.actions.act_window_close'}


class SaleOrderLineConcurrentLine(models.TransientModel):
    _name = "sale.order.line.concurrent.line"
    _description = "Sale order line concurrent"
    _order = "sale_order_date_order desc"

    sale_order_line_concurrent_id = fields.Many2one(
        comodel_name="sale.order.line.concurrent",
        string="Sale order line",
    )
    order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Order id",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Partner",
    )
    partner_shipping_id = fields.Many2one(
        comodel_name="res.partner",
        string="Partner Shipping",
    )
    start_date = fields.Date(
        string="Start date",
    )
    end_date = fields.Date(
        string="End date",
    )
    date_order = fields.Date(
        string="Order date",
    )
    event_date = fields.Date(
        string="Event date",
    )
    salesman_id = fields.Many2one(
        comodel_name="res.users",
        string="Salesman",
    )
    product_uom_qty = fields.Float(
        string="Quantity",
    )
    invoice_status = fields.Selection([
        ('upselling', 'Upselling Opportunity'),
        ('invoiced', 'Fully Invoiced'),
        ('to invoice', 'To Invoice'),
        ('no', 'Nothing to Invoice')
    ], string='Invoice Status',
    )
    amount_total = fields.Float(
        string="Subtotal",
    )
    quantity = fields.Float(
        string="Stock",
    )

