"""Propuesta de devolución del material prestado (PRP §7.5).

Es una **propuesta**, no una ejecución (D2): el responsable ve las cifras, puede cambiar
cuánto se devuelve de cada artículo, y hasta que no acepta no se mueve nada.

La gracia del cálculo es no devolver material que la receptora va a volver a necesitar en
unos días: sería un viaje de ida y otro de vuelta para nada. Lo que decide es la ventana de
retención (parámetro, 7 días por defecto).
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class EntezaPrestamoDevolucion(models.TransientModel):
    _name = 'enteza.prestamo.devolucion'
    _description = 'Proponer la devolución de un préstamo'

    loan_id = fields.Many2one(
        'enteza.stock.loan', string='Préstamo', required=True, readonly=True,
    )
    line_ids = fields.One2many(
        'enteza.prestamo.devolucion.line', 'wizard_id', string='Material prestado',
    )

    def action_devolver(self):
        """Genera el par de albaranes de vuelta con lo que el responsable haya decidido."""
        self.ensure_one()
        cantidades = {
            linea.loan_line_id: linea.qty_devolver
            for linea in self.line_ids
            if linea.qty_devolver > 0
        }
        if not cantidades:
            raise UserError(_(
                'No has marcado nada para devolver. Si quieres retener todo el material, '
                'cierra esta ventana sin más.'
            ))
        for linea in self.line_ids:
            if linea.qty_devolver > linea.qty_pendiente:
                raise UserError(_(
                    'No se pueden devolver %(pide)s de %(producto)s: solo quedan '
                    '%(hay)s pendientes.',
                    pide=linea.qty_devolver,
                    producto=linea.product_id.display_name,
                    hay=linea.qty_pendiente,
                ))

        albaranes = self.loan_id.sudo()._crear_albaranes_devolucion(cantidades)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Albaranes de devolución'),
            'res_model': 'stock.picking',
            'domain': [('id', 'in', albaranes.ids)],
            'view_mode': 'list,form',
        }


class EntezaPrestamoDevolucionLine(models.TransientModel):
    _name = 'enteza.prestamo.devolucion.line'
    _description = 'Línea de la propuesta de devolución'

    wizard_id = fields.Many2one(
        'enteza.prestamo.devolucion', required=True, ondelete='cascade',
    )
    loan_line_id = fields.Many2one(
        'enteza.stock.loan.line', string='Línea de préstamo', required=True,
    )
    product_id = fields.Many2one('product.product', string='Producto', readonly=True)
    qty_pendiente = fields.Float(
        string='Sin devolver', readonly=True, digits='Product Unit of Measure',
    )
    necesita_receptora = fields.Float(
        string='Necesita quien lo tiene', readonly=True,
        digits='Product Unit of Measure',
        help='Pico de demanda de la compañía receptora en la ventana de retención.',
    )
    propio_receptora = fields.Float(
        string='Con lo suyo cubre', readonly=True, digits='Product Unit of Measure',
        help='Lo que la receptora tiene en almacén sin contar lo prestado.',
    )
    necesita_prestamista = fields.Float(
        string='Le falta a quien lo prestó', readonly=True,
        digits='Product Unit of Measure',
        help='Si la compañía que prestó el material también lo necesita, su necesidad '
             'manda: es suyo. La retención se recorta en esa cantidad.',
    )
    qty_retener = fields.Float(
        string='Se queda', readonly=True, digits='Product Unit of Measure',
    )
    # La única editable: la propuesta es una propuesta.
    qty_devolver = fields.Float(string='Devolver', digits='Product Unit of Measure')

    @api.onchange('qty_devolver')
    def _onchange_qty_devolver(self):
        for linea in self:
            linea.qty_retener = max(0.0, linea.qty_pendiente - linea.qty_devolver)
