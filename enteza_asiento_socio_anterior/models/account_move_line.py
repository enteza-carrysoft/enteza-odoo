from odoo import models

# Tipos de línea que no son un apunte de datos real (secciones y notas): nunca llevan socio.
_NON_DATA_DISPLAY_TYPES = ("line_section", "line_subsection", "line_note")


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _compute_partner_id(self):
        # account.move.line._compute_partner_id (núcleo) solo copia el socio de la
        # cabecera del asiento (move_id.partner_id), que en un asiento manual
        # (move_type='entry') casi nunca está rellena. Aquí, solo para ese caso, si la
        # línea sigue sin socio tras el compute nativo, se copia el de la última línea
        # de datos anterior del mismo asiento — el mismo momento en que Odoo ya
        # autocompleta otros campos (cantidad, UoM…) al añadir una línea nueva.
        super()._compute_partner_id()
        for line in self:
            if (
                line.partner_id
                or line.move_id.move_type != "entry"
                or line.display_type in _NON_DATA_DISPLAY_TYPES
            ):
                continue
            lineas_anteriores = line.move_id.line_ids.filtered(
                lambda l: l.id != line.id
                and l.partner_id
                and l.display_type not in _NON_DATA_DISPLAY_TYPES
            )
            if lineas_anteriores:
                line.partner_id = lineas_anteriores[-1].partner_id
