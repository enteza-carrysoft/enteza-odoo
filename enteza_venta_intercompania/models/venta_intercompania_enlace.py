from odoo import fields, models


class VentaIntercompaniaEnlace(models.Model):
    """Una fila por cada tramo de línea de factura de faltas atribuido a una cesión.

    Es la trazabilidad de ida y vuelta: factura de faltas de la receptora → alquiler de
    cesión de la dueña → presupuesto de venta de la dueña a la receptora.
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
    cesion_order_id = fields.Many2one(
        'sale.order', string="Alquiler de cesión", readonly=True)
    cesion_stock_move_id = fields.Many2one(
        'stock.move', string="Movimiento de devolución de la cesión", required=True,
        readonly=True, ondelete='restrict')
    # 'restrict': borrar el presupuesto no puede dejar la factura como no procesada, porque
    # la demanda del alquiler de cesión ya se descontó. Se cancela, no se borra.
    sale_order_id = fields.Many2one(
        'sale.order', string="Venta intercompañía", required=True, readonly=True,
        ondelete='restrict')
    product_id = fields.Many2one('product.product', string="Producto", required=True, readonly=True)
    quantity = fields.Float(string="Cantidad", digits='Product Unit', readonly=True)

    _enlace_uniq = models.UniqueIndex(
        '(source_line_id, cesion_stock_move_id)',
        "Esta línea de factura ya se atribuyó a ese alquiler de cesión.")
