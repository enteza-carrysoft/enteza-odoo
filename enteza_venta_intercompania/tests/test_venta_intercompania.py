from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestVentaIntercompania(AccountTestInvoicingCommon):
    """Escritas pero NO ejecutadas: en este hosting no hay `--test-enable`."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = cls.env.company
        cls.receiver_data = cls.setup_other_company(name='Receptora de prueba')
        cls.receiver = cls.receiver_data['company']
        cls.receiver.write({
            'enteza_ic_owner_company_id': cls.owner.id,
            'enteza_ic_journal_id': cls.company_data['default_journal_sale'].id,
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Copa de prueba',
            'type': 'consu',
            'is_storable': True,
            'rent_ok': True,
            'lst_price': 3.0,
        })
        cls.product.with_company(cls.owner).standard_price = 1.5
        cls.customer = cls.env['res.partner'].create({'name': 'Cliente final'})

    def _factura_de_faltas(self, qty):
        """Factura de la receptora a su cliente por `qty` unidades perdidas, sin publicar."""
        env = self.env(context=dict(self.env.context, allowed_company_ids=[self.receiver.id]))
        rental = env['sale.order'].with_context(in_rental_app=True).create({
            'partner_id': self.customer.id, 'company_id': self.receiver.id,
            'event_date': fields.Date.today(),
        })
        faltas = env['sale.order'].create({
            'partner_id': self.customer.id,
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

    def _rectificar(self, invoice, qty):
        refund = invoice._reverse_moves()
        refund.invoice_line_ids.quantity = qty
        refund.action_post()
        return refund

    def test_publicar_faltas_factura_a_coste_en_la_duena(self):
        invoice = self._factura_de_faltas(2)
        invoice.action_post()

        self.assertEqual(invoice.enteza_ic_estado, 'generada')
        factura_ic = invoice.enteza_ic_enlace_ids.invoice_id
        self.assertEqual(len(factura_ic), 1)
        self.assertEqual(factura_ic.state, 'posted')
        self.assertEqual(factura_ic.move_type, 'out_invoice')
        self.assertEqual(factura_ic.company_id, self.owner)
        self.assertEqual(factura_ic.partner_id, self.receiver.partner_id)
        self.assertEqual(factura_ic.journal_id, self.company_data['default_journal_sale'])
        self.assertEqual(factura_ic.invoice_line_ids.quantity, 2)
        self.assertEqual(factura_ic.invoice_line_ids.price_unit, 1.5, 'a coste de la dueña')

    def test_sin_configuracion_no_hace_nada(self):
        self.receiver.enteza_ic_owner_company_id = False
        invoice = self._factura_de_faltas(2)
        invoice.action_post()
        self.assertFalse(invoice.enteza_ic_estado)
        self.assertFalse(invoice.enteza_ic_enlace_ids)

    def test_sin_coste_queda_pendiente_sin_bloquear_la_factura(self):
        self.product.with_company(self.owner).standard_price = 0.0
        invoice = self._factura_de_faltas(2)
        invoice.action_post()
        self.assertEqual(invoice.state, 'posted', 'la factura al cliente no se bloquea')
        self.assertEqual(invoice.enteza_ic_estado, 'pendiente')
        self.assertFalse(invoice.enteza_ic_enlace_ids)

        self.product.with_company(self.owner).standard_price = 1.5
        invoice.action_enteza_ic_procesar()
        self.assertEqual(invoice.enteza_ic_estado, 'generada')

    def test_reprocesar_no_duplica(self):
        invoice = self._factura_de_faltas(2)
        invoice.action_post()
        invoice._enteza_ic_procesar_una()
        invoice.action_enteza_ic_procesar()
        self.assertEqual(len(invoice.enteza_ic_enlace_ids.invoice_id), 1)

    def test_rectificativa_en_espejo_al_precio_original(self):
        invoice = self._factura_de_faltas(5)
        invoice.action_post()
        factura_ic = invoice.enteza_ic_enlace_ids.invoice_id
        self.product.with_company(self.owner).standard_price = 9.0

        refund = self._rectificar(invoice, 2)

        rectificativa_ic = refund.enteza_ic_enlace_ids.invoice_id
        self.assertEqual(rectificativa_ic.move_type, 'out_refund')
        self.assertEqual(rectificativa_ic.state, 'posted')
        self.assertEqual(rectificativa_ic.reversed_entry_id, factura_ic)
        self.assertEqual(rectificativa_ic.invoice_line_ids.quantity, 2)
        self.assertEqual(rectificativa_ic.invoice_line_ids.price_unit, 1.5)

    def test_rectificativa_de_factura_no_procesada_no_hace_nada(self):
        self.receiver.enteza_ic_owner_company_id = False
        invoice = self._factura_de_faltas(2)
        invoice.action_post()
        self.receiver.enteza_ic_owner_company_id = self.owner

        refund = self._rectificar(invoice, 2)
        self.assertFalse(refund.enteza_ic_estado)
        self.assertFalse(refund.enteza_ic_enlace_ids)

    def test_diario_de_otra_compania_no_se_acepta(self):
        with self.assertRaises(ValidationError):
            self.receiver.enteza_ic_journal_id = self.receiver_data['default_journal_sale']
