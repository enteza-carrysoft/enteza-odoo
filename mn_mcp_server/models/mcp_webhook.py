# -*- coding: utf-8 -*-
"""Security webhooks — POST to an external URL on auth_fail / over_quota / forbidden."""
import json, logging, urllib.request, urllib.error
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class McpWebhook(models.Model):
    _name = "mn.mcp.webhook"
    _description = "MCP security webhook"
    _order = "active desc, name"

    name = fields.Char(required=True)
    url = fields.Char(required=True,
        help="POST target. e.g. Slack incoming-webhook URL.")
    event_types = fields.Char(
        default="auth_fail,forbidden,over_quota,error",
        help="Comma-separated audit statuses to fire on.")
    active = fields.Boolean(default=True)
    secret = fields.Char(help="If set, sent as X-MCP-Signature header.")
    last_fired = fields.Datetime(readonly=True)
    fire_count = fields.Integer(readonly=True)
    last_error = fields.Char(readonly=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)

    def fire(self, payload):
        for w in self.search([("active", "=", True)]):
            evt = payload.get("status")
            allowed = [e.strip() for e in (w.event_types or "").split(",") if e.strip()]
            if allowed and evt not in allowed:
                continue
            try:
                data = json.dumps(payload, default=str).encode()
                req = urllib.request.Request(w.url, data=data, method="POST",
                    headers={"Content-Type": "application/json",
                             **({"X-MCP-Signature": w.secret} if w.secret else {})})
                urllib.request.urlopen(req, timeout=4).read()
                w.sudo().write({
                    "last_fired": fields.Datetime.now(),
                    "fire_count": w.fire_count + 1,
                    "last_error": False,
                })
            except Exception as e:
                _logger.warning(f"MCP webhook {w.name} failed: {e}")
                w.sudo().write({"last_error": str(e)[:255]})
