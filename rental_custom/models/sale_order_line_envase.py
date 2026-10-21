# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
"""Envases en las líneas de alquiler (spec 005).

La línea va SIEMPRE en unidades y al precio de la unidad suelta (no se toca el cálculo de
precios); el almacén necesita saber cuántos envases coger, así que se muestra «Nº envases».
Spec 006: pedir en múltiplos del envase es solo una ADVERTENCIA (onchange), no un bloqueo:
la integración con el sistema legacy crea pedidos por API con cantidades sueltas.
"""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .product_envase import fmt_num


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    enteza_envase_count = fields.Float(
        string="Nº envases",
        compute='_compute_enteza_envase_count',
        digits=(16, 2),
        help="Cantidad ÷ unidades del envase del artículo. Vacío si el artículo no tiene "
             "envase. Solo informativo: no modifica la cantidad.",
    )

    @api.depends(
        'product_id', 'product_uom_qty', 'product_uom_id', 'display_type',
        'product_id.product_tmpl_id.uom_id',
        'product_id.product_tmpl_id.uom_ids.relative_factor',
        'product_id.product_tmpl_id.uom_ids.relative_uom_id')
    def _compute_enteza_envase_count(self):
        # Sin `compute_sudo`: se calcula con los derechos del usuario (AC18). Siempre se
        # asigna: un compute no almacenado sin asignar lanza ValueError.
        for line in self:
            line.enteza_envase_count = line._enteza_envase_numero()

    def _enteza_envase_numero(self):
        """Nº de envases de la línea (0.0 si no aplica)."""
        self.ensure_one()
        if self.display_type or not self.product_id:
            return 0.0
        envase = self.product_id._enteza_envase_uom()
        if not envase:
            return 0.0
        qty_base = self.product_id._enteza_a_unidad_base(
            self.product_uom_qty, self.product_uom_id)
        return round(qty_base / envase.relative_factor, 2)

    def _enteza_envase_lineas_a_validar(self):
        """Líneas de alquiler con producto. Se excluyen las de pedidos de faltas por la
        marca `rental_order_id` (no por `is_rental`: `_enteza_keep_missing_line_as_sale` lo
        pone a False DESPUÉS del `create`, cuando la restricción ya se ha evaluado)."""
        return self.filtered(
            lambda l: l.is_rental and l.product_id and not l.display_type
            and not l.order_id.rental_order_id)

    @api.onchange('product_id', 'product_uom_qty')
    def _onchange_enteza_envase_multiplo(self):
        """Advertencia (no bloqueante, spec 006) si la cantidad no es múltiplo del envase.
        Solo en el formulario: por API (`create`/`write`) no se avisa ni se rechaza."""
        for line in self._enteza_envase_lineas_a_validar():
            mensaje = line.product_id._enteza_envase_error_multiplo(
                line.product_uom_qty, line.product_uom_id)
            if mensaje:
                return {'warning': {'title': _("Cantidad no múltiplo del envase"),
                                    'message': mensaje}}

    @api.constrains('product_id', 'product_uom_id', 'is_rental')
    def _check_enteza_envase_unidad(self):
        """Con envase, la línea va en la unidad base. Separada de la anterior para que
        cambiar SOLO la cantidad de una línea antigua en otra unidad no la dispare."""
        for line in self._enteza_envase_lineas_a_validar():
            mensaje = line.product_id._enteza_envase_error_unidad(line.product_uom_id)
            if mensaje:
                raise ValidationError(mensaje)

    def _enteza_envase_label(self):
        """Texto del parte de recogida: «50 uds (2 envases de 25)», «25 uds (1 envase de
        25)»; sin envase solo la cantidad («40 uds»)."""
        self.ensure_one()
        if not self.product_id or self.display_type:
            return ''
        unidad = self.env.ref('uom.product_uom_unit', raise_if_not_found=False)
        nombre_uom = (_("uds") if not self.product_uom_id or self.product_uom_id == unidad
                      else self.product_uom_id.name)
        texto = "%s %s" % (fmt_num(self.product_uom_qty), nombre_uom)
        envase = self.product_id._enteza_envase_uom()
        if not envase:
            return texto
        numero = self._enteza_envase_numero()
        palabra = _("envase") if numero == 1 else _("envases")
        return "%s (%s %s de %s)" % (
            texto, fmt_num(numero), palabra, fmt_num(envase.relative_factor))


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _enteza_pickup_lines(self):
        """Líneas del parte de recogida: todas las de alquiler (decisión del usuario,
        2026-10-21) más las que el informe ya imprimía (no de alquiler con algo entregado).
        Secciones y notas quedan fuera. Orden del pedido."""
        self.ensure_one()
        return self.order_line.filtered(
            lambda l: not l.display_type and (l.is_rental or l.qty_delivered))
