# -*- coding: utf-8 -*-
"""Custom tools — turn a business question into a first-class MCP tool.

The 24 built-in tools are primitives: search, read, write. They work, but they
make the model guess. Asked for "overdue invoices for Acme", it has to know the
model is ``account.move``, that overdue means ``invoice_date_due < today AND
payment_state != 'paid'``, and that ``move_type`` must be ``out_invoice``. It
usually gets there. Usually is not good enough on a Monday morning.

A custom tool encodes that once, with a name and a description the model reads:

    name:        overdue_invoices
    description: Invoices past their due date and not yet paid.
    model:       account.move
    domain:      [("move_type","=","out_invoice"),
                  ("payment_state","!=","paid"),
                  ("invoice_date_due","<","{as_of}")]
    parameter:   as_of (date, defaults to today)

Now the model calls one tool with one obvious argument, and the *business*
decides what "overdue" means rather than the LLM improvising it.

Deliberately no free-form Python here. A tool that runs arbitrary code is a
remote shell with extra steps; anyone who genuinely needs that can point a tool
at an ``ir.actions.server``, which is Odoo's own reviewed mechanism for it and
carries its own permissions.

Everything still runs as the API key's user, inside the key's model whitelist.
A custom tool can narrow what the AI sees. It can never widen it.
"""
import json
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Claude rejects tool names with dots; this is the pattern the clients accept.
NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

PARAM_TYPES = [
    ("string", "Text"),
    ("integer", "Whole number"),
    ("number", "Decimal"),
    ("boolean", "Yes / No"),
    ("date", "Date"),
]


class McpTool(models.Model):
    _name = "mn.mcp.tool"
    _description = "MCP Custom Tool"
    _order = "sequence, name"

    name = fields.Char(required=True, help="What the AI calls. Letters, digits, _ and - only.")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text(
        required=True,
        help="The AI reads this to decide when to use the tool. Write it for a "
             "new colleague: say what it returns and when to reach for it.")

    kind = fields.Selection([
        ("query", "Find records"),
        ("group", "Aggregate / count by"),
        ("action", "Run a server action"),
    ], default="query", required=True)

    model_id = fields.Many2one("ir.model", string="Model", required=True,
                               ondelete="cascade")
    model_name = fields.Char(related="model_id.model", store=True)

    domain = fields.Text(
        default="[]",
        help="Odoo domain. Use {param} to substitute a parameter, e.g. "
             '[("partner_id","=",{partner_id})]')
    field_names = fields.Char(
        string="Fields returned",
        help="Comma-separated. Empty returns the display name only — which is "
             "usually what you want, since every extra field costs the model tokens.")
    order = fields.Char(help="e.g. invoice_date_due asc")
    limit = fields.Integer(default=50, help="Hard cap on rows returned.")

    groupby = fields.Char(help="Comma-separated fields to group by.")
    aggregates = fields.Char(
        help="Comma-separated, Odoo syntax: amount_total:sum, id:count")

    action_id = fields.Many2one("ir.actions.server", string="Server action",
                                ondelete="cascade")

    param_ids = fields.One2many("mn.mcp.tool.param", "tool_id", string="Parameters")
    call_count = fields.Integer(readonly=True, default=0)

    _sql_constraints = [("name_uniq", "unique(name)", "Tool names must be unique.")]

    # ------------------------------------------------------------------
    @api.constrains("name")
    def _check_name(self):
        for tool in self:
            if not NAME_RE.match(tool.name or ""):
                raise ValidationError(_(
                    "'%s' is not a usable tool name. Use letters, digits, "
                    "underscore or hyphen — no dots, no spaces: clients reject them.",
                    tool.name))
            if (tool.name or "").startswith("odoo_"):
                raise ValidationError(_(
                    "The 'odoo_' prefix belongs to the built-in tools. "
                    "Pick another name so yours cannot be confused with them."))

    @api.constrains("domain")
    def _check_domain(self):
        """Catch a broken domain here, not at 3am inside a model's answer."""
        for tool in self:
            if not tool.domain:
                continue
            probe = re.sub(r"\{[a-zA-Z0-9_]+\}", "0", tool.domain)
            try:
                parsed = eval(probe, {"__builtins__": {}}, {})  # noqa: S307
            except Exception as exc:  # noqa: BLE001
                raise ValidationError(_("That domain does not parse: %s", exc))
            if not isinstance(parsed, list):
                raise ValidationError(_("A domain must be a list."))

    @api.constrains("kind", "action_id", "groupby")
    def _check_kind(self):
        for tool in self:
            if tool.kind == "action" and not tool.action_id:
                raise ValidationError(_("Pick the server action to run."))
            if tool.kind == "group" and not tool.groupby:
                raise ValidationError(_("Say which field(s) to group by."))

    # ------------------------------------------------------------------
    def to_schema(self):
        """The MCP tool definition this record produces."""
        self.ensure_one()
        properties, required = {}, []
        for param in self.param_ids:
            spec = {"type": "string" if param.param_type == "date" else param.param_type,
                    "description": param.description or ""}
            if param.param_type == "date":
                spec["format"] = "date"
            properties[param.name] = spec
            if param.required and not param.default_value:
                required.append(param.name)

        read_only = self.kind in ("query", "group")
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {"type": "object", "properties": properties,
                            "required": required},
            "annotations": {
                "readOnlyHint": read_only,
                "destructiveHint": False,
                "idempotentHint": read_only,
                "openWorldHint": False,
            },
        }

    # ------------------------------------------------------------------
    def _resolve_domain(self, arguments):
        """Substitute parameters into the domain.

        Values are injected as *repr'd Python literals*, never as raw text, so
        a string argument cannot close a bracket and inject its own clause.
        """
        raw = self.domain or "[]"
        values = {}
        for param in self.param_ids:
            given = arguments.get(param.name, None)
            if given in (None, ""):
                given = param.cast_default()
            values[param.name] = param.cast(given)

        def substitute(match):
            key = match.group(1)
            if key not in values:
                raise ValidationError(_("Unknown parameter '%s' in the domain.", key))
            return repr(values[key])

        rendered = re.sub(r"\{([a-zA-Z0-9_]+)\}", substitute, raw)
        try:
            domain = eval(rendered, {"__builtins__": {}}, {})  # noqa: S307
        except Exception as exc:  # noqa: BLE001
            raise ValidationError(_("Could not build the domain: %s", exc))
        if not isinstance(domain, list):
            raise ValidationError(_("A domain must be a list."))
        return domain

    def run(self, env, arguments, max_records):
        """Execute as the API key's user. `env` is already scoped to them."""
        self.ensure_one()
        model = env[self.model_name]
        domain = self._resolve_domain(arguments)
        limit = min(self.limit or max_records, max_records)

        if self.kind == "query":
            fields_list = [f.strip() for f in (self.field_names or "").split(",") if f.strip()]
            if fields_list:
                rows = model.search_read(domain, fields_list, limit=limit,
                                         order=self.order or None)
            else:
                records = model.search(domain, limit=limit, order=self.order or None)
                rows = [{"id": r.id, "name": r.display_name} for r in records]
            result = {"count": len(rows), "records": rows}

        elif self.kind == "group":
            groupby = [g.strip() for g in (self.groupby or "").split(",") if g.strip()]
            aggregates = [a.strip() for a in (self.aggregates or "").split(",") if a.strip()]
            rows = model._read_group(domain, groupby=groupby,
                                     aggregates=aggregates or ["__count"])
            # _read_group hands back recordsets for relational group keys.
            # Serialised naively those become "res.country(233,)", which tells
            # a language model nothing — turn them into id + label.
            result = {
                "groups": [[_readable(cell) for cell in row] for row in rows],
                "groupby": groupby,
                "aggregates": aggregates or ["__count"],
            }

        else:  # action
            records = model.search(domain, limit=limit)
            action = self.action_id.sudo().with_context(
                active_model=self.model_name,
                active_ids=records.ids,
                active_id=records[:1].id or False,
            )
            action.run()
            result = {"ok": True, "ran_on": len(records)}

        self.sudo().call_count += 1
        return result


def _readable(value):
    """Make a _read_group cell safe and meaningful in JSON."""
    if isinstance(value, models.BaseModel):
        if not value:
            return None
        return {"id": value.id, "name": value.display_name}
    return value


class McpToolParam(models.Model):
    _name = "mn.mcp.tool.param"
    _description = "MCP Custom Tool Parameter"
    _order = "sequence, id"

    tool_id = fields.Many2one("mn.mcp.tool", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    param_type = fields.Selection(PARAM_TYPES, default="string", required=True)
    description = fields.Char(
        help="Shown to the AI. Say what a good value looks like.")
    required = fields.Boolean(default=False)
    default_value = fields.Char(
        help="Used when the AI omits it. 'today' works for a date.")

    @api.constrains("name")
    def _check_name(self):
        for param in self:
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", param.name or ""):
                raise ValidationError(_(
                    "'%s' is not a usable parameter name.", param.name))

    # ------------------------------------------------------------------
    def cast_default(self):
        self.ensure_one()
        if self.param_type == "date" and (self.default_value or "").strip() == "today":
            return fields.Date.to_string(fields.Date.context_today(self))
        return self.default_value

    def cast(self, value):
        """Coerce to the declared type.

        Models send numbers as strings often enough that being strict here just
        produces confusing failures; being lenient about the representation and
        strict about the *type* is the useful combination.
        """
        self.ensure_one()
        if value is None:
            return False
        try:
            if self.param_type == "integer":
                return int(value)
            if self.param_type == "number":
                return float(value)
            if self.param_type == "boolean":
                if isinstance(value, str):
                    return value.strip().lower() in ("1", "true", "yes", "y")
                return bool(value)
        except (TypeError, ValueError):
            raise ValidationError(_(
                "'%(value)s' is not a valid %(type)s for '%(name)s'.",
                value=value, type=self.param_type, name=self.name))
        return value
