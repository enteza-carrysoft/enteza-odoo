"""«Registrar faltas» desde el pedido de alquiler (19.0.1.16.0).

Es el camino cuando el alquiler no tiene albaranes: Enteza gestiona el almacén en papel y
desactiva «Traslado de alquiler» (decisión del 2026-10-07). Convive con «Facturar las Faltas»
del albarán de recogida, que sigue siendo el camino de los pedidos que sí tienen albaranes: el
botón del pedido solo se ofrece cuando no hay ninguno abierto.

El pedido de faltas que sale de aquí es el mismo que el del albarán (cabecera y líneas salen de
los mismos métodos de `sale.order`). La única diferencia es `missing_auto_validate`: al
confirmarlo, su salida se valida sola y la baja del material queda hecha y enlazada a la
factura.
"""

from odoo import _, fields, models
from odoo.exceptions import UserError


class RentalMissingWizard(models.TransientModel):
    _name = "rental.missing.wizard"
    _description = "Registrar faltas de un alquiler"

    order_id = fields.Many2one("sale.order", string="Pedido de alquiler", required=True,
                               readonly=True)
    line_ids = fields.One2many("rental.missing.wizard.line", "wizard_id", string="Material")

    def action_confirm(self):
        self.ensure_one()
        order = self.order_id
        if not order.missing_from_order_allowed:
            # Entre abrir la ventana y aceptar, alguien ha podido crear un albarán.
            raise UserError(_(
                "El pedido %s ya tiene albaranes abiertos: factura las faltas desde su "
                "recogida.", order.name,
            ))
        self.line_ids._check_quantities()

        missing = self.line_ids.filtered(lambda l: l.qty_missing > 0)
        sale_order = self.env["sale.order"]
        if missing:
            sale_order = self._create_missing_order(missing)
        else:
            order.message_post(body=_("Marcado como devuelto sin faltas."))

        order._mark_rental_returned()

        if not sale_order:
            return {"type": "ir.actions.act_window_close"}
        return {
            "type": "ir.actions.act_window",
            "name": _("Pedido de faltas"),
            "res_model": "sale.order",
            "view_mode": "form",
            "res_id": sale_order.id,
            "target": "current",
        }

    def _create_missing_order(self, lines):
        order = self.order_id
        partner = order.partner_invoice_id or order.partner_id
        SaleOrder = self.env["sale.order"]
        vals = order._prepare_missing_sale_order_vals(
            partner, order.company_id, order.name,
            [SaleOrder._prepare_missing_line_vals(l.product_id, l.qty_missing,
                                                  l.sale_line_id.product_uom_id)
             for l in lines],
            # Las unidades vuelven a Stock al marcar el pedido como devuelto: la baja sale
            # de ahí, no de la ubicación de Alquiler.
            False,
        )
        vals["missing_auto_validate"] = True
        sale_order = SaleOrder.create(vals)

        for line in lines:
            line.sale_line_id.qty_lost += line.qty_missing

        sale_order.message_post(body=_(
            "Generado al registrar las faltas del pedido de alquiler %s.",
            order._get_html_link(),
        ))
        order.message_post(body=_(
            "Faltas registradas y facturadas en %s.", sale_order._get_html_link(),
        ))
        return sale_order


class RentalMissingWizardLine(models.TransientModel):
    _name = "rental.missing.wizard.line"
    _description = "Línea de faltas de un alquiler"

    wizard_id = fields.Many2one("rental.missing.wizard", required=True, ondelete="cascade")
    sale_line_id = fields.Many2one("sale.order.line", required=True, readonly=True)
    product_id = fields.Many2one(related="sale_line_id.product_id", string="Producto")
    default_code = fields.Char(related="product_id.default_code", string="Referencia")
    qty_rented = fields.Float(related="sale_line_id.product_uom_qty", string="Alquilado")
    qty_lost_prev = fields.Float(related="sale_line_id.qty_lost",
                                 string="Ya facturado como faltas")
    qty_missing = fields.Float(string="Faltas", digits="Product Unit", default=0.0)

    def _check_quantities(self):
        errores = []
        for line in self:
            uom = line.sale_line_id.product_uom_id
            maximo = line.qty_rented - line.qty_lost_prev
            if uom.compare(line.qty_missing, 0.0) < 0:
                errores.append(_("%s: las faltas no pueden ser negativas.",
                                 line.product_id.display_name))
            elif uom.compare(line.qty_missing, maximo) > 0:
                errores.append(_(
                    "%(producto)s: se alquilaron %(alquilado)s y ya hay %(previas)s "
                    "facturadas como faltas; como mucho quedan %(maximo)s.",
                    producto=line.product_id.display_name, alquilado=line.qty_rented,
                    previas=line.qty_lost_prev, maximo=maximo,
                ))
        if errores:
            raise UserError("\n".join(errores))
