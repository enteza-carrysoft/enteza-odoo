from odoo import fields, models


class VentaIntercompaniaEnlace(models.Model):
    """Una fila por cada línea de factura de faltas que se ha facturado a la dueña.

    Es la trazabilidad de ida y vuelta: línea de la factura de faltas de la receptora →
    línea de la factura intercompañía de la dueña.
    """
    _name = 'enteza.venta.intercompania.enlace'
    _description = 'Venta intercompañía de material perdido'
    _order = 'id desc'

    source_line_id = fields.Many2one(
        'account.move.line', string="Línea de la factura de faltas",
        required=True, readonly=True, index=True, ondelete='cascade')
    source_move_id = fields.Many2one(
        related='source_line_id.move_id', string="Factura de faltas", store=True, index=True)
    company_id = fields.Many2one(
        related='source_move_id.company_id', string="Compañía receptora", store=True)
    owner_company_id = fields.Many2one(
        'res.company', string="Compañía dueña", required=True, readonly=True)
    # 'restrict': borrar la factura intercompañía dejaría la de faltas como procesada sin
    # nada al otro lado. Se rectifica, no se borra.
    invoice_line_id = fields.Many2one(
        'account.move.line', string="Línea de la factura intercompañía", readonly=True,
        index=True, ondelete='restrict')
    invoice_id = fields.Many2one(
        related='invoice_line_id.move_id', string="Factura intercompañía", store=True)
    product_id = fields.Many2one('product.product', string="Producto", required=True, readonly=True)
    quantity = fields.Float(string="Cantidad", digits='Product Unit', readonly=True)

    _source_line_uniq = models.UniqueIndex(
        '(source_line_id)', "Esta línea de factura ya se facturó a la compañía dueña.")
