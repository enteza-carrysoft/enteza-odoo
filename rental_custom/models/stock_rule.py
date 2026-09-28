from odoo import models


class StockRule(models.Model):
    _inherit = 'stock.rule'

    def _get_stock_move_values(self, product_id, product_qty, product_uom, location_dest_id, name,
                               origin, company_id, values):
        """La venta de faltas saca el material de la ubicación de Alquiler, no de Stock.

        Las unidades perdidas nunca volvieron: siguen en «Customers/Alquiler». Hasta el
        2026-09-28 el albarán de la venta de faltas salía de Stock (se cancelaba a mano, 59 de
        60) y lo perdido se quedaba para siempre en Alquiler como existencia fantasma.

        El movimiento lleva la línea de la venta de faltas, que NO es de alquiler: así
        `sale_stock_renting` no la suma a `qty_returned` del alquiler, que ya la contó
        «Facturar las Faltas».
        """
        move_values = super()._get_stock_move_values(
            product_id, product_qty, product_uom, location_dest_id, name, origin, company_id, values)
        sale_line_id = values.get('sale_line_id')
        if not sale_line_id or self.picking_type_id.code != 'outgoing':
            return move_values
        order = self.env['sale.order.line'].browse(sale_line_id).order_id
        rental_loc = order.company_id.rental_loc_id
        # Sólo en el primer paso de la entrega (el que sale de Stock), para no alterar
        # entregas en varios pasos.
        if order.missing_from_rental_location and rental_loc \
                and self.location_src_id == self.picking_type_id.warehouse_id.lot_stock_id:
            move_values['location_id'] = rental_loc.id
        return move_values
