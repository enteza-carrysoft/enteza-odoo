"""Enlace entre los albaranes del traslado y el préstamo que los generó.

El préstamo avanza de estado **cuando el almacén valida el albarán**, no cuando alguien
pulsa un botón en el documento de préstamo. Es lo que hace que el estado diga la verdad: si
dice `in_transit` es porque el material ha salido de verdad de las estanterías.
"""

from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    enteza_loan_id = fields.Many2one(
        'enteza.stock.loan', string='Préstamo entre compañías', copy=False, index=True,
        ondelete='set null',
    )

    enteza_devolucion = fields.Boolean(
        string='Devolución de préstamo', copy=False,
        help='Distingue el viaje de vuelta del de ida: los dos usan los mismos tipos de '
             'operación, cambiados de bando.',
    )

    def _action_done(self):
        """Avisa al préstamo cuando su albarán se valida.

        Se engancha en `_action_done` y no en `button_validate` a propósito: `button_validate`
        es el botón, y por debajo hay más caminos que acaban validando un albarán (asistentes
        de backorder, procesado inmediato, llamadas de otros módulos). `_action_done` es por
        donde pasan todos.
        """
        resultado = super()._action_done()
        # `sudo()`: el albarán de salida lo valida el almacén de la PRESTAMISTA y el de
        # entrada el de la RECEPTORA. Cada uno tiene que poder mover el estado del mismo
        # documento, que pertenece a la otra compañía en uno de los dos casos.
        for albaran in self.filtered('enteza_loan_id'):
            albaran.enteza_loan_id.sudo()._enteza_albaran_validado(albaran)
        return resultado


class StockMove(models.Model):
    _inherit = 'stock.move'

    enteza_loan_line_id = fields.Many2one(
        'enteza.stock.loan.line', string='Línea de préstamo', copy=False, index=True,
        ondelete='set null',
        help='Permite ampliar un albarán existente sin duplicar movimientos cuando se '
             'acumula material nuevo en un traslado ya aprobado.',
    )
