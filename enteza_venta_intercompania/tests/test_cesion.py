from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestCesion(TransactionCase):
    """Escritas pero NO ejecutadas: en este hosting no hay `--test-enable`."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = cls.env.company
        cls.receiver = cls.env['res.company'].create({'name': 'Receptora de prueba'})
        cls.env.user.company_ids |= cls.receiver
        cls.product = cls.env['product.product'].create({
            'name': 'Silla de prueba',
            'type': 'consu',
            'is_storable': True,
            'rent_ok': True,
            'lst_price': 100.0,
        })
        warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.owner.id)], limit=1)
        quant = cls.env['stock.quant'].create({
            'product_id': cls.product.id,
            'location_id': warehouse.lot_stock_id.id,
            'inventory_quantity': 10,
        })
        quant.action_apply_inventory()

        # Cesión: la dueña alquila 10 a la receptora y las entrega.
        now = fields.Datetime.now()
        cls.cesion = cls.env['sale.order'].with_context(in_rental_app=True).create({
            'partner_id': cls.receiver.partner_id.id,
            'company_id': cls.owner.id,
            'event_date': fields.Date.today(),
            'rental_start_date': now,
            'rental_return_date': fields.Datetime.add(now, days=90),
            'enteza_cesion_intercompania': True,
            'enteza_cesion_warehouse_dest_id': cls.env['stock.warehouse'].search(
                [('company_id', '=', cls.receiver.id)], limit=1).id,
            'order_line': [(0, 0, {'product_id': cls.product.id, 'product_uom_qty': 10})],
        })
        cls.cesion.action_confirm()
        delivery = cls.cesion.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing')
        delivery.move_ids.quantity = 10
        delivery.move_ids.picked = True
        delivery.button_validate()
        cls.cesion_return = cls.cesion.picking_ids.filtered(
            lambda p: p.state not in ('done', 'cancel') and p != delivery)

    def test_cesion_exige_que_el_cliente_sea_otra_compania(self):
        with self.assertRaises(ValidationError):
            self.cesion.copy({'partner_id': self.env['res.partner'].create({'name': 'X'}).id,
                              'enteza_cesion_intercompania': True})

    def test_lineas_de_material_de_la_cesion_a_cero(self):
        self.assertEqual(self.cesion.order_line.price_unit, 0.0)

    def test_entrega_de_la_cesion_prepara_la_recepcion_en_la_receptora(self):
        recepcion = self.env['stock.picking'].search([
            ('enteza_cesion_origen_picking_id', 'in', self.cesion.picking_ids.ids)])
        self.assertEqual(len(recepcion), 1)
        self.assertEqual(recepcion.company_id, self.receiver)
        self.assertEqual(recepcion.picking_type_code, 'incoming')
        self.assertEqual(recepcion.owner_id, self.owner.partner_id)
        self.assertEqual(recepcion.move_ids.product_uom_qty, 10)
        self.assertNotEqual(recepcion.state, 'done', 'lo valida el almacén de la receptora')

    def test_devolucion_de_la_cesion_prepara_la_salida_en_la_receptora(self):
        self.cesion_return.move_ids.quantity = 3
        self.cesion_return.move_ids.picked = True
        self.cesion_return.with_context(cancel_backorder=False)._action_done()

        salida = self.env['stock.picking'].search([
            ('enteza_cesion_origen_picking_id', '=', self.cesion_return.id)])
        self.assertEqual(salida.company_id, self.receiver)
        self.assertEqual(salida.picking_type_code, 'outgoing')
        self.assertFalse(salida.owner_id)
        self.assertEqual(salida.move_ids.product_uom_qty, 3)
