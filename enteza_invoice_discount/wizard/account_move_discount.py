from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountMoveDiscount(models.TransientModel):
    _name = "account.move.discount"
    _description = "Descuento en factura"

    move_id = fields.Many2one(
        "account.move", default=lambda self: self.env.context.get("active_id"), required=True
    )
    discount_percentage = fields.Float(string="Descuento", digits="Discount")

    @api.constrains("discount_percentage")
    def _check_discount_percentage(self):
        for wizard in self:
            if wizard.discount_percentage > 1.0:
                raise ValidationError(_("El descuento no puede superar el 100%."))

    def action_apply_discount(self):
        self.ensure_one()
        # 🔴 A diferencia de sale.order.line, account.move.line.display_type es un
        # Selection `required=True`: una línea de producto normal vale 'product', nunca
        # False. `invoice_line_ids` ya viene filtrado por dominio a
        # ('product', 'line_section', 'line_subsection', 'line_note'), así que basta con
        # excluir las secciones/notas quedándonos solo con 'product'.
        lines = self.move_id.invoice_line_ids.filtered(lambda line: line.display_type == "product")
        if not lines:
            raise ValidationError(_("La factura no tiene líneas de producto a las que aplicar el descuento."))
        lines.write({"discount": self.discount_percentage * 100})
