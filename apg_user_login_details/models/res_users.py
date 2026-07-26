# -*- coding: utf-8 -*-

from odoo.http import request
from odoo import api, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def _check_credentials(self, password, user_agent_env):
        """ Check user credentials during login and log the login details."""
        result = super(ResUsers, self)._check_credentials(
            password, user_agent_env)
        ip_address = request.httprequest.remote_addr
        vals = {
            'name': self.name,
            'ip_address': ip_address
        }
        self.env['login.detail'].sudo().create(vals)
        return result
