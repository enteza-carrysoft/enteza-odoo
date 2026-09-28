from odoo import models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _get_pricelist_price(self):
        """Las líneas de material de una cesión van a 0 €.

        La cuota simbólica de la cesión se cobra con una línea de servicio aparte (decisión A
        del 2026-09-28): las reglas de tarifa no cambian el precio de alquiler, que sale de
        `product.pricing`, así que ponerlo por tarifa exigiría un precio por artículo.
        """
        if self.is_rental and self.order_id.enteza_cesion_intercompania:
            return 0.0
        return super()._get_pricelist_price()

    def _generate_delay_line(self, qty_returned):
        """Sin recargo por retraso al devolver material cedido.

        La cesión dura meses y su fecha de devolución es orientativa. Método de
        `sale_renting` leído en la 18 Enterprise (no legible en la 19): si en la 19 se llama
        distinto, esta anulación simplemente no se usa.
        """
        if self.order_id.enteza_cesion_intercompania:
            return
        return super()._generate_delay_line(qty_returned)
