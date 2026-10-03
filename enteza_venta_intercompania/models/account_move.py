import logging
from collections import defaultdict

from odoo import Command, _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    enteza_ic_estado = fields.Selection(
        [('pendiente', "Pendiente"), ('generada', "Generada")],
        string="Venta intercompañía",
        copy=False,
        readonly=True,
        tracking=True,
        prefetch=False,
        help="Vacío: la factura no tiene material cedido por otra compañía. Pendiente: lo "
             "tiene, pero no se pudo crear la factura intercompañía (el motivo está en el "
             "historial).",
    )
    enteza_ic_enlace_ids = fields.One2many(
        'enteza.venta.intercompania.enlace', 'source_move_id',
        string="Enlaces de venta intercompañía", readonly=True)
    enteza_ic_invoice_count = fields.Integer(compute='_compute_enteza_ic_invoice_count')

    def _compute_enteza_ic_invoice_count(self):
        for move in self:
            # sudo(): las facturas son de la compañía dueña; sólo se cuentan.
            move.enteza_ic_invoice_count = len(move.sudo().enteza_ic_enlace_ids.invoice_id)

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        posted.filtered(
            lambda m: m.move_type in ('out_invoice', 'out_refund'))._enteza_ic_procesar()
        return posted

    def action_enteza_ic_procesar(self):
        self._enteza_ic_procesar()

    def action_enteza_ic_ver_facturas(self):
        self.ensure_one()
        invoices = self.sudo().enteza_ic_enlace_ids.invoice_id
        action = {
            'type': 'ir.actions.act_window',
            'name': _("Factura intercompañía"),
            'res_model': 'account.move',
            'domain': [('id', 'in', invoices.ids)],
            'view_mode': 'list,form',
        }
        if len(invoices) == 1:
            action.update(view_mode='form', res_id=invoices.id)
        return action

    # ------------------------------------------------------------------
    # Proceso
    # ------------------------------------------------------------------

    def _enteza_ic_procesar(self):
        for move in self:
            # sudo(): la configuración es de la compañía; el usuario sólo factura.
            if move.move_type in ('out_invoice', 'out_refund') and move.state == 'posted' \
                    and move.enteza_ic_estado != 'generada' \
                    and move.company_id.sudo().enteza_ic_owner_company_id:
                move._enteza_ic_procesar_una()

    def _enteza_ic_lineas_faltas(self):
        """Líneas de material físico que vienen de una venta de faltas de un alquiler.

        Se identifican por datos, no por texto: la línea de pedido no es de alquiler y su
        pedido lleva `rental_order_id` (lo pone «Facturar las Faltas» de rental_custom). Una
        rectificativa creada con «Revertir» conserva ese enlace (`sale`
        `_copy_data_extend_business_fields`). Las faltas creadas con el importador de hoja
        de cálculo no lo llevan y no entran.
        """
        self.ensure_one()
        return self.invoice_line_ids.filtered(
            lambda line: line.product_id.is_storable and line.sale_line_ids.filtered(
                lambda sl: not sl.is_rental and sl.order_id.rental_order_id))

    def _enteza_ic_procesar_una(self):
        self.ensure_one()
        lines = self._enteza_ic_lineas_faltas()
        if not lines:
            return
        origin_lines = self.env['account.move.line']
        if self.move_type == 'out_refund':
            # Sólo se rectifica lo que se facturó: una rectificativa de una factura de faltas
            # anterior al módulo (o que no generó nada) no tiene nada que rectificar en la dueña.
            origin_lines = self.reversed_entry_id.sudo().enteza_ic_enlace_ids.invoice_line_id
            if not origin_lines:
                return
        # Serializa dos procesos sobre la misma factura (publicación y botón a la vez). Tras
        # obtener el bloqueo se vuelve a mirar en la base de datos si otro ya la procesó.
        self.lock_for_update()
        Enlace = self.env['enteza.venta.intercompania.enlace'].sudo()
        if Enlace.search_count([('source_move_id', '=', self.id)]):
            self.enteza_ic_estado = 'generada'
            return
        try:
            # Todo o nada: factura de la dueña, su publicación y los enlaces.
            with self.env.cr.savepoint():
                invoice = self._enteza_ic_generar(lines, origin_lines)
        except Exception as error:  # noqa: BLE001 - no se bloquea la factura al cliente
            # La factura de la receptora ya está publicada y así se queda: un problema
            # interno entre compañías no puede impedir facturar al cliente. Queda pendiente,
            # con el motivo en el historial y un botón para reintentarlo.
            _logger.exception("Factura intercompañía pendiente en %s", self.name)
            message = error.args[0] if isinstance(error, UserError) else repr(error)
            self.enteza_ic_estado = 'pendiente'
            self.message_post(body=_(
                "No se ha podido crear la factura intercompañía del material perdido: %s",
                message))
            return
        self.enteza_ic_estado = 'generada'
        self.message_post(body=_(
            "Creada y publicada la factura intercompañía del material perdido: %s",
            invoice._get_html_link()))
        _logger.info("Factura intercompañía %s generada desde %s", invoice.id, self.name)

    def _enteza_ic_precio(self, product, owner, origin_lines):
        """Precio por unidad del producto (en su unidad de medida) para la dueña.

        En una rectificativa, el de la factura intercompañía original, para que se anule lo
        mismo que se cobró aunque el coste haya cambiado después. Si no, el coste del
        producto en la dueña (decisión del 2026-10-03).
        """
        if self.move_type == 'out_refund':
            origin = origin_lines.filtered(lambda line: line.product_id == product)[:1]
            if not origin:
                raise UserError(_(
                    "%s no estaba en la factura intercompañía original: no hay nada que "
                    "rectificar.", product.display_name))
            return origin.product_uom_id._compute_price(origin.price_unit, product.uom_id)
        cost = product.with_company(owner).standard_price
        if owner.currency_id.compare_amounts(cost, 0.0) <= 0:
            raise UserError(_(
                "%(product)s no tiene coste en %(company)s.",
                product=product.display_name, company=owner.name))
        return cost

    def _enteza_ic_cantidades(self, lines):
        """Cantidad por producto, en su unidad de medida."""
        qty_by_product = defaultdict(float)
        for line in lines:
            qty_by_product[line.product_id] += line.product_uom_id._compute_quantity(
                line.quantity, line.product_id.uom_id)
        return qty_by_product

    def _enteza_ic_generar(self, lines, origin_lines):
        """Crea y publica en la dueña la factura (o rectificativa) a esta compañía.

        Al publicarla, Inter-Company Transactions crea la de proveedor en esta compañía si
        aquí está activado «Generar facturas de proveedor».
        """
        company = self.company_id.sudo()
        owner = company.enteza_ic_owner_company_id
        journal = company.enteza_ic_journal_id
        if not journal or journal.company_id != owner:
            raise UserError(_(
                "Falta en la ficha de %(company)s el diario de ventas de %(owner)s para la "
                "factura intercompañía.", company=company.name, owner=owner.name))

        if self.move_type == 'out_refund':
            invoiced = self._enteza_ic_cantidades(origin_lines)
            for product, qty in self._enteza_ic_cantidades(lines).items():
                if product.uom_id.compare(qty, invoiced.get(product, 0.0)) > 0:
                    raise UserError(_(
                        "Se rectifican %(qty)s %(uom)s de %(product)s, más de las que se "
                        "facturaron a %(company)s.", qty=qty, uom=product.uom_id.name,
                        product=product.display_name, company=company.name))

        # sudo(): la factura es de la compañía dueña, a la que el usuario que publica puede no
        # tener acceso.
        invoice = self.env['account.move'].sudo().with_company(owner).create({
            'move_type': self.move_type,
            'company_id': owner.id,
            'journal_id': journal.id,
            'partner_id': company.partner_id.id,
            'invoice_date': self.invoice_date,
            'ref': self.name,
            'invoice_origin': self.name,
            'reversed_entry_id': origin_lines.move_id[:1].id,
            'invoice_line_ids': [Command.create({
                'sequence': sequence,
                'product_id': line.product_id.id,
                'quantity': line.product_uom_id._compute_quantity(
                    line.quantity, line.product_id.uom_id),
                'product_uom_id': line.product_id.uom_id.id,
                'price_unit': self._enteza_ic_precio(line.product_id, owner, origin_lines),
            }) for sequence, line in enumerate(lines, start=1)],
        })
        invoice.message_post(body=_(
            "Material perdido facturado por %(company)s en %(move)s.",
            company=company.name, move=self._get_html_link()))
        invoice.action_post()

        # La línea N de la factura es la línea N de `lines` (secuencia asignada arriba).
        invoice_lines = invoice.invoice_line_ids.sorted('sequence')
        self.env['enteza.venta.intercompania.enlace'].sudo().create([{
            'source_line_id': line.id,
            'owner_company_id': owner.id,
            'invoice_line_id': invoice_line.id,
            'product_id': line.product_id.id,
            'quantity': invoice_line.quantity,
        } for line, invoice_line in zip(lines, invoice_lines, strict=True)])
        return invoice
