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
        # 🔴 `prefetch=False` a propósito, y no cosmético (19.0.10.0.1).
        #
        # Un campo normal de `res.company` se cuela en CUALQUIER lectura de la compañía: el
        # ORM agrupa todos los campos almacenados sin `prefetch=False` en un único SELECT,
        # aunque solo se haya pedido uno. Eso incluye comprobaciones genéricas de Odoo que no
        # tienen nada que ver con este módulo — la que reventó en `enteza26` el 2026-08-04 fue
        # `ir_module.py:button_install`, que lee `res.company` para mirar países al instalar
        # CUALQUIER módulo.
        #
        # El problema de fondo es de arranque: el registro de Odoo carga la definición de este
        # campo en cuanto el fichero llega por `git pull` y el proceso se reinicia, pero la
        # columna en la base de datos no existe hasta que `_auto_init()` termina de
        # actualizar ESTE módulo. Entre medias, cualquier lectura de `res.company` — de
        # cualquier módulo, para cualquier cosa — revienta con
        # `UndefinedColumn: res_company.enteza_dia_traslado_semana does not exist`, y eso
        # incluye el propio botón «Actualizar», que no llega a ejecutar el `_auto_init` que
        # crearía la columna. `prefetch=False` saca el campo de esas lecturas en bloque: solo
        # se pide expresamente cuando algo (la vista de Ajustes, `_fecha_traslado_de`) lo
        # necesita de verdad, así que deja de arrastrar a comprobaciones que no tienen nada
        # que ver con él.
        prefetch=False,
        help='Día de la semana en el que esta compañía, cuando presta material a otra, '
             'traslada el material: siempre el más cercano ANTERIOR al día del evento, '
             'nunca el mismo día. Sustituye a los días de antelación fijos de antes de la '
             '19.0.10.0.0 (`[PENDIENTE-3]` del PRP): con eventos concentrados en fin de '
             'semana, un día fijo de reparto encaja mejor con la logística real que contar '
             'días desde el evento.',
    )
