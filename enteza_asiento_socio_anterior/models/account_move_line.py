from odoo import api, models

# Tipos de línea que no son un apunte de datos real (secciones y notas): nunca llevan socio.
_NON_DATA_DISPLAY_TYPES = ("line_section", "line_subsection", "line_note")


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # 🔴 La primera versión heredaba _compute_partner_id (compute='...', precompute=True,
    # sin @api.depends). El precompute nativo solo se garantiza en create(), no al ir
    # tabulando por la rejilla editable sin guardar todavía, así que en el flujo real
    # (añadir línea → tabular) nunca llegaba a dispararse. El onchange sí está garantizado
    # por Odoo para ver las líneas hermanas ya escritas en pantalla aunque el asiento no se
    # haya guardado — es el mecanismo correcto para este caso.
    @api.onchange("account_id")
    def _onchange_account_id_socio_anterior(self):
        if (
            self.partner_id
            or self.move_id.move_type != "entry"
            or self.display_type in _NON_DATA_DISPLAY_TYPES
        ):
            return
        lineas_anteriores = self.move_id.line_ids.filtered(
            lambda l: l.id != self.id
            and l.partner_id
            and l.display_type not in _NON_DATA_DISPLAY_TYPES
        )
        if lineas_anteriores:
            self.partner_id = lineas_anteriores[-1].partner_id
