# -*- coding: utf-8 -*-
"""Confirm-before-write — the guard rail that makes an LLM safe near an ERP.

The single most common objection to connecting an AI assistant to a live ERP is
"what stops it deleting my customers". Odoo's ACLs stop it doing what the *user*
cannot do; they do not stop it doing something the user could do but did not
mean to. This module adds the missing step: for destructive or bulk operations,
the server refuses to act until a human has seen exactly what is about to
happen and said yes.

It is built on **MRTR** (Multi Round-Trip Requests, 2026-07-28). The server
returns ``resultType: "input_required"`` with an elicitation asking for
confirmation, plus an opaque ``requestState``. The client shows the prompt,
then retries the same call with the answer. No session, no server-side pending
table — which is the whole point of MRTR, and means this works behind a load
balancer with no sticky routing.

``requestState`` crosses the client, so the spec is blunt about treating it as
attacker-controlled. Ours is HMAC-signed and carries:

* the authenticated principal — state minted for one key cannot be replayed by
  another,
* a short expiry,
* a digest of the exact call it was issued for — so a confirmation for
  "delete 3 draft quotes" cannot be replayed to authorise "delete 3000
  invoices".

Older clients have no MRTR. Rather than leaving them unprotected or blocking
them, they get the same guarantee through an explicit ``confirm: true``
argument, which the model must set after telling the user what it is about to
do. Same protection, one fewer round trip, and it works on every revision.
"""
import base64
import hashlib
import hmac
import json
import time

from odoo.http import request

from . import protocol as P

# Operations that are never silently executed.
ALWAYS_CONFIRM = {"odoo_unlink"}
# Operations that need confirmation once they touch more than N records.
BULK_TOOLS = {"odoo_write": "confirm_write_over",
              "odoo_create_many": "confirm_create_over"}
# Calling arbitrary model methods is confirmed by default: the server cannot
# know what `action_post` or `unlink_all` does on a custom model.
METHOD_TOOLS = {"odoo_execute", "odoo_run_server_action"}

STATE_TTL_SECONDS = 300
CONFIRM_KEY = "mcp_confirm"          # key of the elicitation in inputRequests


# ----------------------------------------------------------------------
# requestState — signed, self-contained, no server-side storage
# ----------------------------------------------------------------------
def _secret():
    """A per-database signing secret, distinct from Odoo's session secret."""
    params = request.env["ir.config_parameter"].sudo()
    secret = params.get_param("mn_mcp.confirm_secret")
    if not secret:
        import secrets as _s
        secret = _s.token_urlsafe(48)
        params.set_param("mn_mcp.confirm_secret", secret)
    return secret.encode()


def _digest(tool, arguments):
    """A stable fingerprint of the call this confirmation is good for.

    sort_keys matters: without it the same call could hash differently between
    two requests and every confirmation would be rejected as a mismatch.
    """
    payload = json.dumps({"tool": tool, "args": arguments},
                         sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def mint_state(api_key, tool, arguments):
    body = {
        "k": api_key.id,
        "u": api_key.user_id.id,
        "d": _digest(tool, arguments),
        "e": int(time.time()) + STATE_TTL_SECONDS,
    }
    raw = json.dumps(body, separators=(",", ":")).encode()
    sig = hmac.new(_secret(), raw, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(raw + b"." + sig).decode()


def verify_state(state, api_key, tool, arguments):
    """True only for state this server minted, for this caller, for this call."""
    try:
        blob = base64.urlsafe_b64decode((state or "").encode())
        raw, sig = blob.rsplit(b".", 1)
        expected = hmac.new(_secret(), raw, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            return False
        body = json.loads(raw)
    except Exception:  # noqa: BLE001 — any malformed state is simply invalid
        return False

    if body.get("e", 0) < time.time():
        return False
    if body.get("k") != api_key.id or body.get("u") != api_key.user_id.id:
        return False
    # The digest binds the approval to the exact arguments that were shown to
    # the user. Approving a small delete must not authorise a large one.
    return hmac.compare_digest(str(body.get("d", "")), _digest(tool, arguments))


# ----------------------------------------------------------------------
# Policy
# ----------------------------------------------------------------------
def _param(name, default):
    value = request.env["ir.config_parameter"].sudo().get_param(
        f"mn_mcp.{name}", default)
    return value


def _enabled():
    return _param("confirm_enabled", "True") in ("True", "true", "1", True)


def _count_targets(tool, arguments):
    if tool == "odoo_write":
        return len(arguments.get("ids") or [])
    if tool == "odoo_create_many":
        return len(arguments.get("records") or [])
    if tool == "odoo_unlink":
        return len(arguments.get("ids") or [])
    return 0


def needs_confirmation(tool, arguments):
    """Does this call require a human before it runs?"""
    if not _enabled():
        return False
    # A custom tool that runs a server action can do anything that action does,
    # so it is treated like odoo_execute rather than like a query.
    custom = request.env["mn.mcp.tool"].sudo().search([("name", "=", tool)], limit=1)
    if custom:
        return custom.kind == "action" and _param(
            "confirm_execute", "True") in ("True", "true", "1", True)
    if tool in ALWAYS_CONFIRM:
        return True
    if tool in METHOD_TOOLS:
        return _param("confirm_execute", "True") in ("True", "true", "1", True)
    if tool in BULK_TOOLS:
        try:
            threshold = int(_param(BULK_TOOLS[tool], "10"))
        except (TypeError, ValueError):
            threshold = 10
        # A threshold of 0 means "confirm every one of these".
        return _count_targets(tool, arguments) > threshold if threshold else True
    return False


def describe(tool, arguments, env):  # noqa: C901 — a flat map of cases reads better
    """A sentence a human can actually check, not a JSON dump.

    The whole guard rail is worthless if the prompt says
    "execute odoo_unlink?" — the user has to see *what* is about to happen.
    """
    model = arguments.get("model") or ""
    label = model
    if model:
        described = env["ir.model"].sudo().search([("model", "=", model)], limit=1)
        if described:
            label = f"{described.name} ({model})"

    custom = env["mn.mcp.tool"].sudo().search([("name", "=", tool)], limit=1)
    if custom:
        return (f"Run the custom tool '{custom.name}' — {custom.description} "
                f"This runs a server action on {custom.model_name}.")

    count = _count_targets(tool, arguments)
    if tool == "odoo_unlink":
        return f"Permanently delete {count} record(s) from {label}. This cannot be undone."
    if tool == "odoo_write":
        fields = ", ".join(sorted((arguments.get("values") or {}).keys())) or "no fields"
        return f"Update {count} record(s) in {label}. Fields: {fields}."
    if tool == "odoo_create_many":
        return f"Create {count} new record(s) in {label}."
    if tool == "odoo_execute":
        return (f"Call the method '{arguments.get('method')}' on {label}. "
                f"The server cannot predict what this does.")
    if tool == "odoo_run_server_action":
        return f"Run server action {arguments.get('action_id')} on {label}."
    return f"Run {tool} on {label}."


# ----------------------------------------------------------------------
# The MRTR round trip
# ----------------------------------------------------------------------
def client_supports_elicitation(params):
    """Only offer elicitation to a client that declared it.

    The spec forbids sending an inputRequest the client never said it could
    handle — doing so strands the call, because nothing will ever answer it.
    """
    caps = ((params.get("_meta") or {}).get(P.META_CLIENT_CAPS) or {})
    return "elicitation" in caps


def already_confirmed(params, api_key, tool, arguments):
    """Has the user already said yes to exactly this call?"""
    # Path 1 — MRTR retry: signed state plus an accepted elicitation.
    state = params.get("requestState") or (params.get("_meta") or {}).get("requestState")
    if state and verify_state(state, api_key, tool, arguments):
        responses = params.get("inputResponses") or {}
        answer = responses.get(CONFIRM_KEY) or {}
        if answer.get("action") == "accept":
            content = answer.get("content") or {}
            # An explicit "no" in the form is still an answer — respect it.
            return bool(content.get("confirm", True))
        # State is valid but the user declined or did not answer.
        return False

    # Path 2 — clients without MRTR: an explicit argument. Removed before the
    # call runs so it never reaches the ORM.
    return bool(arguments.get("confirm"))


def input_required(tool, arguments, api_key, env, offer_elicitation):
    """Build the InputRequiredResult that asks the human."""
    summary = describe(tool, arguments, env)
    result = {
        "resultType": "input_required",
        "requestState": mint_state(api_key, tool, arguments),
    }
    if offer_elicitation:
        result["inputRequests"] = {
            CONFIRM_KEY: {
                "method": "elicitation/create",
                "params": {
                    "mode": "form",
                    "message": f"Confirm this action in Odoo:\n\n{summary}",
                    "requestedSchema": {
                        "type": "object",
                        "properties": {
                            "confirm": {
                                "type": "boolean",
                                "title": "Go ahead",
                                "description": summary,
                            },
                        },
                        "required": ["confirm"],
                    },
                },
            },
        }
    else:
        # No elicitation support: tell the model exactly how to proceed. Per
        # the spec an InputRequiredResult must carry at least one of
        # inputRequests or requestState — we always send the state.
        result["content"] = [{
            "type": "text",
            "text": (f"CONFIRMATION REQUIRED. {summary}\n\n"
                     "Tell the user what will happen and get their agreement, "
                     "then call this tool again with \"confirm\": true."),
        }]
    return result
