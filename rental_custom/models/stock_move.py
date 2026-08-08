from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    qty_missing = fields.Float(
        string="Faltas",
        default=0.0,
        digits='Product Unit',
        help="Atajo para registrar el recuento de faltas directamente en el albarán: al "
             "escribir aquí las unidades que no han vuelto, la columna \"Hecho\" se "
             "recalcula sola restándolas de la demanda. Alternativa a la app de Código de "
             "Barras cuando no se ha usado para contar la devolución.",
    )

    @api.onchange('qty_missing')
    def _onchange_qty_missing(self):
        for move in self:
            move.quantity = max(move.product_uom_qty - move.qty_missing, 0.0)
