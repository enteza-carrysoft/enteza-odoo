from odoo import fields, models
from odoo.tools import float_compare


class ProductProduct(models.Model):
    """Motor de disponibilidad del portal — no reimplementa, delega en el nativo (PRP §2.5,
    §6.1).

    `_enteza_portal_disponible` es una réplica de `RentalOrderLine._compute_qty_at_date`
    (`sale_stock_renting/models/sale_order_line.py`): se replica y no se llama porque el
    nativo es un `@api.depends` atado a una línea de pedido ya existente, y aquí hace falta
    preguntar por una cantidad hipotética antes de montar la línea (mientras el cliente edita
    la rejilla, todavía no hay `sale.order.line`).

    Ajuste ya verificado en este mismo repositorio (`enteza_prestamo_intercompania`,
    2026-08-02): `ignored_soline_id` en `_get_virtual_unavailable_qty_in_rent` SOLO debe
    pasarse si la línea que se ignora sigue en borrador. En cuanto se confirma existe un
    movimiento de stock real que `virtual_available` ya ha descontado, y esa suma existe
    precisamente para devolverlo; ignorar una línea ya confirmada lo resta dos veces. Se
    detectó con un pedido de 95 unidades y 80 en almacén dando un déficit de 110 en vez de 15.
    """
    _inherit = 'product.product'

    def _enteza_portal_disponible(self, desde, hasta, almacen, ignorar_linea=None):
        """Unidades realmente alquilables de este producto en [desde, hasta] en `almacen`.

        :param desde, hasta: `datetime` del periodo de alquiler solicitado
        :param almacen: `stock.warehouse` desde el que se serviría
        :param ignorar_linea: `sale.order.line` a excluir del cálculo (la propia línea que
            se está recalculando, para que la solicitud en curso no compita consigo misma)
        :return: cantidad libre, nunca negativa
        """
        self.ensure_one()
        ahora = fields.Datetime.now()
        if desde <= ahora:
            rentable = self.with_context(
                from_date=desde, to_date=hasta, warehouse_id=almacen.id).qty_available
        else:
            rentable = self.with_context(
                from_date=False, to_date=desde, warehouse_id=almacen.id).virtual_available
            ignorar_en_rent = (
                ignorar_linea.id
                if ignorar_linea and ignorar_linea.state == 'draft'
                else False
            )
            rentable += self._get_virtual_unavailable_qty_in_rent(
                pivot_date=desde, ignored_soline_id=ignorar_en_rent, warehouse_id=almacen.id,
            )

        alquilado = self._get_unavailable_qty(
            desde, hasta,
            ignored_soline_id=ignorar_linea.id if ignorar_linea else False,
            warehouse_id=almacen.id,
        )
        return max(rentable - alquilado, 0.0)

    def _enteza_portal_semaforo(self, qty_pedida, desde, hasta, almacen, ignorar_linea=None):
        """Color del semáforo (PRP §6.3). Nunca devuelve la cantidad libre, solo el color.

        :param qty_pedida: cantidad que el cliente tiene tecleada en la fila (0 si ninguna)
        :return: 'grey' | 'green' | 'amber' | 'red'
        """
        self.ensure_one()
        if not self.is_storable:
            return 'grey'

        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        libre = self._enteza_portal_disponible(desde, hasta, almacen, ignorar_linea=ignorar_linea)

        if float_compare(libre, 0.0, precision_digits=precision) <= 0:
            return 'red'
        if qty_pedida and float_compare(qty_pedida, 0.0, precision_digits=precision) > 0:
            if float_compare(libre, qty_pedida, precision_digits=precision) >= 0:
                return 'green'
            return 'amber'
        return 'green'
