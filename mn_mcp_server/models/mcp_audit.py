# -*- coding: utf-8 -*-
"""Every MCP call gets logged. The audit log is the single source of truth
for what the AI did — required for compliance + safety review."""
import hashlib, json
from odoo import api, fields, models


class McpAudit(models.Model):
    _name = "mn.mcp.audit"
    _description = "MCP audit log"
    _order = "create_date desc"

    create_date = fields.Datetime(readonly=True, index=True)
    api_key_id = fields.Many2one("mn.mcp.api_key", required=True, ondelete="cascade")
    user_id = fields.Many2one(related="api_key_id.user_id", store=True)
    method = fields.Char(required=True, index=True,
        help="JSON-RPC method that was called.")
    model_target = fields.Char(string="Target model")
    record_ids = fields.Char(string="Target ids")
    args_hash = fields.Char(string="Args hash",
        help="SHA-256 of the request body — for non-repudiation.")
    ip = fields.Char()
    latency_ms = fields.Integer()
    status = fields.Selection([
        ("ok", "OK"),
        ("auth_fail", "Authentication failed"),
        ("forbidden", "Forbidden — out of scope"),
        ("error", "Error"),
        ("over_quota", "Over daily quota"),
    ], required=True, default="ok", index=True)
    error_msg = fields.Char()

    @api.model
    def _cron_cleanup(self):
        """Delete audit entries older than configured retention."""
        from datetime import timedelta
        days = int(self.env["ir.config_parameter"].sudo().get_param(
            "mn_mcp.audit_retention", "90"))
        cutoff = fields.Datetime.now() - timedelta(days=days)
        old = self.sudo().search([("create_date", "<", cutoff)])
        n = len(old)
        old.unlink()
        return n

    @api.model
    def log(self, **kw):
        """Convenience: log() called from the controller."""
        args = kw.pop("args", None)
        if args is not None:
            try:
                payload = json.dumps(args, default=str, sort_keys=True)
            except Exception:
                payload = str(args)
            kw["args_hash"] = hashlib.sha256(payload.encode()).hexdigest()[:32]
        return self.sudo().create(kw)
