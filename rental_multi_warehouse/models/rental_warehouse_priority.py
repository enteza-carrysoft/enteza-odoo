# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class RentalWarehousePriority(models.Model):
    """
    Lista ordenada de almacenes disponibles para completar alquileres.
    El algoritmo recorre esta lista en orden de secuencia cuando el
    almacén preferente del pedido no tiene stock suficiente.
    """
    _name = 'rental.warehouse.priority'
    _description = 'Prioridad de almacenes para alquiler'
    _order = 'sequence, id'

    sequence = fields.Integer(
        string='Prioridad',
        default=10,
        help='Menor número = mayor prioridad. '
             'El almacén del pedido siempre se consulta primero.',
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Almacén',
        required=True,
        ondelete='cascade',
    )
    is_active = fields.Boolean(
        string='Activo',
        default=True,
        help='Desactivar para excluir temporalmente este almacén.',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        related='warehouse_id.company_id',
        store=True,
        readonly=True,
    )
    name = fields.Char(
        related='warehouse_id.name',
        string='Nombre',
        readonly=True,
    )

    _sql_constraints = [
        ('warehouse_unique',
         'UNIQUE(warehouse_id)',
         'Cada almacén solo puede aparecer una vez en la lista de prioridad.'),
    ]

    @api.model
    def get_ordered_warehouses(self, exclude_warehouse=None):
        """
        Devuelve los almacenes activos ordenados por prioridad,
        opcionalmente excluyendo uno (el preferente del pedido).
        """
        domain = [('is_active', '=', True)]
        if exclude_warehouse:
            domain.append(('warehouse_id', '!=', exclude_warehouse.id))
        return self.search(domain).mapped('warehouse_id')
