from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestFacturarFaltas(TransactionCase):
    """`action_create_sale_order` factura las faltas de CUALQUIER albarán.

    Hasta el 12/08/2026 el botón sólo salía en albaranes de alquiler que fuesen backorder y
    no estuviesen validados, y encima estaba restringido a un grupo que no tenía ningún
    usuario asignado —así que no aparecía nunca, en ningún albarán—. Ahora decide el almacén:
    el botón está siempre y el método sólo se niega a facturar dos veces el mismo albarán o a
    crear un pedido vacío.
    """

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Cliente de faltas'})
        self.product = self.env['product.product'].create({
            'name': 'Artículo de faltas',
            'is_storable': True,
            'lst_price': 30.0,
        })
        self.picking_type = self.env.ref('stock.picking_type_in')

    def _crear_albaran(self, qty=4):
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.picking_type.id,
            'partner_id': self.partner.id,
            'location_id': self.picking_type.default_location_src_id.id
            or self.env.ref('stock.stock_location_customers').id,
            'location_dest_id': self.picking_type.default_location_dest_id.id,
        })
        self.env['stock.move'].create({
            'picking_id': picking.id,
            'product_id': self.product.id,
            'product_uom_qty': qty,
            'product_uom': self.product.uom_id.id,
            'location_id': picking.location_id.id,
            'location_dest_id': picking.location_dest_id.id,
        })
        return picking

    def test_factura_faltas_sin_ser_backorder_ni_alquiler(self):
        """El caso que antes abortaba: un albarán normal, sin backorder ni pedido detrás."""
        picking = self._crear_albaran(qty=4)
        self.assertFalse(picking.backorder_id)
        self.assertFalse(picking.sale_id)

        picking.action_create_sale_order()

        pedido = picking.sale_order_id
        self.assertTrue(pedido, 'no se ha creado el pedido de faltas')
        self.assertEqual(pedido.partner_id, self.partner)
        self.assertFalse(pedido.is_rental_order)
        self.assertEqual(len(pedido.order_line), 1)
        self.assertEqual(pedido.order_line.product_uom_qty, 4)
        self.assertFalse(pedido.order_line.is_rental)

    def test_no_factura_dos_veces_el_mismo_albaran(self):
        picking = self._crear_albaran()
        picking.action_create_sale_order()
        with self.assertRaises(UserError):
            picking.action_create_sale_order()

    def test_no_crea_pedido_vacio(self):
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.picking_type.id,
            'partner_id': self.partner.id,
            'location_id': self.env.ref('stock.stock_location_customers').id,
            'location_dest_id': self.picking_type.default_location_dest_id.id,
        })
        with self.assertRaises(UserError):
            picking.action_create_sale_order()
