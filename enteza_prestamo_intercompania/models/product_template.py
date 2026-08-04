from odoo import models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _compute_display_name(self):
        """Ídem `product.product._compute_display_name`: ver ese fichero para el porqué.

        `product_template_id` es el campo que el buscador de la línea usa por defecto —
        `product_id` está oculto salvo que el usuario active esa columna—, así que hace
        falta la misma corrección aquí.
        """
        super()._compute_display_name()
        self._enteza_anadir_disponible_alquiler()

    def _enteza_anadir_disponible_alquiler(self):
        motor = self.env['enteza.disponibilidad']
        desde, hasta, almacen = motor._enteza_contexto_periodo()
        if not almacen:
            return
        # Solo con una única variante: con varias, «disponible» no dice nada sin saber cuál,
        # y en el buscador todavía no se ha elegido ninguna.
        con_variante_unica = self.filtered(
            lambda plantilla: plantilla.is_storable and len(plantilla.product_variant_ids) == 1
        )
        if not con_variante_unica:
            return
        variantes = con_variante_unica.product_variant_ids
        disponible = motor.disponible(variantes, almacen, desde, hasta)
        for plantilla in con_variante_unica:
            variante = plantilla.product_variant_ids
            plantilla.display_name = motor._enteza_texto_disponible(
                plantilla.display_name,
                disponible.get(variante.id, 0.0),
                variante.uom_id.display_name,
            )
