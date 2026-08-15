# -*- coding: utf-8 -*-
"""OAuth 2.1 endpoints — discovery, authorization, token, registration.

MCP splits the world into a *resource server* (this MCP endpoint) and an
*authorization server* (whoever issues tokens). Odoo plays both here, because
asking a workshop owner to also run Keycloak is not a product.

The discovery documents are what make the whole flow automatic: a client hits
``/mcp`` with no token, gets a 401 naming its metadata URL, follows that to the
authorization server, and from there it is ordinary OAuth. Nobody pastes a
token anywhere.
"""
import json
import logging
import secrets
from urllib.parse import urlencode

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

from ..models.mcp_oauth import DEFAULT_SCOPE, SCOPES, SCOPES_SUPPORTED

_logger = logging.getLogger(__name__)

MCP_PATH = "/mcp"


def base_url():
    """The externally reachable origin.

    Taken from the live request rather than a stored parameter: these servers
    get reached over nip.io, a tunnel, or a reverse proxy, and a hardcoded
    web.base.url produces discovery documents that point somewhere the client
    cannot reach. ``mn_mcp.public_url`` overrides when the guess is wrong.
    """
    override = request.env["ir.config_parameter"].sudo().get_param("mn_mcp.public_url")
    if override:
        return override.rstrip("/")
    host = (request.httprequest.host_url or "").rstrip("/")
    if host:
        return host
    return (request.env["ir.config_parameter"].sudo()
            .get_param("web.base.url", "")).rstrip("/")


def _json(payload, status=200, headers=None):
    hdr = [("Content-Type", "application/json"),
           ("Access-Control-Allow-Origin", "*"),
           ("Cache-Control", "no-store")]
    if headers:
        hdr.extend(headers)
    return request.make_response(json.dumps(payload), status=status, headers=hdr)


def _oauth_error(code, description=None, status=400):
    payload = {"error": code}
    if description:
        payload["error_description"] = description
    return _json(payload, status=status)


class McpOauth(http.Controller):

    # ==================================================================
    # Discovery
    # ==================================================================
    @http.route(["/.well-known/oauth-protected-resource",
                 "/.well-known/oauth-protected-resource/mcp"],
                type="http", auth="public", methods=["GET", "OPTIONS"],
                csrf=False, cors="*", save_session=False)
    def protected_resource_metadata(self, **kw):
        """RFC 9728 — MUST be implemented by an MCP server.

        Both paths are served: the bare one, and the path-suffixed variant a
        client derives from a resource URL of ``https://host/mcp``.
        """
        root = base_url()
        return _json({
            "resource": f"{root}{MCP_PATH}",
            "authorization_servers": [root],
            "scopes_supported": SCOPES_SUPPORTED,
            "bearer_methods_supported": ["header"],
            "resource_documentation": "https://github.com/moaaznaabilali",
        })

    @http.route(["/.well-known/oauth-authorization-server",
                 "/.well-known/oauth-authorization-server/mcp",
                 "/.well-known/openid-configuration"],
                type="http", auth="public", methods=["GET", "OPTIONS"],
                csrf=False, cors="*", save_session=False)
    def authorization_server_metadata(self, **kw):
        """RFC 8414. The OIDC path is served too because clients MUST try both."""
        root = base_url()
        return _json({
            "issuer": root,
            "authorization_endpoint": f"{root}/mcp/oauth/authorize",
            "token_endpoint": f"{root}/mcp/oauth/token",
            "registration_endpoint": f"{root}/mcp/oauth/register",
            "revocation_endpoint": f"{root}/mcp/oauth/revoke",
            "scopes_supported": SCOPES_SUPPORTED,
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            # OAuth 2.1 allows S256 only — "plain" is not offered on purpose.
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
            # We emit `iss` on every authorization response, so we must say so.
            "authorization_response_iss_parameter_supported": True,
            "client_id_metadata_document_supported": True,
        })

    # ==================================================================
    # Authorization
    # ==================================================================
    @http.route("/mcp/oauth/authorize", type="http", auth="public",
                methods=["GET", "POST"], csrf=False, website=False)
    def authorize(self, **kw):
        """The consent screen.

        ``auth="public"`` and then a manual session check, rather than
        ``auth="user"``: Odoo's own redirect would bounce the user to the login
        page and lose the OAuth query string, stranding the flow.
        """
        client_id = kw.get("client_id") or ""
        redirect_uri = kw.get("redirect_uri") or ""
        state = kw.get("state") or ""
        scope = (kw.get("scope") or DEFAULT_SCOPE).strip()
        resource = kw.get("resource") or ""
        challenge = kw.get("code_challenge") or ""
        method = (kw.get("code_challenge_method") or "").upper()

        if kw.get("response_type") not in ("code",):
            return _oauth_error("unsupported_response_type")
        if not challenge or method != "S256":
            return _oauth_error("invalid_request", "PKCE with S256 is required")

        client = request.env["mn.mcp.oauth.client"].sudo().resolve(client_id)
        if not client or not client.active:
            return _oauth_error("invalid_client", "Unknown client_id")
        # Never redirect to an unregistered URI — that is the open-redirect
        # hole. An error here is rendered, not bounced back to the caller.
        if not client.check_redirect(redirect_uri):
            return _oauth_error("invalid_request", "redirect_uri is not registered")

        unknown = [s for s in scope.split() if s not in SCOPES]
        if unknown:
            return self._redirect_error(redirect_uri, "invalid_scope", state)

        # Not logged in? Send them through Odoo's login and come back here.
        if not request.session.uid:
            login_url = "/web/login?" + urlencode({
                "redirect": request.httprequest.full_path,
            })
            return request.redirect(login_url)

        user = request.env["res.users"].sudo().browse(request.session.uid)

        if request.httprequest.method == "POST":
            if kw.get("decision") != "allow":
                return self._redirect_error(redirect_uri, "access_denied", state)
            code = request.env["mn.mcp.oauth.grant"].sudo().issue(
                client, user, redirect_uri, challenge, scope, resource)
            params = {"code": code, "iss": base_url()}
            if state:
                params["state"] = state
            return request.redirect(f"{redirect_uri}?{urlencode(params)}", local=False)

        return request.render("mn_mcp_server.oauth_consent", {
            "client": client,
            "user": user,
            "scopes": [(s, SCOPES.get(s, {})) for s in scope.split()],
            "scope": scope,
            "params": {
                "client_id": client_id, "redirect_uri": redirect_uri,
                "state": state, "scope": scope, "resource": resource,
                "code_challenge": challenge, "code_challenge_method": method,
                "response_type": "code",
            },
        })

    def _redirect_error(self, redirect_uri, code, state):
        """Errors go back to the client, carrying `iss` per RFC 9207."""
        params = {"error": code, "iss": base_url()}
        if state:
            params["state"] = state
        return request.redirect(f"{redirect_uri}?{urlencode(params)}", local=False)

    # ==================================================================
    # Token
    # ==================================================================
    @http.route("/mcp/oauth/token", type="http", auth="public",
                methods=["POST", "OPTIONS"], csrf=False, cors="*",
                save_session=False)
    def token(self, **kw):
        grant_type = kw.get("grant_type")
        client = request.env["mn.mcp.oauth.client"].sudo().resolve(
            kw.get("client_id") or "")
        if not client or not client.active:
            return _oauth_error("invalid_client", status=401)

        Token = request.env["mn.mcp.oauth.token"].sudo()
        try:
            if grant_type == "authorization_code":
                grant = request.env["mn.mcp.oauth.grant"].sudo().consume(
                    kw.get("code") or "", kw.get("code_verifier") or "",
                    client, kw.get("redirect_uri") or "")
                # Bind the token to the resource the code was requested for,
                # falling back to whatever the client asks for now.
                audience = grant.resource or kw.get("resource") or ""
                issued = Token.issue(client, grant.user_id, grant.scope,
                                     audience, grant=grant)
            elif grant_type == "refresh_token":
                issued = Token.refresh(kw.get("refresh_token") or "", client)
            else:
                return _oauth_error("unsupported_grant_type")
        except ValidationError as exc:
            return _oauth_error(str(exc) or "invalid_grant", status=400)

        return _json(issued)

    @http.route("/mcp/oauth/revoke", type="http", auth="public",
                methods=["POST", "OPTIONS"], csrf=False, cors="*",
                save_session=False)
    def revoke(self, **kw):
        """RFC 7009. Always answers 200 — telling a caller that a token did not
        exist is itself an oracle."""
        raw = kw.get("token") or ""
        Token = request.env["mn.mcp.oauth.token"].sudo()
        from ..models.mcp_oauth import _hash
        found = Token.search(["|", ("access_hash", "=", _hash(raw)),
                              ("refresh_hash", "=", _hash(raw))], limit=1)
        if found:
            found.revoked = True
        return _json({})

    # ==================================================================
    # Registration (deprecated, kept for clients that only speak DCR)
    # ==================================================================
    @http.route("/mcp/oauth/register", type="http", auth="public",
                methods=["POST", "OPTIONS"], csrf=False, cors="*",
                save_session=False)
    def register(self, **kw):
        enabled = request.env["ir.config_parameter"].sudo().get_param(
            "mn_mcp.oauth_allow_dcr", "True") in ("True", "true", "1")
        if not enabled:
            return _oauth_error("invalid_request",
                                "Dynamic registration is disabled; use a "
                                "Client ID Metadata Document", status=403)
        try:
            doc = json.loads(request.httprequest.data or b"{}")
        except ValueError:
            return _oauth_error("invalid_request", "Malformed JSON")

        redirects = [u for u in (doc.get("redirect_uris") or []) if isinstance(u, str)]
        if not redirects:
            return _oauth_error("invalid_redirect_uri", "redirect_uris is required")

        client_id = "mcp-" + secrets.token_urlsafe(16)
        client = request.env["mn.mcp.oauth.client"].sudo().create({
            "name": doc.get("client_name") or client_id,
            "client_id": client_id,
            "redirect_uris": "\n".join(redirects),
            "source": "dcr",
            "metadata_json": json.dumps(doc, indent=2)[:20000],
        })
        return _json({
            "client_id": client.client_id,
            "client_id_issued_at": int(client.create_date.timestamp()),
            "redirect_uris": redirects,
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
        }, status=201)
