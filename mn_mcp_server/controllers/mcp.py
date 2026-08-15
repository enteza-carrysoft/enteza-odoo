# -*- coding: utf-8 -*-
"""MCP server controller — v2 with 24 tools, prompts, rate limiting,
IP allowlist, webhooks."""
import base64, json, time, logging
from odoo import http, fields
from odoo.http import request

from . import confirm as C
from . import protocol as P

_logger = logging.getLogger(__name__)

JSONRPC = "2.0"
# Kept for the module version string reported to clients.
SERVER_VERSION = "19.0.3.0.0"


def _err(code, message, rpc_id=None, data=None):
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": JSONRPC, "id": rpc_id, "error": error}


def _ok(result, rpc_id=None):
    return {"jsonrpc": JSONRPC, "id": rpc_id, "result": result}


class _Forbidden(Exception):
    pass


class McpController(http.Controller):

    @http.route("/mcp", type="http", auth="public", methods=["POST", "OPTIONS"],
                csrf=False, cors="*", save_session=False)
    def mcp(self, **kw):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=[
                ("Access-Control-Allow-Origin", "*"),
                ("Access-Control-Allow-Methods", "POST, OPTIONS"),
                ("Access-Control-Allow-Headers", "Authorization, Content-Type"),
            ])

        env = request.env(su=True)
        enabled = env["ir.config_parameter"].get_param("mn_mcp.enabled", "True") in ("True", "true", "1", True)
        if not enabled:
            return self._respond(_err(P.ERR_DISABLED, "MCP endpoint disabled"), status=503)

        # Read the raw JSON body. Some clients POST JSON without the
        # 'application/json' content-type; Werkzeug then parses the body into
        # form keys and request.httprequest.data is empty — recover it from kw
        # (ignoring the optional ?key= auth param).
        raw = request.httprequest.data
        if not raw and kw:
            raw = (next((k for k in kw if k != "key"), "") or "").encode()
        try:
            body = json.loads(raw or b"{}")
        except Exception:
            return self._respond(_err(P.ERR_PARSE, "Parse error"))

        rpc_id = body.get("id")
        method = body.get("method")
        params = body.get("params") or {}
        ip = request.httprequest.remote_addr

        # The revision is settled per request: from 2026-07-28 there is no
        # handshake to settle it once, so it travels in _meta or the header.
        revision, unsupported = P.negotiate(body, request.httprequest.headers)
        if unsupported:
            return self._respond(_err(
                P.err_code(P.ERR_UNSUPPORTED_VERSION, P.LATEST_REVISION),
                "Unsupported protocol version",
                rpc_id, data={"supported": list(P.SUPPORTED_REVISIONS)}), status=400)

        # 2026-07-28 requires Mcp-Method / Mcp-Name on every POST so proxies
        # can route without parsing the body. We validate rather than demand:
        # rejecting a request whose headers are merely absent would break
        # clients that are otherwise compliant, but a header that CONTRADICTS
        # the body is a routing bug worth surfacing.
        header_method = request.httprequest.headers.get("Mcp-Method")
        if header_method and method and header_method != method:
            return self._respond(_err(
                P.err_code(P.ERR_HEADER_MISMATCH, revision),
                "Mcp-Method header '%s' does not match body method '%s'" % (header_method, method),
                rpc_id), status=400)

        # JSON-RPC notifications carry no "id" and MUST NOT receive a response.
        # MCP clients send 'notifications/initialized' right after initialize and
        # before tools/list; replying with an error aborts the handshake.
        if "id" not in body or (method or "").startswith("notifications/"):
            return request.make_response("", status=202, headers=[
                ("Access-Control-Allow-Origin", "*"),
            ])

        # Auth token: prefer the Authorization header (mcp-remote, SDK clients),
        # but also accept it in the URL (?key=…) so MCP clients that only take a
        # URL — like Claude's native "custom connector" — can authenticate too.
        token = (request.httprequest.headers.get("Authorization") or "").replace("Bearer ", "").strip()
        from_url = False
        if not token:
            # Only a *static API key* may travel in the URL, and only because
            # Claude's custom-connector dialog has no header field. OAuth
            # access tokens must never be accepted here — the spec forbids
            # tokens in the query string, and a URL leaks into history, proxy
            # logs and screenshots.
            token = (request.httprequest.args.get("key") or "").strip()
            from_url = bool(token)

        api_key = env["mn.mcp.api_key"].authenticate(token)
        if not api_key and token and not from_url:
            # Not a static key — try it as an OAuth access token, bound to
            # this server as its audience (RFC 8707).
            api_key = env["mn.mcp.oauth.token"].authenticate(
                token, audience=self._canonical_resource())

        # server/discover is unauthenticated: a client must be able to learn
        # which revisions we speak before it has credentials, and the answer
        # leaks nothing about the database.
        if method == "server/discover":
            return self._respond(_ok(P.discover(SERVER_VERSION), rpc_id))

        # initialize is open. Removed in 2026-07-28, kept here because the
        # installed base of older clients still opens with it.
        if method == "initialize":
            # echo the client's requested protocol version when supplied, so
            # newer clients (2025-xx-xx) negotiate cleanly; fall back otherwise.
            return self._respond(_ok({
                "protocolVersion": revision,
                "serverInfo": P.server_info(SERVER_VERSION),
                "capabilities": P.capabilities(revision),
            }, rpc_id))

        if not api_key:
            env["mn.mcp.webhook"].fire({"event": "auth_fail", "status": "auth_fail",
                                         "ip": ip, "method": method})
            return self._respond(
                _err(P.ERR_AUTH, "Authentication failed", rpc_id),
                status=401, extra_headers=[("WWW-Authenticate", self._challenge())])

        # IP allowlist
        if not api_key.is_ip_allowed(ip):
            env["mn.mcp.audit"].log(
                api_key_id=api_key.id, method=method, status="forbidden",
                error_msg=f"IP {ip} not in allowlist", ip=ip, args=params,
            )
            return self._respond(_err(P.ERR_IP, f"IP {ip} not allowed", rpc_id), status=403)

        # Rate limit
        if not api_key.check_rate_limit():
            env["mn.mcp.audit"].log(
                api_key_id=api_key.id, method=method, status="over_quota",
                error_msg=f"Rate limit ({api_key.rate_per_minute}/min) exceeded",
                ip=ip, args=params,
            )
            env["mn.mcp.webhook"].fire({"event": "rate_limit", "status": "over_quota",
                                          "key": api_key.name, "ip": ip})
            return self._respond(_err(P.ERR_RATE_LIMIT, "Rate limit exceeded — try again in 60s", rpc_id),
                                 status=429, extra_headers=[("Retry-After", "60")])

        start = time.time()
        try:
            user_env = request.env(user=api_key.user_id.id, su=False)

            if method == "tools/list":
                result = self._tools_list()
            elif method == "tools/call":
                result = self._tools_call(api_key, user_env, params)
            elif method == "resources/list":
                result = self._resources_list(api_key)
            elif method == "resources/read":
                result = self._resources_read(api_key, user_env, params)
            elif method == "prompts/list":
                result = self._prompts_list(env)
            elif method == "prompts/get":
                result = self._prompts_get(env, params)
            elif method == "ping" and not P.is_at_least(revision, P.STATELESS_FROM):
                # Removed in 2026-07-28; still answered for older clients.
                result = {}
            elif method == "logging/setLevel" and not P.is_at_least(revision, P.STATELESS_FROM):
                result = {}
            else:
                return self._respond(_err(P.ERR_METHOD_NOT_FOUND, f"Method '{method}' not found", rpc_id))

            latency = int((time.time() - start) * 1000)
            api_key.sudo().write({
                "last_used": fields.Datetime.now(),
                "last_ip": ip,
                "total_calls": api_key.total_calls + 1,
            })
            env["mn.mcp.audit"].log(
                api_key_id=api_key.id, method=method,
                status="ok", latency_ms=latency,
                args=params, ip=ip,
                model_target=(params.get("arguments") or {}).get("model"),
            )
            result = P.decorate_result(result, revision, method, SERVER_VERSION)
            return self._respond(_ok(result, rpc_id))
        except _Forbidden as e:
            env["mn.mcp.audit"].log(
                api_key_id=api_key.id, method=method, status="forbidden",
                error_msg=str(e), ip=ip, args=params,
                model_target=(params.get("arguments") or {}).get("model"),
            )
            env["mn.mcp.webhook"].fire({"event": "forbidden", "status": "forbidden",
                                          "key": api_key.name, "ip": ip, "msg": str(e)})
            return self._respond(_err(P.ERR_FORBIDDEN, str(e), rpc_id))
        except Exception as e:
            _logger.exception("MCP error")
            env["mn.mcp.audit"].log(
                api_key_id=api_key.id, method=method, status="error",
                error_msg=str(e)[:255], ip=ip, args=params,
            )
            return self._respond(_err(P.ERR_INTERNAL, f"Internal error: {e}", rpc_id))

    # ───────────── helpers ───────────────────────────────────────────
    def _canonical_resource(self):
        """The RFC 8707 identifier a token must be bound to: our /mcp URL."""
        from .oauth import base_url, MCP_PATH
        return f"{base_url()}{MCP_PATH}"

    def _challenge(self):
        """RFC 6750 challenge naming our metadata document.

        This is the whole point of the discovery chain: a client that gets a
        401 learns from this header where to find the authorization server,
        with no configuration from the user.
        """
        from .oauth import base_url
        from ..models.mcp_oauth import SCOPES_SUPPORTED
        meta = f"{base_url()}/.well-known/oauth-protected-resource"
        return ('Bearer resource_metadata="%s", scope="%s"'
                % (meta, " ".join(SCOPES_SUPPORTED[:1])))

    def _respond(self, body, status=200, extra_headers=None):
        headers = [("Content-Type", "application/json"),
                   ("Access-Control-Allow-Origin", "*")]
        if extra_headers:
            headers.extend(extra_headers)
        return request.make_response(json.dumps(body), status=status, headers=headers)

    # ───────────── tools/list ────────────────────────────────────────
    # Tools that never change data, and tools that destroy it. Clients use
    # these hints to decide what may run unattended and what needs a human —
    # Claude will happily call a readOnlyHint tool but prompts before a
    # destructive one.
    _READ_ONLY_TOOLS = {
        "odoo_search", "odoo_search_count", "odoo_read", "odoo_search_read",
        "odoo_read_group", "odoo_name_search", "odoo_fields_get",
        "odoo_list_models", "odoo_get_view", "odoo_menu_tree",
        "odoo_user_context", "odoo_print_report",
    }
    _DESTRUCTIVE_TOOLS = {"odoo_unlink"}

    def _tools_list(self):
        def s(t, p):
            return {"type": "object", "required": list(t),
                    "properties": p}
        tools = [
            # — Core CRUD —
            {"name": "odoo_search",
             "description": "Search records. Returns ids.",
             "inputSchema": s(("model",), {
                 "model": {"type": "string"},
                 "domain": {"type": "array"},
                 "limit": {"type": "integer"},
                 "order": {"type": "string"}})},
            {"name": "odoo_search_count",
             "description": "Count records matching a domain.",
             "inputSchema": s(("model",), {
                 "model": {"type": "string"}, "domain": {"type": "array"}})},
            {"name": "odoo_read",
             "description": "Read fields for given ids.",
             "inputSchema": s(("model", "ids"), {
                 "model": {"type": "string"},
                 "ids": {"type": "array"}, "fields": {"type": "array"}})},
            {"name": "odoo_search_read",
             "description": "Search + read in one call.",
             "inputSchema": s(("model",), {
                 "model": {"type": "string"}, "domain": {"type": "array"},
                 "fields": {"type": "array"}, "limit": {"type": "integer"},
                 "order": {"type": "string"}})},
            {"name": "odoo_read_group",
             "description": "Group-by aggregation. SQL-style.",
             "inputSchema": s(("model", "groupby"), {
                 "model": {"type": "string"}, "domain": {"type": "array"},
                 "fields": {"type": "array"}, "groupby": {"type": "array"}})},
            {"name": "odoo_name_search",
             "description": "Quick name lookup — Odoo's autocomplete primitive.",
             "inputSchema": s(("model",), {
                 "model": {"type": "string"}, "name": {"type": "string"},
                 "limit": {"type": "integer"}})},
            {"name": "odoo_create",
             "description": "Create a record. Requires perm_create.",
             "inputSchema": s(("model", "values"), {
                 "model": {"type": "string"}, "values": {"type": "object"}})},
            {"name": "odoo_create_many",
             "description": "Bulk create multiple records.",
             "inputSchema": s(("model", "records"), {
                 "model": {"type": "string"}, "records": {"type": "array"}})},
            {"name": "odoo_write",
             "description": "Update records. Requires perm_write.",
             "inputSchema": s(("model", "ids", "values"), {
                 "model": {"type": "string"}, "ids": {"type": "array"},
                 "values": {"type": "object"}})},
            {"name": "odoo_unlink",
             "description": "Delete records. Requires perm_unlink.",
             "inputSchema": s(("model", "ids"), {
                 "model": {"type": "string"}, "ids": {"type": "array"}})},
            {"name": "odoo_copy",
             "description": "Duplicate a record.",
             "inputSchema": s(("model", "id"), {
                 "model": {"type": "string"}, "id": {"type": "integer"},
                 "default": {"type": "object"}})},
            {"name": "odoo_find_or_create",
             "description": "Find record by domain; if not found, create.",
             "inputSchema": s(("model", "domain", "values"), {
                 "model": {"type": "string"}, "domain": {"type": "array"},
                 "values": {"type": "object"}})},
            # — Discovery —
            {"name": "odoo_fields_get",
             "description": "Field schema of a model.",
             "inputSchema": s(("model",), {"model": {"type": "string"}})},
            {"name": "odoo_list_models",
             "description": "Models this key may access.",
             "inputSchema": s((), {})},
            {"name": "odoo_get_view",
             "description": "Get a UI view definition (form/list/kanban).",
             "inputSchema": s(("model",), {
                 "model": {"type": "string"},
                 "view_type": {"type": "string"}})},
            # — Chatter / activities / mail —
            {"name": "odoo_message_post",
             "description": "Post a message on a record's chatter.",
             "inputSchema": s(("model", "id", "body"), {
                 "model": {"type": "string"}, "id": {"type": "integer"},
                 "body": {"type": "string"}, "subject": {"type": "string"}})},
            {"name": "odoo_activity_schedule",
             "description": "Schedule a follow-up activity on a record.",
             "inputSchema": s(("model", "id", "summary"), {
                 "model": {"type": "string"}, "id": {"type": "integer"},
                 "summary": {"type": "string"}, "date_deadline": {"type": "string"},
                 "user_id": {"type": "integer"}})},
            {"name": "odoo_send_email",
             "description": "Send an email via a mail.template id.",
             "inputSchema": s(("template_id", "model", "id"), {
                 "template_id": {"type": "integer"},
                 "model": {"type": "string"},
                 "id": {"type": "integer"},
                 "email_to": {"type": "string"}})},
            # — Reports & attachments —
            {"name": "odoo_print_report",
             "description": "Render a QWeb PDF report. Returns base64.",
             "inputSchema": s(("report_name", "ids"), {
                 "report_name": {"type": "string"},
                 "ids": {"type": "array"}})},
            {"name": "odoo_attach_file",
             "description": "Attach a base64 file to a record.",
             "inputSchema": s(("model", "id", "name", "datas"), {
                 "model": {"type": "string"}, "id": {"type": "integer"},
                 "name": {"type": "string"}, "datas": {"type": "string"},
                 "mimetype": {"type": "string"}})},
            # — Server actions / generic execute —
            {"name": "odoo_run_server_action",
             "description": "Execute an ir.actions.server by id.",
             "inputSchema": s(("action_id",), {
                 "action_id": {"type": "integer"},
                 "model": {"type": "string"},
                 "ids": {"type": "array"}})},
            {"name": "odoo_execute",
             "description": "Call a model method. Whitelist-gated.",
             "inputSchema": s(("model", "method"), {
                 "model": {"type": "string"}, "method": {"type": "string"},
                 "args": {"type": "array"}, "kwargs": {"type": "object"}})},
            # — Discovery / helpers —
            {"name": "odoo_menu_tree",
             "description": "Return the app menu tree for the current user.",
             "inputSchema": s((), {})},
            {"name": "odoo_user_context",
             "description": "Return current user info + company + lang + tz.",
             "inputSchema": s((), {})},
        ]

        # Tools behind the confirmation guard advertise the argument that
        # satisfies it, so a model on a client without elicitation can see how
        # to proceed instead of retrying blindly.
        for tool in tools:
            if tool["name"] in C.ALWAYS_CONFIRM or tool["name"] in C.BULK_TOOLS \
                    or tool["name"] in C.METHOD_TOOLS:
                tool["inputSchema"]["properties"]["confirm"] = {
                    "type": "boolean",
                    "description": ("Set true only after the user has agreed to "
                                    "this exact action. The server refuses "
                                    "without it."),
                }

        for tool in tools:
            read_only = tool["name"] in self._READ_ONLY_TOOLS
            tool["annotations"] = {
                "readOnlyHint": read_only,
                "destructiveHint": tool["name"] in self._DESTRUCTIVE_TOOLS,
                # Re-running a search is free; re-running a create is not.
                "idempotentHint": read_only,
                "openWorldHint": False,
            }

        # Custom tools defined in the database sit alongside the built-ins.
        # They are added here rather than merged later so they get the same
        # sorting and the same cache guarantees.
        custom = request.env["mn.mcp.tool"].sudo().search([])
        tools.extend(tool.to_schema() for tool in custom)

        # Deterministic order: 2026-07-28 asks for it so clients can cache the
        # list, and a stable order also keeps the LLM's prompt cache warm —
        # a reshuffled tool list invalidates it on every conversation.
        tools.sort(key=lambda t: t["name"])
        return {"tools": tools}

    # ───────────── tools/call ────────────────────────────────────────
    def _max_records(self):
        return int(request.env["ir.config_parameter"].sudo().get_param(
            "mn_mcp.max_records", "100"))

    def _tools_call(self, key, env, params):
        name = params.get("name")
        a = params.get("arguments") or {}

        # Guard rail: destructive and bulk operations stop here until a human
        # has seen what is about to happen. `confirm` is stripped either way so
        # it can never reach the ORM as a field value.
        confirmed = C.already_confirmed(params, key, name, a)
        a = {k: v for k, v in a.items() if k != "confirm"}
        if C.needs_confirmation(name, a) and not confirmed:
            request.env["mn.mcp.audit"].sudo().log(
                api_key_id=key.id, method="tools/call", status="ok",
                error_msg=f"confirmation requested for {name}",
                args=params, model_target=a.get("model"),
            )
            return C.input_required(
                name, a, key, env,
                offer_elicitation=C.client_supports_elicitation(params))

        # A custom tool is looked up before the built-ins so an administrator
        # can add one without worrying about colliding with a future built-in
        # (the `odoo_` prefix is reserved for ours, which keeps them apart).
        custom = request.env["mn.mcp.tool"].sudo().search([("name", "=", name)], limit=1)
        if custom:
            if not key.is_model_allowed(custom.model_name):
                raise _Forbidden(f"Model '{custom.model_name}' out of scope")
            if custom.kind in ("query", "group") and not key.perm_read:
                raise _Forbidden("perm_read missing")
            if custom.kind == "action" and not key.perm_write:
                raise _Forbidden("perm_write missing")
            return self._content(custom.run(env, a, self._max_records()))

        model = a.get("model")

        def _check_model():
            if not model:
                raise _Forbidden("Missing 'model'")
            if not key.is_model_allowed(model):
                raise _Forbidden(f"Model '{model}' out of scope")
            if model not in env:
                raise _Forbidden(f"Model '{model}' does not exist")

        # CRUD
        if name == "odoo_search":
            _check_model()
            if not key.perm_read: raise _Forbidden("perm_read missing")
            ids = env[model].search(a.get("domain") or [],
                limit=min(a.get("limit") or self._max_records(), self._max_records()),
                order=a.get("order")).ids
            return self._content({"ids": ids, "count": len(ids)})

        if name == "odoo_search_count":
            _check_model()
            if not key.perm_read: raise _Forbidden("perm_read missing")
            return self._content({"count": env[model].search_count(a.get("domain") or [])})

        if name == "odoo_read":
            _check_model()
            if not key.perm_read: raise _Forbidden("perm_read missing")
            data = env[model].browse(a.get("ids") or []).read(a.get("fields"))
            return self._content(data[: self._max_records()])

        if name == "odoo_search_read":
            _check_model()
            if not key.perm_read: raise _Forbidden("perm_read missing")
            data = env[model].search_read(a.get("domain") or [], a.get("fields"),
                limit=min(a.get("limit") or self._max_records(), self._max_records()),
                order=a.get("order"))
            return self._content(data)

        if name == "odoo_read_group":
            _check_model()
            if not key.perm_read: raise _Forbidden("perm_read missing")
            data = env[model].read_group(a.get("domain") or [],
                a.get("fields") or [], a.get("groupby") or [])
            return self._content(data)

        if name == "odoo_name_search":
            _check_model()
            if not key.perm_read: raise _Forbidden("perm_read missing")
            res = env[model].name_search(a.get("name") or "", limit=a.get("limit") or 8)
            return self._content(res)

        if name == "odoo_create":
            _check_model()
            if not key.perm_create: raise _Forbidden("perm_create missing")
            rec = env[model].create(a.get("values") or {})
            return self._content({"id": rec.id})

        if name == "odoo_create_many":
            _check_model()
            if not key.perm_create: raise _Forbidden("perm_create missing")
            recs = env[model].create(a.get("records") or [])
            return self._content({"ids": recs.ids})

        if name == "odoo_write":
            _check_model()
            if not key.perm_write: raise _Forbidden("perm_write missing")
            ok = env[model].browse(a.get("ids") or []).write(a.get("values") or {})
            return self._content({"ok": bool(ok)})

        if name == "odoo_unlink":
            _check_model()
            if not key.perm_unlink: raise _Forbidden("perm_unlink missing")
            ok = env[model].browse(a.get("ids") or []).unlink()
            return self._content({"ok": bool(ok)})

        if name == "odoo_copy":
            _check_model()
            if not key.perm_create: raise _Forbidden("perm_create missing")
            new = env[model].browse(a.get("id")).copy(default=a.get("default") or {})
            return self._content({"id": new.id})

        if name == "odoo_find_or_create":
            _check_model()
            if not key.perm_read: raise _Forbidden("perm_read missing")
            found = env[model].search(a.get("domain") or [], limit=1)
            if found:
                return self._content({"id": found.id, "created": False})
            if not key.perm_create: raise _Forbidden("perm_create missing")
            new = env[model].create(a.get("values") or {})
            return self._content({"id": new.id, "created": True})

        # Discovery
        if name == "odoo_fields_get":
            _check_model()
            if not key.perm_read: raise _Forbidden("perm_read missing")
            schema = env[model].fields_get(attributes=["string", "type", "required", "help", "relation", "selection"])
            return self._content(schema)

        if name == "odoo_list_models":
            allowed = (key.allowed_models or "").strip()
            return self._content({"allowed": allowed.split(",") if allowed != "*" else ["*"]})

        if name == "odoo_get_view":
            _check_model()
            view_type = a.get("view_type") or "form"
            try:
                arch = env[model].get_view(view_type=view_type)
                return self._content(arch)
            except Exception:
                return self._content({"error": "view not found"})

        # Chatter / activities / mail
        if name == "odoo_message_post":
            _check_model()
            if not key.perm_write: raise _Forbidden("perm_write missing")
            rec = env[model].browse(a.get("id"))
            msg = rec.message_post(body=a.get("body") or "", subject=a.get("subject"))
            return self._content({"message_id": msg.id})

        if name == "odoo_activity_schedule":
            _check_model()
            if not key.perm_write: raise _Forbidden("perm_write missing")
            rec = env[model].browse(a.get("id"))
            vals = {"summary": a.get("summary") or "Follow-up",
                    "activity_type_id": env.ref("mail.mail_activity_data_todo").id}
            if a.get("date_deadline"):
                vals["date_deadline"] = a.get("date_deadline")
            if a.get("user_id"):
                vals["user_id"] = a.get("user_id")
            act = rec.activity_schedule(**vals) if hasattr(rec, "activity_schedule") else env["mail.activity"].create({
                **vals, "res_model": model, "res_id": rec.id,
                "res_model_id": env["ir.model"]._get(model).id,
            })
            aid = act.id if hasattr(act, "id") else (act[0].id if act else 0)
            return self._content({"activity_id": aid})

        if name == "odoo_send_email":
            tid = a.get("template_id")
            tmpl = env["mail.template"].browse(tid)
            if not tmpl.exists():
                raise _Forbidden(f"Template {tid} not found")
            tmpl.send_mail(a.get("id"), force_send=True,
                           email_values={"email_to": a.get("email_to")} if a.get("email_to") else None)
            return self._content({"ok": True})

        # Reports & attachments
        if name == "odoo_print_report":
            report = env["ir.actions.report"]._render_qweb_pdf(
                a.get("report_name"), a.get("ids") or [])
            if isinstance(report, tuple):
                pdf = report[0]
            else:
                pdf = report
            return self._content({
                "filename": f"{a.get('report_name')}.pdf",
                "mimetype": "application/pdf",
                "datas_b64": base64.b64encode(pdf).decode() if pdf else "",
            })

        if name == "odoo_attach_file":
            _check_model()
            if not key.perm_create: raise _Forbidden("perm_create missing")
            att = env["ir.attachment"].create({
                "name": a.get("name") or "file.bin",
                "res_model": model, "res_id": a.get("id"),
                "datas": a.get("datas") or "",
                "mimetype": a.get("mimetype") or "application/octet-stream",
            })
            return self._content({"attachment_id": att.id})

        # Server action / generic execute
        if name == "odoo_run_server_action":
            action = env["ir.actions.server"].browse(a.get("action_id"))
            if not action.exists():
                raise _Forbidden(f"Server action {a.get('action_id')} not found")
            ctx = {"active_model": a.get("model"), "active_ids": a.get("ids") or [],
                   "active_id": (a.get("ids") or [None])[0]}
            res = action.with_context(**ctx).run()
            return self._content({"ok": True, "result": res})

        if name == "odoo_execute":
            _check_model()
            method = a.get("method") or ""
            if not key.is_method_allowed(method):
                raise _Forbidden(f"Method '{method}' not in allowed_methods")
            res = getattr(env[model], method)(*(a.get("args") or []), **(a.get("kwargs") or {}))
            return self._content(res)

        # Discovery / helpers
        if name == "odoo_menu_tree":
            menus = env["ir.ui.menu"].search([("parent_id", "=", False)], limit=50)
            def walk(m, depth=0):
                return {"id": m.id, "name": m.name, "depth": depth,
                        "children": [walk(c, depth + 1) for c in m.child_id[:25]]}
            return self._content([walk(m) for m in menus])

        if name == "odoo_user_context":
            u = env.user
            return self._content({
                "id": u.id, "name": u.name, "login": u.login, "email": u.email,
                "company": u.company_id.name, "lang": u.lang, "tz": u.tz,
                "groups": u.groups_id.mapped("name")[:20],
            })

        raise _Forbidden(f"Unknown tool '{name}'")

    def _content(self, payload):
        try:
            text = json.dumps(payload, default=str)
        except Exception:
            text = str(payload)
        return {"content": [{"type": "text", "text": text}]}

    # ───────────── resources ─────────────────────────────────────────
    def _resources_list(self, key):
        allowed = (key.allowed_models or "").strip()
        models = (allowed.split(",") if allowed != "*"
                  else ["res.partner", "product.template", "sale.order"])
        return {"resources": [
            {"uri": f"odoo://model/{m}", "name": m,
             "description": f"Schema of {m}",
             "mimeType": "application/json"} for m in models if m
        ]}

    def _resources_read(self, key, env, params):
        uri = params.get("uri") or ""
        if not uri.startswith("odoo://model/"):
            raise _Forbidden(f"Unknown resource '{uri}'")
        model = uri.replace("odoo://model/", "").strip()
        if not key.is_model_allowed(model) or model not in env:
            raise _Forbidden(f"Model '{model}' out of scope")
        schema = env[model].fields_get(attributes=["string", "type", "required", "help"])
        return {"contents": [{"uri": uri, "mimeType": "application/json",
                              "text": json.dumps(schema, default=str)}]}

    # ───────────── prompts ───────────────────────────────────────────
    def _prompts_list(self, env):
        prompts = env["mn.mcp.prompt"].sudo().search([("active", "=", True)])
        return {"prompts": [p.to_mcp() for p in prompts]}

    def _prompts_get(self, env, params):
        name = params.get("name")
        args = params.get("arguments") or {}
        p = env["mn.mcp.prompt"].sudo().search([("name", "=", name), ("active", "=", True)], limit=1)
        if not p:
            raise _Forbidden(f"Prompt '{name}' not found")
        text = p.render(args)
        return {"description": p.title or name,
                "messages": [{"role": "user",
                              "content": {"type": "text", "text": text}}]}
