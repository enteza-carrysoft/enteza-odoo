# -*- coding: utf-8 -*-
"""MCP prompts — pre-baked instructions surfaced via prompts/list + prompts/get."""
from odoo import api, fields, models


class McpPrompt(models.Model):
    _name = "mn.mcp.prompt"
    _description = "MCP Prompt template"
    _order = "sequence, name"

    name = fields.Char(required=True, index=True,
        help="Identifier — exposed as prompts/list 'name'.")
    sequence = fields.Integer(default=10)
    title = fields.Char(translate=True,
        help="Human-readable title shown to the AI client.")
    description = fields.Text(translate=True)
    arguments_json = fields.Text(string="Arguments (JSON list)",
        default="[]",
        help='List of {"name": str, "description": str, "required": bool}')
    template = fields.Text(string="Prompt body", translate=True,
        help="Use {placeholders} that match argument names.")
    active = fields.Boolean(default=True)
    category = fields.Char()

    def to_mcp(self):
        """Convert to the MCP prompts/list format."""
        import json
        try:
            args = json.loads(self.arguments_json or "[]")
        except Exception:
            args = []
        return {
            "name": self.name,
            "description": self.title or self.description or self.name,
            "arguments": args,
        }

    def render(self, kwargs):
        body = self.template or ""
        for k, v in (kwargs or {}).items():
            body = body.replace("{" + k + "}", str(v))
        return body
