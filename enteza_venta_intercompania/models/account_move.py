import logging
from collections import defaultdict

from markupsafe import Markup

from odoo import _, fields, models
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
             "tiene, pero no se pudo preparar la venta (el motivo está en el historial).",
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
        posted.filtered(lambda m: m.move_type == 'out_invoice')._enteza_ic_procesar()
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
            if move.move_type == 'out_invoice' and move.state == 'posted' \
                    and move.enteza_ic_estado != 'generada':
                move._enteza_ic_procesar_una()

    def _enteza_ic_lineas_faltas(self):
        """Líneas de material físico que vienen de una venta de faltas de un alquiler.

        Se identifican por datos, no por texto: la línea de pedido no es de alquiler y su
        pedido lleva `rental_order_id` (lo pone «Facturar las Faltas» de rental_custom). Las
        faltas creadas con el importador de hoja de cálculo no llevan ese enlace y no entran.
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
        # Serializa dos procesos sobre la misma factura (publicación y botón a la vez). Tras
        # obtener el bloqueo se vuelve a mirar en la base de datos si otro ya la procesó.
        self.lock_for_update()
        Enlace = self.env['enteza.venta.intercompania.enlace'].sudo()
        if Enlace.search_count([('source_move_id', '=', self.id)]):
            self.enteza_ic_estado = 'generada'
            return
        try:
            # Todo o nada: ventas, factura, descuentos en los alquileres de cesión y enlaces.
            with self.env.cr.savepoint():
                invoices = self._enteza_ic_generar(lines)
        except Exception as error:  # noqa: BLE001 - no se bloquea la factura al cliente
            # La factura de la receptora ya está publicada y así se queda: un problema
            # interno entre compañías no puede impedir facturar al cliente. Queda pendiente,
            # con el motivo en el historial y un botón para reintentarlo.
            _logger.exception("Venta intercompañía pendiente en %s", self.name)
            message = error.args[0] if isinstance(error, UserError) else repr(error)
            self.enteza_ic_estado = 'pendiente'
            self.message_post(body=_(
                "No se ha podido preparar la venta intercompañía del material perdido: %s",
                message))
            return
        if not invoices:
            return
        self.enteza_ic_estado = 'generada'
        # En borrador la factura no tiene número todavía: se enlaza por su nombre visible.
        self.message_post(body=_(
            "Preparada en borrador la factura intercompañía del material perdido: %s",
            Markup(", ").join(invoice._get_html_link() for invoice in invoices)))
        _logger.info("Factura intercompañía %s generada desde %s", invoices.ids, self.name)

    def _enteza_ic_movimientos_cesion(self, product):
        """Devoluciones pendientes de alquileres de cesión hacia esta compañía.

        sudo(): son movimientos de la compañía dueña, a la que el usuario que publica puede
        no tener acceso.
        """
        moves = self.env['stock.move'].sudo().search([
            ('product_id', '=', product.id),
            ('state', 'not in', ('draft', 'done', 'cancel')),
            ('picking_id', '!=', False),
            ('sale_line_id.is_rental', '=', True),
            ('sale_line_id.order_id.enteza_cesion_company_dest_id', '=', self.company_id.id),
        ], order='date, id')
        return moves.filtered(lambda m: m.location_id == m.company_id.rental_loc_id)

    def _enteza_ic_repartir(self, lines):
        """Atribuye cada línea de faltas a devoluciones pendientes de cesión, por fecha.

        :return: lista de (línea de factura, movimiento de cesión, cantidad en la unidad del
            producto). Una línea cuyo producto no tiene ninguna cesión no se reparte: es
            material propio de la receptora.
        """
        allocations = []
        taken = defaultdict(float)
        for line in lines:
            candidates = self._enteza_ic_movimientos_cesion(line.product_id)
            if not candidates:
                continue
            uom = line.product_id.uom_id
            pending = line.product_uom_id._compute_quantity(line.quantity, uom)
            for stock_move in candidates:
                if uom.compare(pending, 0.0) <= 0:
                    break
                if stock_move.product_uom.compare(stock_move.qty_missing, 0.0) > 0:
                    raise UserError(_(
                        "El albarán %s de la cesión tiene faltas anotadas a mano sin facturar. "
                        "Hay que facturarlas o borrarlas antes.", stock_move.picking_id.name))
                free = stock_move.product_uom._compute_quantity(
                    stock_move.product_uom_qty, uom) - taken[stock_move]
                take = min(free, pending)
                if uom.compare(take, 0.0) > 0:
                    allocations.append((line, stock_move, take))
                    taken[stock_move] += take
                    pending -= take
            if uom.compare(pending, 0.0) > 0:
                raise UserError(_(
                    "Se facturan %(qty)s %(uom)s de %(product)s más de las que quedan "
                    "pendientes en los alquileres de cesión.",
                    qty=pending, uom=uom.name, product=line.product_id.display_name))
        return allocations

    def _enteza_ic_generar(self, lines):
        allocations = self._enteza_ic_repartir(lines)
        if not allocations:
            return self.env['sale.order']

        qty_by_picking = defaultdict(lambda: defaultdict(float))
        for _line, stock_move, qty in allocations:
            qty_by_picking[stock_move.picking_id][stock_move] += qty

        order_by_picking = {}
        orders = self.env['sale.order'].sudo()
        for picking, qty_by_move in qty_by_picking.items():
            for stock_move, qty in qty_by_move.items():
                stock_move.qty_missing = stock_move.product_id.uom_id._compute_quantity(
                    qty, stock_move.product_uom)
            # El picking viene en sudo (ver `_enteza_ic_movimientos_cesion`): el presupuesto
            # se crea en la compañía dueña por el camino normal de «Facturar las Faltas», con
            # la tarifa que esa compañía tenga para la receptora.
            order = picking.with_company(picking.company_id)._create_missing_sale_order()
            order.message_post(body=_(
                "Generado automáticamente al publicar %s, factura de faltas de %s.",
                self._get_html_link(), self.company_id.name))
            order.journal_id = picking.sale_id.enteza_cesion_journal_id
            order_by_picking[picking] = order
            orders |= order

        invoices = self._enteza_ic_facturar(orders)

        # sudo(): el usuario que publica sólo puede leer los enlaces (ir.model.access.csv).
        self.env['enteza.venta.intercompania.enlace'].sudo().create([{
            'source_line_id': line.id,
            'owner_company_id': stock_move.company_id.id,
            'cesion_order_id': stock_move.sale_line_id.order_id.id,
            'cesion_stock_move_id': stock_move.id,
            'sale_order_id': order_by_picking[stock_move.picking_id].id,
            'invoice_id': order_by_picking[stock_move.picking_id].invoice_ids[:1].id,
            'product_id': line.product_id.id,
            'quantity': qty,
        } for line, stock_move, qty in allocations])
        return invoices

    def _enteza_ic_facturar(self, orders):
        """Confirma las ventas de la dueña y crea su factura a la receptora, SIN publicarla.

        Confirmar sólo prepara el albarán de salida desde Alquiler (lo valida el almacén).
        Los artículos de alquiler se facturan por lo pedido (1.101 de 1.101, RPC del
        2026-09-28), así que se puede facturar sin esperar al albarán. La factura la revisa y
        publica una persona; al publicarla, Inter-Company Transactions crea la de proveedor
        en la receptora.
        """
        for order in orders:
            # El valor de `action_confirm` puede ser una acción (diálogo de otro módulo): si
            # el pedido no ha quedado confirmado, se dice en vez de facturar a medias.
            order.action_confirm()
            if order.state != 'sale':
                raise UserError(_(
                    "No se ha podido confirmar %s sin intervención: hay que revisarlo a mano.",
                    order.name))
        invoices = orders._create_invoices()
        for invoice in invoices:
            invoice.message_post(body=_(
                "Factura intercompañía por el material perdido facturado en %s (%s). "
                "Revisarla y publicarla.", self._get_html_link(), self.company_id.name))
        return invoices
