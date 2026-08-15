# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    mcp_enabled = fields.Boolean(string="Enable MCP endpoint",
        config_parameter="mn_mcp.enabled", default=True,
        help="Master switch. When OFF, /mcp returns 503.")
    mcp_public_url = fields.Char(
        string="Public MCP URL",
        config_parameter="mn_mcp.public_url",
        help="Full public HTTPS URL of the /mcp endpoint, e.g. "
             "https://erp.mycompany.com/mcp . Set this if Odoo is behind a "
             "reverse proxy / different public domain — the 'Connect to Claude' "
             "instructions use it. Leave empty to use this server's base URL.")
    mcp_default_model_ids = fields.Many2many(
        "ir.model", string="Default allowed models",
        help="Models pre-selected when you create a new API key. "
             "Leave empty to start new keys with no models.")
    mcp_max_records = fields.Integer(
        string="Max records per call",
        config_parameter="mn_mcp.max_records",
        default=100,
        help="Hard cap on records returned by search / read.")
    mcp_audit_retention_days = fields.Integer(
        string="Audit retention (days)",
        config_parameter="mn_mcp.audit_retention",
        default=90)

    # --- Confirm before write -----------------------------------------
    mcp_confirm_enabled = fields.Boolean(
        string="Ask before destructive actions",
        config_parameter="mn_mcp.confirm_enabled", default=True,
        help="The AI must get a human's confirmation before deleting records, "
             "editing in bulk, or calling a model method. Odoo's access rules "
             "stop it doing what the user may not do; this stops it doing "
             "something the user could do but did not mean to.")
    mcp_confirm_write_over = fields.Integer(
        string="Confirm updates over N records",
        config_parameter="mn_mcp.confirm_write_over", default=10,
        help="Updating more than this many records at once needs confirmation. "
             "0 means confirm every update.")
    mcp_confirm_create_over = fields.Integer(
        string="Confirm bulk create over N records",
        config_parameter="mn_mcp.confirm_create_over", default=20)
    mcp_confirm_execute = fields.Boolean(
        string="Confirm arbitrary method calls",
        config_parameter="mn_mcp.confirm_execute", default=True,
        help="odoo_execute and odoo_run_server_action can do anything the "
             "model allows, so they are confirmed by default.")

    # The default-models list is stored as a CSV config parameter; load/save it
    # through a friendly model picker.
    def get_values(self):
        res = super().get_values()
        csv = self.env["ir.config_parameter"].sudo().get_param("mn_mcp.default_models", "")
        names = [m.strip() for m in csv.split(",") if m.strip()]
        models = self.env["ir.model"].search([("model", "in", names)]) if names else self.env["ir.model"]
        res["mcp_default_model_ids"] = [(6, 0, models.ids)]
        return res

    def set_values(self):
        super().set_values()
        csv = ",".join(sorted(self.mcp_default_model_ids.mapped("model")))
        self.env["ir.config_parameter"].sudo().set_param("mn_mcp.default_models", csv)
