"""Tipos de operación propios del préstamo, uno por almacén (PRP §6.1).

Por qué no se reutilizan los `OUT`/`IN` de cliente
--------------------------------------------------
Mezclar los traslados entre compañías con los albaranes de reparto haría ilegible el trabajo
diario del almacén: el operario vería préstamos entre sociedades en la misma lista que las
entregas a clientes, y no son lo mismo ni los prepara la misma persona.

Por qué se crean sobre la marcha y no como datos del módulo
------------------------------------------------------------
Los almacenes no existen cuando el módulo se instala, y sus ids no se pueden conocer desde un
XML. El PRP proponía una acción de configuración; sale más barato crearlos **la primera vez
que hacen falta**, que además hace que no haya que acordarse de configurar nada cuando el
cliente añada el tercer almacén.
"""

from odoo import _, api, fields, models


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    enteza_loan_out_type_id = fields.Many2one(
        'stock.picking.type', string='Operación de salida de préstamo', copy=False,
        help='Se crea solo la primera vez que este almacén presta material.',
    )
    enteza_loan_in_type_id = fields.Many2one(
        'stock.picking.type', string='Operación de entrada de préstamo', copy=False,
    )

    def _enteza_tipo_prestamo(self, salida):
        """Tipo de operación de préstamo de este almacén; lo crea si aún no existe."""
        self.ensure_one()
        campo = 'enteza_loan_out_type_id' if salida else 'enteza_loan_in_type_id'
        if self[campo]:
            return self[campo]

        transito = self.env['enteza.stock.loan']._ubicacion_transito()
        # `sudo()` y `with_company()`: quien dispara esto puede ser de la otra sociedad, y el
        # tipo de operación pertenece a la compañía del almacén.
        tipo = self.env['stock.picking.type'].sudo().with_company(self.company_id).create({
            'name': _('Préstamo · salida') if salida else _('Préstamo · entrada'),
            'code': 'outgoing' if salida else 'incoming',
            'sequence_code': 'PREOUT' if salida else 'PREIN',
            'warehouse_id': self.id,
            'company_id': self.company_id.id,
            # 🔴 En la 19 las dos ubicaciones por defecto son OBLIGATORIAS en el tipo de
            # operación (no lo eran en versiones anteriores). Sin ellas no se puede crear.
            'default_location_src_id': (
                self.lot_stock_id.id if salida else transito.id
            ),
            'default_location_dest_id': (
                transito.id if salida else self.lot_stock_id.id
            ),
        })
        self.sudo()[campo] = tipo
        return tipo
