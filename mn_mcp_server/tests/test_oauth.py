# -*- coding: utf-8 -*-
"""OAuth 2.1 tests.

These concentrate on the properties that make the difference between an OAuth
server and an open door: PKCE binding, single-use codes, exact redirect-URI
matching, audience binding, and refresh-token rotation. Each of those has a
well-known exploit if it is missing, and none of them is visible in a happy-path
demo — which is exactly why they need tests.
"""
import base64
import hashlib
import json
import secrets
from urllib.parse import parse_qs, urlparse

from odoo.exceptions import ValidationError
from odoo.tests import HttpCase, TransactionCase, tagged

from ..models import mcp_oauth as O


def pkce():
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


@tagged("post_install", "-at_install")
class TestOauthModels(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.client = cls.env["mn.mcp.oauth.client"].create({
            "name": "Test Client",
            "client_id": "test-client",
            "redirect_uris": "https://app.example.com/cb\nhttps://app.example.com/cb2",
        })
        cls.user = cls.env.ref("base.user_admin")

    # ------------------------------------------------------------------
    def test_redirect_uri_must_match_exactly(self):
        """Prefix matching is the classic open-redirect hole."""
        self.assertTrue(self.client.check_redirect("https://app.example.com/cb"))
        self.assertFalse(self.client.check_redirect("https://app.example.com/cb/evil"))
        self.assertFalse(self.client.check_redirect("https://app.example.com"))
        self.assertFalse(self.client.check_redirect("https://evil.example.com/cb"))

    def test_scope_maps_to_permissions(self):
        token = self.env["mn.mcp.oauth.token"]
        key = token._provision_key(self.user, self.client, "odoo:read")
        self.assertTrue(key.perm_read)
        self.assertFalse(key.perm_write)
        self.assertFalse(key.perm_unlink)

        key = token._provision_key(self.user, self.client, "odoo:write")
        self.assertTrue(key.perm_write)
        self.assertTrue(key.perm_create)
        self.assertFalse(key.perm_unlink)

        key = token._provision_key(self.user, self.client, "odoo:admin")
        self.assertTrue(key.perm_unlink)

    def test_code_is_single_use(self):
        verifier, challenge = pkce()
        Grant = self.env["mn.mcp.oauth.grant"]
        code = Grant.issue(self.client, self.user, "https://app.example.com/cb",
                           challenge, "odoo:read", "https://x/mcp")
        Grant.consume(code, verifier, self.client, "https://app.example.com/cb")
        with self.assertRaises(ValidationError):
            Grant.consume(code, verifier, self.client, "https://app.example.com/cb")

    def test_replayed_code_revokes_what_it_issued(self):
        """A reused code means the code may have leaked, so burn its tokens."""
        verifier, challenge = pkce()
        Grant = self.env["mn.mcp.oauth.grant"]
        Token = self.env["mn.mcp.oauth.token"]
        code = Grant.issue(self.client, self.user, "https://app.example.com/cb",
                           challenge, "odoo:read", "https://x/mcp")
        grant = Grant.consume(code, verifier, self.client, "https://app.example.com/cb")
        issued = Token.issue(self.client, self.user, "odoo:read",
                             "https://x/mcp", grant=grant)
        self.assertTrue(Token.authenticate(issued["access_token"]))

        # NOT assertRaises here: Odoo wraps it in a savepoint and rolls back
        # when the exception fires, which would discard the very revocation
        # this test exists to check. Catch it by hand instead.
        raised = False
        try:
            Grant.consume(code, verifier, self.client, "https://app.example.com/cb")
        except ValidationError:
            raised = True
        self.assertTrue(raised, "a replayed code must be refused")
        self.assertFalse(Token.authenticate(issued["access_token"]),
                         "a replayed code must also revoke what it issued")

    def test_wrong_pkce_verifier_is_rejected(self):
        _verifier, challenge = pkce()
        Grant = self.env["mn.mcp.oauth.grant"]
        code = Grant.issue(self.client, self.user, "https://app.example.com/cb",
                           challenge, "odoo:read", "https://x/mcp")
        with self.assertRaises(ValidationError):
            Grant.consume(code, "not-the-verifier", self.client,
                          "https://app.example.com/cb")

    def test_code_bound_to_its_redirect_uri(self):
        verifier, challenge = pkce()
        Grant = self.env["mn.mcp.oauth.grant"]
        code = Grant.issue(self.client, self.user, "https://app.example.com/cb",
                           challenge, "odoo:read", "https://x/mcp")
        with self.assertRaises(ValidationError):
            Grant.consume(code, verifier, self.client, "https://app.example.com/cb2")

    def test_token_is_audience_bound(self):
        """A token minted for another MCP server must not work here.

        This is the confused-deputy attack RFC 8707 exists to prevent.
        """
        Token = self.env["mn.mcp.oauth.token"]
        issued = Token.issue(self.client, self.user, "odoo:read",
                             "https://ours.example.com/mcp")
        self.assertTrue(Token.authenticate(
            issued["access_token"], audience="https://ours.example.com/mcp"))
        self.assertFalse(Token.authenticate(
            issued["access_token"], audience="https://someone-else.example.com/mcp"))

    def test_audience_tolerates_trailing_slash(self):
        Token = self.env["mn.mcp.oauth.token"]
        issued = Token.issue(self.client, self.user, "odoo:read",
                             "https://ours.example.com/mcp")
        self.assertTrue(Token.authenticate(
            issued["access_token"], audience="https://ours.example.com/mcp/"))

    def test_refresh_rotates_and_old_one_dies(self):
        Token = self.env["mn.mcp.oauth.token"]
        first = Token.issue(self.client, self.user, "odoo:read", "https://x/mcp")
        second = Token.refresh(first["refresh_token"], self.client)
        self.assertNotEqual(first["access_token"], second["access_token"])
        with self.assertRaises(ValidationError):
            Token.refresh(first["refresh_token"], self.client)

    def test_refresh_bound_to_its_client(self):
        other = self.env["mn.mcp.oauth.client"].create({
            "name": "Other", "client_id": "other-client",
            "redirect_uris": "https://other.example.com/cb",
        })
        Token = self.env["mn.mcp.oauth.token"]
        issued = Token.issue(self.client, self.user, "odoo:read", "https://x/mcp")
        with self.assertRaises(ValidationError):
            Token.refresh(issued["refresh_token"], other)

    def test_revoked_token_stops_working(self):
        Token = self.env["mn.mcp.oauth.token"]
        issued = Token.issue(self.client, self.user, "odoo:read", "https://x/mcp")
        Token.search([]).write({"revoked": True})
        self.assertFalse(Token.authenticate(issued["access_token"]))

    def test_cimd_requires_https(self):
        self.assertFalse(self.env["mn.mcp.oauth.client"].resolve("http://evil.example.com/c"))
        self.assertFalse(self.env["mn.mcp.oauth.client"].resolve("not-a-url-or-known-client"))


@tagged("post_install", "-at_install")
class TestOauthEndpoints(HttpCase):

    def test_protected_resource_metadata(self):
        """RFC 9728 — MCP servers MUST implement this."""
        body = self.url_open("/.well-known/oauth-protected-resource").json()
        self.assertTrue(body["resource"].endswith("/mcp"))
        self.assertTrue(body["authorization_servers"])
        self.assertIn("odoo:read", body["scopes_supported"])
        self.assertEqual(body["bearer_methods_supported"], ["header"])

    def test_authorization_server_metadata(self):
        body = self.url_open("/.well-known/oauth-authorization-server").json()
        self.assertEqual(body["code_challenge_methods_supported"], ["S256"])
        self.assertTrue(body["authorization_response_iss_parameter_supported"])
        self.assertIn("authorization_code", body["grant_types_supported"])
        self.assertIn("refresh_token", body["grant_types_supported"])

    def test_openid_discovery_path_also_served(self):
        """Clients MUST try both discovery paths, so both must answer."""
        self.assertEqual(
            self.url_open("/.well-known/openid-configuration").status_code, 200)

    def test_unauthenticated_mcp_call_challenges(self):
        response = self.url_open("/mcp", data=json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
            headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 401)
        challenge = response.headers.get("WWW-Authenticate", "")
        self.assertIn("resource_metadata=", challenge)
        self.assertIn("scope=", challenge)

    def test_authorize_requires_pkce_s256(self):
        response = self.url_open(
            "/mcp/oauth/authorize?response_type=code&client_id=x"
            "&redirect_uri=https://a/cb")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_request")

    def test_authorize_rejects_unknown_client(self):
        _v, challenge = pkce()
        response = self.url_open(
            "/mcp/oauth/authorize?response_type=code&client_id=nope"
            f"&redirect_uri=https://a/cb&code_challenge={challenge}"
            "&code_challenge_method=S256")
        self.assertEqual(response.json()["error"], "invalid_client")

    def test_authorize_rejects_unregistered_redirect(self):
        self.env["mn.mcp.oauth.client"].create({
            "name": "R", "client_id": "redir-test",
            "redirect_uris": "https://good.example.com/cb",
        })
        # HttpCase shares its cursor with the request handler, so no commit is
        # needed — and committing inside a test breaks the rollback.
        _v, challenge = pkce()
        response = self.url_open(
            "/mcp/oauth/authorize?response_type=code&client_id=redir-test"
            f"&redirect_uri=https://evil.example.com/cb&code_challenge={challenge}"
            "&code_challenge_method=S256")
        self.assertEqual(response.json()["error"], "invalid_request")

    def test_token_endpoint_rejects_unknown_grant_type(self):
        response = self.url_open("/mcp/oauth/token", data={
            "grant_type": "password", "client_id": "x"})
        self.assertIn(response.json()["error"],
                      ("invalid_client", "unsupported_grant_type"))

    def test_dynamic_registration_needs_redirect_uris(self):
        response = self.url_open("/mcp/oauth/register", data=json.dumps({}),
                                 headers={"Content-Type": "application/json"})
        self.assertEqual(response.json()["error"], "invalid_redirect_uri")
