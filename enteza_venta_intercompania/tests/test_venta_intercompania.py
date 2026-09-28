from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestVentaIntercompania(TransactionCase):
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
            'order_line': [(0, 0, {'product_id': cls.product.id, 'product_uom_qty': 10})],
        })
        cls.cesion.action_confirm()
        delivery = cls.cesion.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing')
        delivery.move_ids.quantity = 10
        delivery.move_ids.picked = True
        delivery.button_validate()
        cls.cesion_return = cls.cesion.picking_ids.filtered(
            lambda p: p.state not in ('done', 'cancel') and p != delivery)

    def _factura_de_faltas(self, qty):
        """Factura de la receptora a su cliente por `qty` unidades perdidas."""
        env = self.env(context=dict(self.env.context, allowed_company_ids=[self.receiver.id]))
        customer = env['res.partner'].create({'name': 'Cliente final'})
        rental = env['sale.order'].with_context(in_rental_app=True).create({
            'partner_id': customer.id, 'company_id': self.receiver.id,
            'event_date': fields.Date.today(),
        })
        faltas = env['sale.order'].create({
            'partner_id': customer.id,
            'company_id': self.receiver.id,
            'rental_order_id': rental.id,
            'is_rental_order': False,
            'order_line': [(0, 0, {
                'product_id': self.product.id, 'product_uom_qty': qty, 'is_rental': False,
            })],
        })
        faltas.action_confirm()
        faltas.order_line.qty_delivered = qty
        return faltas._create_invoices()

    def test_cesion_exige_que_el_cliente_sea_otra_compania(self):
        with self.assertRaises(ValidationError):
            self.cesion.copy({'partner_id': self.env['res.partner'].create({'name': 'X'}).id,
                              'enteza_cesion_intercompania': True})

    def test_publicar_faltas_prepara_la_venta_y_descuenta_la_cesion(self):
        invoice = self._factura_de_faltas(2)
        invoice.action_post()

        self.assertEqual(invoice.enteza_ic_estado, 'generada')
        venta = invoice.enteza_ic_enlace_ids.sale_order_id
        self.assertEqual(len(venta), 1)
        self.assertEqual(venta.company_id, self.owner)
        self.assertEqual(venta.partner_id.commercial_partner_id, self.receiver.partner_id)
        self.assertEqual(venta.state, 'draft', 'nada se confirma solo')
        self.assertEqual(venta.order_line.product_uom_qty, 2)
        self.assertEqual(self.cesion_return.move_ids.product_uom_qty, 8)
        self.assertEqual(self.cesion.order_line.qty_lost, 2)

    def test_reprocesar_no_duplica(self):
        invoice = self._factura_de_faltas(2)
        invoice.action_post()
        invoice._enteza_ic_procesar_una()
        invoice.action_enteza_ic_procesar()
        self.assertEqual(len(invoice.enteza_ic_enlace_ids.sale_order_id), 1)
        self.assertEqual(self.cesion_return.move_ids.product_uom_qty, 8)

    def test_mas_faltas_que_pendiente_queda_pendiente_sin_crear_nada(self):
        invoice = self._factura_de_faltas(20)
        invoice.action_post()
        self.assertEqual(invoice.state, 'posted', 'la factura al cliente no se bloquea')
        self.assertEqual(invoice.enteza_ic_estado, 'pendiente')
        self.assertFalse(invoice.enteza_ic_enlace_ids)
        self.assertEqual(self.cesion_return.move_ids.product_uom_qty, 10)

    def test_facturacion_acumulativa(self):
        self._factura_de_faltas(1).action_post()
        self._factura_de_faltas(2).action_post()
        self.assertEqual(self.cesion_return.move_ids.product_uom_qty, 7)
        self.assertEqual(self.cesion.order_line.qty_lost, 3)
