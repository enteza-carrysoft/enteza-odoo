from odoo import models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _compute_display_name(self):
        """Añade la disponibilidad de alquiler al nombre que ve el buscador de la línea.

        Petición del cliente (2026-08-04): al escribir en «Añadir un producto», el
        desplegable dice cuántas unidades hay libres para el periodo del pedido, sin tener
        que elegir el producto primero para verlo en el popover nativo
        (`qty_at_date_widget`, que solo aparece con la línea ya montada).

        Se engancha aquí y no en `name_search`/`web_name_search` porque es el texto que
        `web_name_search` (`addons/web/models/models.py` de la 19) usa tal cual para el
        desplegable: `record.display_name` sin `formatted_display_name` en contexto y
        `record.with_context(formatted_display_name=True).display_name` con él — y las dos
        pasan por aquí, así que basta un único sitio. No aparece en ningún otro rincón de
        Odoo por accidente: solo se toca cuando el contexto trae el periodo
        (`_enteza_contexto_periodo`), y ese contexto solo lo manda el buscador de producto
        de la línea de un pedido de alquiler (`views/sale_order_product_search_views.xml`).
        """
        super()._compute_display_name()
        self._enteza_anadir_disponible_alquiler()

    def _enteza_anadir_disponible_alquiler(self):
        motor = self.env['enteza.disponibilidad']
        desde, hasta, almacen = motor._enteza_contexto_periodo()
        if not almacen:
            return
        productos = self.filtered('is_storable')
        if not productos:
            return
        disponible = motor.disponible(productos, almacen, desde, hasta)
        for producto in productos:
            producto.display_name = motor._enteza_texto_disponible(
                producto.display_name,
                disponible.get(producto.id, 0.0),
                producto.uom_id.display_name,
            )
