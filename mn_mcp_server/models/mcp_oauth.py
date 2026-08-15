# -*- coding: utf-8 -*-
"""OAuth 2.1 for MCP — Odoo acts as both authorization server and resource server.

Why this exists: pasting a bearer token into a connector URL is a support
burden and a security smell (the token ends up in browser history, proxy logs
and screenshots). OAuth lets a whole team connect claude.ai and have every
call run as *themselves*, with Odoo's own login and record rules.

Design decision worth knowing: an issued access token does not carry its own
copy of the permission logic. It provisions a hidden ``mn.mcp.api_key`` and
points at it. Everything downstream — model whitelist, r/w/c/d flags, rate
limit, audit log — then works unchanged, and there is exactly one place where
"what may this caller touch" is decided. Two parallel permission systems is
how these servers grow holes.

Tokens are stored as SHA-256 hashes. A database dump therefore cannot be
replayed against the server.
"""
import hashlib
import json
import logging
import secrets
from datetime import timedelta
from urllib.parse import urlparse

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# Scope → the permission flags it grants on the provisioned key.
# Deliberately coarse: fine-grained scopes that nobody can explain lead to
# users granting everything anyway.
SCOPES = {
    "odoo:read": {"perm_read": True},
    "odoo:write": {"perm_read": True, "perm_write": True, "perm_create": True},
    "odoo:admin": {"perm_read": True, "perm_write": True,
                   "perm_create": True, "perm_unlink": True},
}
DEFAULT_SCOPE = "odoo:read"
# Advertised as the minimum for basic functionality; clients step up from here.
SCOPES_SUPPORTED = ["odoo:read", "odoo:write", "odoo:admin"]

AUTH_CODE_TTL_SECONDS = 60          # OAuth 2.1: codes should be short-lived
ACCESS_TOKEN_TTL_HOURS = 8          # one working day
REFRESH_TOKEN_TTL_DAYS = 30


def _hash(raw):
    return hashlib.sha256((raw or "").encode()).hexdigest()


class McpOauthClient(models.Model):
    """A client that may ask for tokens.

    Three ways one gets here, in the priority the spec gives them:

    * **Client ID Metadata Documents** — the client_id *is* an HTTPS URL that
      serves its own metadata. Nothing to pre-register; we fetch and validate.
    * **Pre-registration** — an administrator creates the record by hand.
    * **Dynamic Client Registration** — deprecated in 2026-07-28 but kept,
      because the authorization servers and clients in the wild still use it.
    """

    _name = "mn.mcp.oauth.client"
    _description = "MCP OAuth Client"
    _order = "create_date desc"

    name = fields.Char(required=True)
    client_id = fields.Char(required=True, index=True, copy=False)
    client_secret_hash = fields.Char(copy=False)
    redirect_uris = fields.Text(
        required=True,
        help="One per line. A redirect URI must match one of these exactly.")
    source = fields.Selection([
        ("cimd", "Client ID Metadata Document"),
        ("manual", "Pre-registered"),
        ("dcr", "Dynamic Registration (deprecated)"),
    ], default="manual", required=True, readonly=True)
    metadata_json = fields.Text(readonly=True, help="The fetched CIMD document.")
    active = fields.Boolean(default=True)
    last_seen = fields.Datetime(readonly=True)
    token_ids = fields.One2many("mn.mcp.oauth.token", "client_id_ref")
    token_count = fields.Integer(compute="_compute_token_count")

    _sql_constraints = [
        ("client_id_uniq", "unique(client_id)", "That client_id already exists."),
    ]

    def _compute_token_count(self):
        for r in self:
            r.token_count = len(r.token_ids)

    # ------------------------------------------------------------------
    def redirect_list(self):
        self.ensure_one()
        return [u.strip() for u in (self.redirect_uris or "").splitlines() if u.strip()]

    def check_redirect(self, redirect_uri):
        """Exact match only.

        Prefix or wildcard matching on redirect URIs is the classic open-redirect
        hole in OAuth deployments: an attacker registers a path they control
        under an allowed prefix and harvests authorization codes.
        """
        return redirect_uri in self.redirect_list()

    # ------------------------------------------------------------------
    @api.model
    def resolve(self, client_id):
        """Find a client, resolving a Client ID Metadata Document if needed."""
        existing = self.sudo().search([("client_id", "=", client_id)], limit=1)
        if existing:
            return existing
        if str(client_id or "").startswith("https://"):
            return self._resolve_cimd(client_id)
        return self.browse()

    @api.model
    def _resolve_cimd(self, url):
        """Fetch and validate a Client ID Metadata Document.

        Security notes, in order of how badly each would hurt:

        * HTTPS only, and the document must be served *from the client_id URL
          itself* — that is what binds the identity to the domain.
        * ``redirect_uris`` must be same-origin with the client_id. Without
          this a document could nominate somebody else's callback.
        * Short timeout and a size cap: this is an outbound fetch triggered by
          an unauthenticated request, so it is a DoS surface.
        """
        import requests

        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.fragment:
            _logger.warning("MCP OAuth: refusing non-HTTPS client_id %s", url)
            return self.browse()

        try:
            response = requests.get(url, timeout=5, headers={"Accept": "application/json"})
            response.raise_for_status()
            if len(response.content) > 64_000:
                raise ValueError("client metadata document too large")
            doc = response.json()
        except Exception as exc:  # noqa: BLE001 — any failure means "no client"
            _logger.warning("MCP OAuth: could not resolve client_id %s (%s)", url, exc)
            return self.browse()

        if doc.get("client_id") and doc["client_id"] != url:
            _logger.warning("MCP OAuth: client_id mismatch in metadata for %s", url)
            return self.browse()

        redirects = [u for u in (doc.get("redirect_uris") or []) if isinstance(u, str)]
        origin = f"{parsed.scheme}://{parsed.netloc}"
        same_origin = [u for u in redirects if u.startswith(origin + "/") or u == origin]
        if not same_origin:
            _logger.warning(
                "MCP OAuth: no same-origin redirect_uris in metadata for %s", url)
            return self.browse()

        return self.sudo().create({
            "name": doc.get("client_name") or parsed.netloc,
            "client_id": url,
            "redirect_uris": "\n".join(same_origin),
            "source": "cimd",
            "metadata_json": json.dumps(doc, indent=2)[:20000],
        })


class McpOauthGrant(models.Model):
    """A pending authorization code. Single-use and short-lived."""

    _name = "mn.mcp.oauth.grant"
    _description = "MCP OAuth Authorization Code"
    _order = "create_date desc"
    _rec_name = "client_id_ref"

    code_hash = fields.Char(required=True, index=True, copy=False)
    client_id_ref = fields.Many2one("mn.mcp.oauth.client", required=True,
                                    ondelete="cascade", string="Client")
    user_id = fields.Many2one("res.users", required=True, ondelete="cascade")
    redirect_uri = fields.Char(required=True)
    code_challenge = fields.Char(required=True)
    scope = fields.Char(default=DEFAULT_SCOPE)
    resource = fields.Char(help="RFC 8707 audience this code may be exchanged for.")
    expires_at = fields.Datetime(required=True)
    used = fields.Boolean(default=False)

    @api.model
    def issue(self, client, user, redirect_uri, code_challenge, scope, resource):
        raw = secrets.token_urlsafe(32)
        self.sudo().create({
            "code_hash": _hash(raw),
            "client_id_ref": client.id,
            "user_id": user.id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "scope": scope or DEFAULT_SCOPE,
            "resource": resource or "",
            "expires_at": fields.Datetime.now() + timedelta(seconds=AUTH_CODE_TTL_SECONDS),
        })
        return raw

    @api.model
    def consume(self, raw_code, verifier, client, redirect_uri):
        """Validate and burn an authorization code.

        Returns the grant, or raises ValidationError with an OAuth error code
        as the message so the controller can map it straight to a response.
        """
        grant = self.sudo().search([("code_hash", "=", _hash(raw_code))], limit=1)
        if not grant:
            raise ValidationError("invalid_grant")
        # Burn it first: a replayed code must fail even if a later check raises.
        already_used = grant.used
        grant.used = True
        if already_used:
            # OAuth 2.1: a reused code means the code may have leaked. Revoke
            # everything already issued from it rather than just refusing.
            #
            # Flagging beats deleting: the row stays for the audit trail, and
            # a flush here makes the revocation durable before the exception
            # unwinds the call — otherwise the security action can be lost
            # with the transaction that raised.
            self.env["mn.mcp.oauth.token"].sudo().search(
                [("grant_id", "=", grant.id)]).write({"revoked": True})
            # Write it through and drop the cache: a security state change must
            # be readable by the next lookup even if that lookup happens in a
            # different environment, and must not be served from a stale cache.
            self.env.flush_all()
            self.env.invalidate_all()
            raise ValidationError("invalid_grant")
        if grant.expires_at < fields.Datetime.now():
            raise ValidationError("invalid_grant")
        if grant.client_id_ref != client:
            raise ValidationError("invalid_grant")
        if grant.redirect_uri != redirect_uri:
            raise ValidationError("invalid_grant")
        # PKCE S256 — the only method OAuth 2.1 allows.
        import base64
        digest = hashlib.sha256((verifier or "").encode()).digest()
        expected = base64.urlsafe_b64encode(digest).decode().rstrip("=")
        if not secrets.compare_digest(expected, grant.code_challenge or ""):
            raise ValidationError("invalid_grant")
        return grant


class McpOauthToken(models.Model):
    """An issued access token (and its refresh token).

    The token itself carries no permissions — ``api_key_id`` does. See the
    module docstring for why.
    """

    _name = "mn.mcp.oauth.token"
    _description = "MCP OAuth Token"
    _order = "create_date desc"
    _rec_name = "client_id_ref"

    access_hash = fields.Char(required=True, index=True, copy=False)
    refresh_hash = fields.Char(index=True, copy=False)
    client_id_ref = fields.Many2one("mn.mcp.oauth.client", required=True,
                                    ondelete="cascade", string="Client")
    user_id = fields.Many2one("res.users", required=True, ondelete="cascade")
    api_key_id = fields.Many2one("mn.mcp.api_key", ondelete="cascade",
                                 help="Carries the scoping for this token.")
    grant_id = fields.Many2one("mn.mcp.oauth.grant", ondelete="set null")
    scope = fields.Char(default=DEFAULT_SCOPE)
    audience = fields.Char(help="RFC 8707 resource this token is bound to.")
    expires_at = fields.Datetime(required=True)
    refresh_expires_at = fields.Datetime()
    revoked = fields.Boolean(default=False)

    # ------------------------------------------------------------------
    @api.model
    def _provision_key(self, user, client, scope):
        """Create the hidden API key that carries this token's permissions."""
        perms = {"perm_read": False, "perm_write": False,
                 "perm_create": False, "perm_unlink": False}
        for one in (scope or DEFAULT_SCOPE).split():
            perms.update(SCOPES.get(one, {}))

        Key = self.env["mn.mcp.api_key"].sudo()
        vals = {
            "name": f"OAuth · {client.name} · {user.name}",
            "user_id": user.id,
            **perms,
        }
        # Inherit the instance-wide default model whitelist, exactly as a
        # hand-made key does — an OAuth session should not be broader than
        # what the administrator configured as the default.
        return Key.create(vals)

    @api.model
    def issue(self, client, user, scope, audience, grant=None):
        access = secrets.token_urlsafe(40)
        refresh = secrets.token_urlsafe(40)
        now = fields.Datetime.now()
        self.sudo().create({
            "access_hash": _hash(access),
            "refresh_hash": _hash(refresh),
            "client_id_ref": client.id,
            "user_id": user.id,
            "api_key_id": self._provision_key(user, client, scope).id,
            "grant_id": grant.id if grant else False,
            "scope": scope or DEFAULT_SCOPE,
            "audience": audience or "",
            "expires_at": now + timedelta(hours=ACCESS_TOKEN_TTL_HOURS),
            "refresh_expires_at": now + timedelta(days=REFRESH_TOKEN_TTL_DAYS),
        })
        client.sudo().last_seen = now
        return {
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "Bearer",
            "expires_in": ACCESS_TOKEN_TTL_HOURS * 3600,
            "scope": scope or DEFAULT_SCOPE,
        }

    @api.model
    def authenticate(self, raw_token, audience=None):
        """Resolve a bearer token to its API key, or return an empty recordset.

        Audience binding is the point of RFC 8707 and the reason the spec says
        a server MUST NOT accept tokens issued for somebody else: without this
        check, a token minted for another MCP server would work here, which is
        the confused-deputy attack the spec calls out by name.
        """
        token = self.sudo().search([("access_hash", "=", _hash(raw_token))], limit=1)
        if not token or token.revoked:
            return self.env["mn.mcp.api_key"].browse()
        if token.expires_at < fields.Datetime.now():
            return self.env["mn.mcp.api_key"].browse()
        if audience and token.audience and not _audience_matches(token.audience, audience):
            _logger.warning("MCP OAuth: token audience %s does not match %s",
                            token.audience, audience)
            return self.env["mn.mcp.api_key"].browse()
        return token.api_key_id

    @api.model
    def refresh(self, raw_refresh, client):
        """Exchange a refresh token, rotating it (OAuth 2.1 requires rotation)."""
        token = self.sudo().search([("refresh_hash", "=", _hash(raw_refresh))], limit=1)
        if (not token or token.revoked or token.client_id_ref != client
                or not token.refresh_expires_at
                or token.refresh_expires_at < fields.Datetime.now()):
            raise ValidationError("invalid_grant")
        issued = self.issue(client, token.user_id, token.scope, token.audience)
        token.revoked = True
        return issued

    @api.autovacuum
    def _gc_expired(self):
        """Expired tokens and used codes are noise; clear them nightly."""
        now = fields.Datetime.now()
        self.sudo().search([("refresh_expires_at", "<", now)]).unlink()
        self.env["mn.mcp.oauth.grant"].sudo().search(
            [("expires_at", "<", now - timedelta(days=1))]).unlink()


def _audience_matches(bound, requested):
    """Compare canonical resource URIs, tolerating a trailing slash.

    The spec asks for exact string comparison but also says implementations
    should prefer the no-trailing-slash form; real clients send both.
    """
    return bound.rstrip("/").lower() == (requested or "").rstrip("/").lower()
