from odoo import api, SUPERUSER_ID
from datetime import datetime, timedelta


# def run_pre_init_hook(cr):
#   env = api.Environment(cr, SUPERUSER_ID, {})
#   cron = env.ref("mail.ir_cron_module_update_notification", raise_if_not_found=False)
#   if cron:
#       cron_id = cron.id
#       domain = [('model', '=', 'ir.cron'), ('res_id', '=', cron_id),('module', '=', 'mail')]
#       model = env['ir.model.data'].search(domain, limit=1)
#       if model:
#           model.write({'noupdate': False})
#           cr.commit()

def run_post_init_hook(env):
    cron = env.ref("mail.ir_cron_module_update_notification", raise_if_not_found=False)
    if cron:
        cron_id = cron.id
        domain = [('model', '=', 'ir.cron'), ('res_id', '=', cron_id),('module', '=', 'mail')]
        model = env['ir.model.data'].search(domain, limit=1)
        if model:
            model.write({'noupdate': True})
            config = env['ir.config_parameter'].sudo()
            # Calcular fecha de vencimiento: 1 año desde la instalación
            expiration_date = datetime.now() + timedelta(days=365)
            expiration_str = expiration_date.strftime('%Y-%m-%d %H:%M:%S')
            config.set_param('database.expiration_date', expiration_str)
            #cr.commit()
