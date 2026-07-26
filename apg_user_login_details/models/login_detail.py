# -*- coding: utf-8 -*-

from odoo import fields, models


class LoginDetail(models.Model):
    _name = 'login.detail'
    _description = 'Login Detail'

    name = fields.Char(string="User Name", help="Name of logged in user")
    date_time = fields.Datetime(
        string="Login Date And Time",
        default=lambda self: fields.Datetime.now(),
        help="Date and time of log in")
    ip_address = fields.Char(string="IP Address", help="IP address of login")
