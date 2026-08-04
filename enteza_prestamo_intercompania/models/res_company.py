from odoo import fields, models

# Mismo convenio que `resource.calendar.attendance.dayofweek`: la CLAVE es el número que
# devuelve `date.weekday()` (lunes = 0 ... domingo = 6), como texto porque así lo pide
# `fields.Selection`. Evita tener que traducir de un lado a otro en `_fecha_traslado_de`.
DIAS_SEMANA = [
    ('0', 'Lunes'),
    ('1', 'Martes'),
    ('2', 'Miércoles'),
    ('3', 'Jueves'),
    ('4', 'Viernes'),
    ('5', 'Sábado'),
    ('6', 'Domingo'),
]


class ResCompany(models.Model):
    _inherit = 'res.company'

    enteza_dia_traslado_semana = fields.Selection(
        DIAS_SEMANA, string='Día de traslado entre compañías', default='2',
        help='Día de la semana en el que esta compañía, cuando presta material a otra, '
             'traslada el material: siempre el más cercano ANTERIOR al día del evento, '
             'nunca el mismo día. Sustituye a los días de antelación fijos de antes de la '
             '19.0.10.0.0 (`[PENDIENTE-3]` del PRP): con eventos concentrados en fin de '
             'semana, un día fijo de reparto encaja mejor con la logística real que contar '
             'días desde el evento.',
    )
