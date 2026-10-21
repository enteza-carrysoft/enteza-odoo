"""Envases en el portal (spec 005, AC15).

La definición de envase y los mensajes viven en `rental_custom`
(`product.product._enteza_envase_error_multiplo`); aquí solo se reúnen para el portal. Fichero
aparte porque `sale_order.py` ya supera con mucho el límite de líneas.
"""
from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _enteza_portal_errores_envase(self, cambios):
        """Mensajes (en castellano, los mismos que el backend) de los `cambios` que no
        respetan el envase del artículo.

        :param cambios: pares `(producto, qty)` que se van a crear o cuya cantidad cambia,
            con `qty` en la unidad base del artículo (el portal siempre pide en ella).
        :return: lista de mensajes; vacía si todo vale o el artículo no tiene envase.
        """
        errores = []
        for producto, qty in cambios:
            mensaje = producto._enteza_envase_error_multiplo(qty, producto.uom_id)
            if mensaje:
                errores.append(mensaje)
        return errores
