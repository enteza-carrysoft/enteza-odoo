# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    rental_transfer_day = fields.Selection(
        [
            ('0', 'Lunes'),
            ('1', 'Martes'),
            ('2', 'Miércoles'),
            ('3', 'Jueves'),
            ('4', 'Viernes'),
            ('5', 'Sábado'),
            ('6', 'Domingo'),
        ],
        string='Día de traslado inter-almacén',
        default='1',
        config_parameter='rental_multi_wh.transfer_day',
        help='Día de la semana en que se programan los traslados '
             'inter-almacén. Se elegirá el día de esta semana anterior '
             'a la fecha de entrega del alquiler.',
    )
    rental_transfer_lead_days = fields.Integer(
        string='Días mínimos de antelación',
        default=2,
        config_parameter='rental_multi_wh.transfer_lead_days',
        help='Días laborables mínimos de antelación para programar '
             'un traslado inter-almacén. Si la fecha calculada es '
             'demasiado cercana, se usará la fecha de hoy.',
    )
    rental_auto_return_transfer = fields.Boolean(
        string='Crear traslado de retorno automático',
        default=True,
        config_parameter='rental_multi_wh.auto_return_transfer',
        help='Al completar la devolución del cliente, crear '
             'automáticamente traslados para devolver el material '
             'a sus almacenes de origen.',
    )
