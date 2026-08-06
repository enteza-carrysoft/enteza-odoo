from odoo import _, fields, models
from odoo.exceptions import ValidationError


class RentalOrderRenameWizard(models.TransientModel):
    _name = "rental.order.rename.wizard"
    _description = "Cambiar número de presupuesto de alquiler"

    order_id = fields.Many2one("sale.order", required=True, readonly=True)
    name = fields.Char(string="Nuevo número", required=True)

    def action_confirm(self):
        self.ensure_one()
        order = self.order_id
        new_name = (self.name or "").strip()
        if not order.is_rental_order or order.state not in ("draft", "sent"):
            raise ValidationError(_("El número solo puede modificarse antes de confirmar el pedido."))
        if not new_name or new_name == "/":
            raise ValidationError(_("Indica un número de presupuesto válido."))
        duplicate = self.env["sale.order"].sudo().search_count([
            ("name", "=", new_name),
            ("id", "!=", order.id),
        ])
        if duplicate:
            raise ValidationError(_("Ya existe un pedido con el número %s.") % new_name)
        old_name = order.name
        order.write({"name": new_name})
        order.message_post(body=_("Número de presupuesto modificado de %s a %s.") % (old_name, new_name))
        return {"type": "ir.actions.act_window_close"}
