# -*- coding: utf-8 -*-
{
    "name": "Odoo MCP Server | Free | Claude · ChatGPT · Gemini · AI Agents",
    "version": "19.0.3.2.0",
    "category": "Tools",
    "summary": "Turn Odoo into an MCP tool server. Free LGPL-3. Speaks the current "
               "2026-07-28 stateless MCP spec AND every earlier revision, negotiated "
               "per request. Connect Claude, ChatGPT, Cursor and any MCP client to "
               "live Odoo data — 24 tools, scoped API keys, model whitelists, "
               "permission enforcement and a full audit log.",
    "description": """
Odoo MCP Server (FREE)
======================
Expose Odoo as a Model Context Protocol (MCP) tool server so AI assistants
can read and write your live ERP data — safely.

Protocol support — current, and backwards compatible
----------------------------------------------------
MCP has been revised four times, and the **2026-07-28** revision is a breaking
redesign: it removes the ``initialize`` handshake and protocol-level sessions,
makes every request self-contained, and adds required result fields.

This server negotiates the revision **per request** and speaks all of them:

* ``2026-07-28`` — stateless core, ``server/discover``, ``resultType``,
  cacheable list results (``ttlMs`` / ``cacheScope``), renumbered error codes,
  ``Mcp-Method`` routing-header validation
* ``2025-11-25`` · ``2025-06-18`` · ``2025-03-26`` · ``2024-11-05``

A 2024-era client keeps working untouched after you upgrade — it never sees
the new fields. A 2026 client gets the new shape without an initialize call.
Tools are returned in a deterministic order so clients can cache the list and
the model's prompt cache stays warm.

Custom tools — teach it your business, without code
---------------------------------------------------
The built-in tools are primitives, so the model has to work out what "overdue"
or "at risk" means in *your* Odoo. It usually gets there. Usually is not good
enough on a Monday morning.

Define a tool in the Odoo UI instead:

    name         overdue_invoices
    description  Invoices past their due date and not yet paid.
    model        account.move
    domain       [("move_type","=","out_invoice"),
                  ("payment_state","!=","paid"),
                  ("invoice_date_due","<",{as_of})]
    parameter    as_of · date · defaults to today

Now the AI calls one tool with one obvious argument, and *the business* decides
what overdue means rather than the model improvising it.

* Three kinds — find records, aggregate/count by, or run a server action
* Typed parameters substituted into the domain as literals, so a parameter can
  never inject its own clause
* Broken domains are caught when you save, not at 3am inside an answer
* Custom tools run as the API key's user, inside that key's allowed models.
  They can narrow what the AI sees; they can never widen it
* No free-form Python: a tool that runs arbitrary code is a remote shell with
  extra steps. Point one at an ``ir.actions.server`` if you genuinely need it —
  that is Odoo's own reviewed mechanism, with its own permissions

Confirm before it deletes — the guard rail nobody else ships
------------------------------------------------------------
Odoo's access rules stop an AI doing what the *user* may not do. They do not
stop it doing something the user could do but did not mean to. This does.

Deleting records, editing in bulk, or calling a model method now stops until a
human has seen **exactly what is about to happen** and agreed:

    Permanently delete 42 record(s) from Customer Invoice (account.move).
    This cannot be undone.                              [ Confirm ]  [ Cancel ]

* Built on **MRTR** (Multi Round-Trip Requests, 2026-07-28) — stateless, so it
  works behind a load balancer with no sticky sessions
* The approval is **cryptographically bound to the exact call**: a confirmation
  for "delete 3 draft quotes" cannot be replayed to authorise "delete 3000
  invoices". Forged or expired state is refused.
* Clients without elicitation are told to re-call with ``confirm: true`` — the
  same protection on every protocol revision
* Thresholds are yours: always confirm deletes, confirm updates over N records,
  confirm arbitrary method calls. Or switch the whole thing off.

OAuth 2.1 — connect a whole team without pasting tokens
--------------------------------------------------------
Pasting a bearer token into a connector URL puts it in browser history, proxy
logs and screenshots. With OAuth, a user clicks Connect, logs in to Odoo, sees
a consent screen, and every call afterwards runs **as them**.

Implemented as both authorization server and resource server, so there is no
second system to install:

* **Protected Resource Metadata** (RFC 9728) and **Authorization Server
  Metadata** (RFC 8414) — discovery is automatic; the 401 tells the client
  where to go
* **PKCE with S256 only** — plain is not offered
* **Client ID Metadata Documents** — the modern registration path; a client
  publishes its own metadata and needs no pre-registration. Dynamic Client
  Registration is still accepted for clients that only speak it
* **Audience-bound tokens** (RFC 8707) — a token minted for another MCP server
  is refused here, which is the confused-deputy attack the spec names
* **Refresh-token rotation**, and a replayed authorization code revokes every
  token it issued
* **Scopes** ``odoo:read`` / ``odoo:write`` / ``odoo:admin``, mapped onto the
  same permission model as an API key — one place decides what a caller may do
* Access tokens are refused in the query string, per the spec

Endpoints (JSON-RPC 2.0 over HTTP)
----------------------------------
* ``/mcp`` — server/discover + tools/list + tools/call + resources/list +
  resources/read + prompts/list + prompts/get (+ initialize for old clients)
* Bearer-token authentication using scoped API keys
* Every tool carries ``readOnlyHint`` / ``destructiveHint`` annotations, so a
  client knows which calls are safe to run unattended and which need a human

Out-of-the-box tools
--------------------
* ``odoo.search`` — search records on any allowed model
* ``odoo.read`` — read fields for given ids
* ``odoo.create`` — create a record
* ``odoo.write`` — update a record
* ``odoo.unlink`` — delete (manager-scoped key required)
* ``odoo.fields_get`` — discover a model's schema
* ``odoo.list_models`` — list models the key is allowed to touch
* ``odoo.execute`` — call a model method (whitelist-gated)

Safety rails
------------
* **Scoped API keys** — per-key allowed models, permissions (r/w/c/d),
  per-day request quota, expiry date
* **Permission enforcement** — every call runs under the API key's user;
  Odoo's standard ACL + record rules apply
* **Audit log** — every request stored with method, args (hashed), latency,
  success / failure, response code
* **Rate limiting** — daily quota per key

Pricing
-------
**FREE** under LGPL-3. Source code on GitHub. Lifetime updates.
The premium paid alternatives are $200+. This one is free because every
MENA Odoo shop should have AI access without paying twice.
    """,
    "author": "Moaz Nabil",
    "website": "https://github.com/moaaznaabilali",
    "support": "moaaznaabilali@gmail.com",
    "license": "LGPL-3",
    "depends": ["base", "mail", "web"],
    "data": [
        "security/mcp_security.xml",
        "security/ir.model.access.csv",
        "data/sequences.xml",
        "data/config_data.xml",
        "data/cron.xml",
        "data/prompts_data.xml",
        "views/mcp_api_key_views.xml",
        "views/oauth_templates.xml",
        "views/mcp_oauth_views.xml",
        "views/mcp_tool_views.xml",
        "views/mcp_audit_views.xml",
        "views/mcp_prompt_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mn_mcp_server/static/src/lib/chart.umd.min.js",
            "mn_mcp_server/static/src/dashboard/mcp_dashboard.js",
            "mn_mcp_server/static/src/dashboard/mcp_dashboard.xml",
        ],
    },
    "images": ["static/description/banner.png"],
    "installable": True,
    "application": True,
    "auto_install": False,
}
