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

    def _create_backorder_picking(self):
        """El backorder de un albarán del préstamo sigue siendo del préstamo (19.0.10.1.0).

        El nativo crea el backorder con `copy()`, y los dos campos son `copy=False` para que
        duplicar un albarán a mano no lo cuelgue de un préstamo. Sin esto, lo que el almacén
        valida en una segunda entrega no llega nunca al préstamo: no cuenta como enviado y la
        devolución propone devolver de menos.
        """
        backorder = super()._create_backorder_picking()
        if self.enteza_loan_id:
            backorder.write({
                'enteza_loan_id': self.enteza_loan_id.id,
                'enteza_devolucion': self.enteza_devolucion,
            })
        return backorder

    def _enteza_albaran_raiz(self):
        """El albarán original de una cadena de backorders (el propio si no lo es)."""
        self.ensure_one()
        albaran = self
        while albaran.backorder_id:
            albaran = albaran.backorder_id
        return albaran


class StockMove(models.Model):
    _inherit = 'stock.move'

    enteza_loan_line_id = fields.Many2one(
        'enteza.stock.loan.line', string='Línea de préstamo', copy=False, index=True,
        ondelete='set null',
        help='Permite ampliar un albarán existente sin duplicar movimientos cuando se '
             'acumula material nuevo en un traslado ya aprobado.',
    )

    def _prepare_move_split_vals(self, qty):
        """La parte que pasa al backorder en una entrega parcial conserva su línea de préstamo.

        Mismo motivo que `StockPicking._create_backorder_picking`: el campo es `copy=False`
        y `_split` crea el movimiento nuevo con `copy_data()`.
        """
        vals = super()._prepare_move_split_vals(qty)
        if self.enteza_loan_line_id:
            vals['enteza_loan_line_id'] = self.enteza_loan_line_id.id
        return vals
