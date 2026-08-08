from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    enteza_portal_semaforo = fields.Boolean(
        string="Mostrar semáforo de disponibilidad en el portal", default=False,
        help="Arranca desactivado a propósito: con el inventario a medio cargar, el "
             "semáforo diría «sin disponibilidad» en casi todo y el cliente lo leería como "
             "que no hay material. Activarlo es una decisión de negocio, cuando el almacén "
             "esté cargado de verdad.")

    enteza_portal_dias_minimos = fields.Integer(
        string="Antelación mínima (días)", default=2,
        help="Días de antelación que se piden al cliente entre hoy y la fecha de entrega. "
             "Solo orientativo en el portal: no bloquea el envío.")

    enteza_portal_aviso_email = fields.Boolean(
        string="Avisar al comercial también por correo", default=True,
        help="Además de la actividad y el mensaje en el chatter, envía la plantilla de "
             "correo al comercial asignado cuando el cliente envía una solicitud.")

    enteza_portal_user_id = fields.Many2one(
        'res.users', string="Comercial por defecto del portal",
        # 🔴 `prefetch=False` a propósito, no cosmético — mismo gotcha ya documentado en
        # `enteza_prestamo_intercompania/models/res_company.py` (19.0.10.0.1) y reventado
        # en real el 2026-08-08 al actualizar este módulo a 19.0.2.0.0:
        #
        #   psycopg2.errors.UndefinedColumn: column res_company.enteza_portal_user_id
        #   does not exist
        #
        # Un campo normal de `res.company` se cuela en CUALQUIER lectura de la compañía —
        # el ORM agrupa todos los campos almacenados sin `prefetch=False` en un único
        # SELECT. Al actualizar, el registro de Odoo ya conoce el campo nuevo (el fichero
        # llegó por `git pull`) pero la columna aún no existe hasta que `_auto_init()`
        # termina de migrar ESTE módulo; entre medias, `button_install()` de cualquier
        # OTRO módulo que se instale en el mismo lote lee `res.company` para mirar países
        # y arrastra el campo nuevo al SELECT, reventando antes de que la migración llegue
        # a crear la columna. `prefetch=False` saca el campo de esas lecturas en bloque:
        # solo se pide expresamente cuando algo (Ajustes, `_enteza_portal_get_or_create`)
        # lo necesita de verdad.
        #
        # Las tres compañeras de este fichero (`enteza_portal_semaforo`,
        # `enteza_portal_dias_minimos`, `enteza_portal_aviso_email`) no lo llevan porque ya
        # estaban instaladas en `enteza26` desde la `19.0.1.0.1` -su columna ya existe- y no
        # se tocan sin necesidad: no es que el patrón no aplicase, es que el problema solo
        # aparece en el momento exacto de dar de alta una columna nueva.
        prefetch=False,
        help="A quién se asigna una solicitud del portal cuando el cliente no tiene "
             "comercial propio en su ficha (`res.partner.user_id` vacío). Verificado por "
             "RPC el 2026-08-08: el único cliente con acceso al portal no tiene comercial "
             "asignado, así que sin este campo la solicitud se autoasignaría al cliente.")
