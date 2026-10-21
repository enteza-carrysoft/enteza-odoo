# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
"""Definición ÚNICA de «envase» de un artículo (spec 005).

En la 19 un envase es una unidad de medida (`uom.uom`) enlazada al artículo en
`product.template.uom_ids` («Packagings»/«Envases»). Todo lo demás (líneas de alquiler, parte
de recogida, portal de clientes) pregunta aquí, para que la regla no se repita ni se desvíe.
"""
import math

from odoo import _, models
from odoo.tools import float_compare


def fmt_num(value, digits=2):
    """Número en castellano sin ceros finales: 30 -> «30», 1.2 -> «1,2», 12.5 -> «12,5»."""
    texto = ('%.*f' % (digits, round(value or 0.0, digits))).rstrip('0').rstrip('.')
    if texto in ('', '-0'):
        texto = '0'
    return texto.replace('.', ',')


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _enteza_envase_uom(self):
        """Envase del artículo (`uom.uom`, vacío si no tiene).

        Valen las unidades de `uom_ids` cuya unidad de referencia es la unidad base del
        artículo y cuyo factor es > 1; con varias se usa la de menor factor (y, a igualdad,
        la de menor id). Factor <= 1, otra referencia o encadenadas se ignoran.
        """
        self.ensure_one()
        candidatas = self.uom_ids.filtered(
            lambda uom: uom.relative_uom_id == self.uom_id and uom.relative_factor > 1)
        if not candidatas:
            return self.env['uom.uom']
        return min(candidatas, key=lambda uom: (uom.relative_factor, uom.id))


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _enteza_envase_uom(self):
        """Los métodos de la plantilla no se heredan por `_inherits`: se delegan."""
        self.ensure_one()
        return self.product_tmpl_id._enteza_envase_uom()

    def _enteza_envase_nombre(self):
        """Nombre sin «[referencia]», como en los mensajes de la spec."""
        self.ensure_one()
        return self.with_context(display_default_code=False).display_name

    def _enteza_a_unidad_base(self, qty, uom):
        """`qty` expresada en la unidad base del artículo (sin redondear)."""
        self.ensure_one()
        base = self.uom_id
        if not uom or uom == base:
            return qty
        return uom._compute_quantity(qty, base, round=False, raise_if_failure=False)

    def _enteza_envase_error_multiplo(self, qty, uom):
        """Mensaje de error si `qty` (en `uom`) no vale para el envase del artículo; si
        vale, o el artículo no tiene envase, `False`. Respeta la precisión de la unidad
        base (50,0000001 se acepta). El cero es múltiplo; los negativos se rechazan."""
        self.ensure_one()
        envase = self._enteza_envase_uom()
        if not envase:
            return False
        rounding = self.uom_id.rounding
        tamano = envase.relative_factor
        qty_base = self._enteza_a_unidad_base(qty, uom)
        nombre = self._enteza_envase_nombre()
        if float_compare(qty_base, 0.0, precision_rounding=rounding) < 0:
            return _("%(nombre)s: la cantidad no puede ser negativa (%(qty)s uds).",
                     nombre=nombre, qty=fmt_num(qty_base))
        multiplos = round(qty_base / tamano)
        if float_compare(multiplos * tamano, qty_base, precision_rounding=rounding) == 0:
            return False
        inferior = math.floor(qty_base / tamano) * tamano
        if inferior:
            propuesta = _("%(a)s o %(b)s", a=fmt_num(inferior), b=fmt_num(inferior + tamano))
        else:
            propuesta = fmt_num(tamano)  # no se propone 0
        return _("%(nombre)s: %(qty)s uds no es múltiplo del envase de %(n)s. "
                 "Prueba con %(propuesta)s.",
                 nombre=nombre, qty=fmt_num(qty_base), n=fmt_num(tamano),
                 propuesta=propuesta)

    def _enteza_envase_error_unidad(self, uom):
        """Mensaje de error si el artículo tiene envase y `uom` no es su unidad base."""
        self.ensure_one()
        envase = self._enteza_envase_uom()
        if not envase or not uom or uom == self.uom_id:
            return False
        return _("%(nombre)s: este artículo se alquila por envases de %(n)s y la línea "
                 "tiene que ir en %(base)s, su unidad base, no en %(uom)s. El número de "
                 "envases se calcula solo.",
                 nombre=self._enteza_envase_nombre(), n=fmt_num(envase.relative_factor),
                 base=self.uom_id.name, uom=uom.name)
