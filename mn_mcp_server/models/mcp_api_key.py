# -*- coding: utf-8 -*-
"""Scoped API token used by MCP clients.

Each token belongs to a specific Odoo user — every MCP call from this
token runs under that user, so Odoo's standard ACL + record rules apply.
The token additionally narrows access to a chosen list of models and a
permission matrix (read / write / create / unlink)."""
import hashlib, secrets
from datetime import date
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class McpApiKey(models.Model):
    _name = "mn.mcp.api_key"
    _description = "MCP API key"
    _inherit = ["mail.thread"]
    _order = "create_date desc"

    name = fields.Char(required=True, tracking=True,
        help="Human-readable label — e.g. 'Claude desktop · Moaz'.")
    user_id = fields.Many2one("res.users", required=True, tracking=True,
        default=lambda s: s.env.user,
        help="The Odoo user this key impersonates. ACL + record rules apply.")
    token = fields.Char(string="Token", readonly=True, copy=False, index=True,
        help="The secret Bearer token. Shown ONCE on creation.")
    token_hash = fields.Char(readonly=True, copy=False, index=True,
        help="SHA-256 of the token — what we actually store.")

    # Scope
    def _default_allowed_models(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "mn_mcp.default_models",
            "res.partner,product.template,sale.order,crm.lead,account.move")

    allowed_models = fields.Char(string="Allowed models",
        default=_default_allowed_models,
        help="Comma-separated list of models this key can touch. * = all.")
    perm_read = fields.Boolean(default=True, tracking=True)
    perm_write = fields.Boolean(default=False, tracking=True)
    perm_create = fields.Boolean(default=False, tracking=True)
    perm_unlink = fields.Boolean(default=False, tracking=True)
    allowed_methods = fields.Char(
        string="Allowed exec methods",
        default="",
        help="Comma-separated method names callable via odoo.execute. "
             "Leave empty to forbid execute entirely.")

    # Limits
    daily_quota = fields.Integer(default=1000, tracking=True,
        help="Max requests per day. 0 = unlimited.")
    rate_per_minute = fields.Integer(default=60, tracking=True,
        help="Max requests per minute. 0 = unlimited.")
    usage_today = fields.Integer(compute="_compute_usage_today")
    expiry_date = fields.Date(tracking=True,
        help="Optional. After this date the key stops working.")
    ip_allowlist = fields.Char(string="IP allowlist",
        help="Comma-separated CIDR/IPs. Empty = any. e.g. '10.0.0.0/24, 1.2.3.4'.")

    state = fields.Selection([
        ("active", "Active"), ("revoked", "Revoked"),
    ], default="active", tracking=True, index=True)

    last_used = fields.Datetime(readonly=True)
    last_ip = fields.Char(readonly=True)
    total_calls = fields.Integer(readonly=True)

    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)

    # --- model selector: friendly UI over the allowed_models CSV -----------
    allow_all_models = fields.Boolean(
        string="Allow all models", compute="_compute_model_helpers",
        inverse="_inverse_model_helpers",
        help="Let this key reach every model the user can (Odoo ACLs still apply).")
    allowed_model_ids = fields.Many2many(
        "ir.model", string="Models", compute="_compute_model_helpers",
        inverse="_inverse_model_helpers",
        help="Pick exactly which models this key may access.")

    # --- one-click connection helper (link to Claude) ----------------------
    connect_url = fields.Char(string="MCP URL", compute="_compute_connect")
    connect_url_key = fields.Char(string="Connector URL", compute="_compute_connect",
        help="MCP URL with the key embedded — paste into Claude's custom connector.")
    claude_config = fields.Text(string="Client config", compute="_compute_connect")
    mcp_remote_cmd = fields.Char(string="mcp-remote command", compute="_compute_connect")

    @api.depends("allowed_models")
    def _compute_model_helpers(self):
        Model = self.env["ir.model"]
        for r in self:
            csv = (r.allowed_models or "").strip()
            r.allow_all_models = csv == "*"
            if csv and csv != "*":
                names = [m.strip() for m in csv.split(",") if m.strip()]
                r.allowed_model_ids = Model.search([("model", "in", names)])
            else:
                r.allowed_model_ids = Model.browse()

    def _inverse_model_helpers(self):
        for r in self:
            if r.allow_all_models:
                r.allowed_models = "*"
            else:
                r.allowed_models = ",".join(sorted(r.allowed_model_ids.mapped("model")))

    @api.depends("token")
    def _compute_connect(self):
        from odoo.http import request
        ICP = self.env["ir.config_parameter"].sudo()
        # 1) explicit override (only needed when the public domain differs from
        #    what Odoo sees, e.g. behind certain proxies);
        # 2) otherwise auto-detect: the exact host the admin is browsing right
        #    now (so the link always matches THIS database/instance);
        # 3) fall back to the configured base URL.
        public = (ICP.get_param("mn_mcp.public_url") or "").strip().rstrip("/")
        if public:
            url = public
        else:
            base = ""
            try:
                if request and request.httprequest:
                    base = (request.httprequest.host_url or "").rstrip("/")
            except Exception:
                base = ""
            if not base:
                base = (ICP.get_param("web.base.url") or "").rstrip("/")
            url = (base + "/mcp") if base else "/mcp"
        for r in self:
            tok = r.token or "PASTE-YOUR-TOKEN-HERE"
            r.connect_url = url
            r.connect_url_key = "%s?key=%s" % (url, tok)
            r.mcp_remote_cmd = 'npx -y mcp-remote %s --header "Authorization: Bearer %s"' % (url, tok)
            r.claude_config = (
                '{\n'
                '  "mcpServers": {\n'
                '    "odoo": {\n'
                '      "command": "npx",\n'
                '      "args": ["-y", "mcp-remote", "%s",\n'
                '               "--header", "Authorization: Bearer %s"]\n'
                '    }\n'
                '  }\n'
                '}'
            ) % (url, tok)

    @api.model_create_multi
    def create(self, vals_list):
        records = []
        for vals in vals_list:
            raw = secrets.token_urlsafe(40)
            vals["token"] = raw
            vals["token_hash"] = hashlib.sha256(raw.encode()).hexdigest()
            records.append(super().create([vals]))
        return self.browse([r.id for r in records])

    def action_reveal_token(self):
        """Show the raw token via a wizard-style notification. ONCE."""
        self.ensure_one()
        if not self.token:
            raise UserError(_("Token has already been shown and cleared. Issue a new key."))
        token = self.token
        # Clear after reveal so it's never stored in clear-text long-term
        self.sudo().write({"token": False})
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("MCP API key — copy now"),
                "message": token,
                "type": "warning",
                "sticky": True,
            },
        }

    def action_revoke(self):
        self.write({"state": "revoked"})

    @api.depends("name")
    def _compute_usage_today(self):
        Audit = self.env["mn.mcp.audit"].sudo()
        today = fields.Date.today()
        for r in self:
            r.usage_today = Audit.search_count([
                ("api_key_id", "=", r.id),
                ("create_date", ">=", f"{today} 00:00:00"),
                ("create_date", "<=", f"{today} 23:59:59"),
            ])

    def is_model_allowed(self, model):
        allowed = (self.allowed_models or "").strip()
        if allowed == "*":
            return True
        return model in [m.strip() for m in allowed.split(",") if m.strip()]

    def is_method_allowed(self, method):
        allowed = (self.allowed_methods or "").strip()
        return method in [m.strip() for m in allowed.split(",") if m.strip()]

    def is_ip_allowed(self, ip):
        spec = (self.ip_allowlist or "").strip()
        if not spec or not ip:
            return True
        import ipaddress
        try:
            ip_obj = ipaddress.ip_address(ip)
        except ValueError:
            return False
        for chunk in spec.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                if "/" in chunk:
                    if ip_obj in ipaddress.ip_network(chunk, strict=False):
                        return True
                else:
                    if ip_obj == ipaddress.ip_address(chunk):
                        return True
            except ValueError:
                continue
        return False

    def check_rate_limit(self):
        """Per-minute rate limit. Returns True if OK, False if over."""
        if not self.rate_per_minute:
            return True
        from datetime import timedelta
        Audit = self.env["mn.mcp.audit"].sudo()
        one_min_ago = fields.Datetime.now() - timedelta(minutes=1)
        recent = Audit.search_count([
            ("api_key_id", "=", self.id),
            ("create_date", ">=", one_min_ago),
        ])
        return recent < self.rate_per_minute

    @api.model
    def authenticate(self, raw_token):
        """Look up the API key by hash, return the record or False."""
        if not raw_token:
            return False
        h = hashlib.sha256(raw_token.encode()).hexdigest()
        key = self.sudo().search([
            ("token_hash", "=", h),
            ("state", "=", "active"),
        ], limit=1)
        if not key:
            return False
        if key.expiry_date and key.expiry_date < date.today():
            return False
        if key.daily_quota and key.usage_today >= key.daily_quota:
            return False
        return key
