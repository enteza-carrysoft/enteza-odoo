# -*- coding: utf-8 -*-
"""Protocol-revision tests.

The 2026-07-28 revision is a breaking redesign, so the risk here is not that
new clients fail — it is that fixing them quietly breaks the 2024-era clients
already installed against this server. Every test that asserts a new field is
present is paired with one asserting it is *absent* for an older revision.
"""
import json

from odoo.tests import HttpCase, tagged

from ..controllers import protocol as P


@tagged("post_install", "-at_install")
class TestMcpProtocol(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Key = cls.env["mn.mcp.api_key"]
        vals = {"name": "protocol-test", "user_id": cls.env.ref("base.user_admin").id}
        if "allow_all_models" in Key._fields:
            vals["allow_all_models"] = True
        for perm in ("perm_read", "perm_write", "perm_create", "perm_unlink"):
            if perm in Key._fields:
                vals[perm] = True
        cls.key = Key.create(vals)
        cls.token = cls.key.token

    # ------------------------------------------------------------------
    def _post(self, payload, headers=None, token=True):
        hdr = {"Content-Type": "application/json"}
        if token:
            hdr["Authorization"] = f"Bearer {self.token}"
        hdr.update(headers or {})
        response = self.url_open("/mcp", data=json.dumps(payload), headers=hdr)
        return response

    def _call(self, method, revision=None, params=None, headers=None, token=True):
        params = dict(params or {})
        if revision:
            params.setdefault("_meta", {})[P.META_PROTOCOL] = revision
        body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        return self._post(body, headers=headers, token=token).json()

    # ==================================================================
    # Pure functions
    # ==================================================================
    def test_rank_orders_newest_first(self):
        self.assertEqual(P.rank("2026-07-28"), 0)
        self.assertGreater(P.rank("2024-11-05"), P.rank("2026-07-28"))

    def test_unknown_revision_is_not_ranked(self):
        """A future date must read as unknown, not as 'newer than everything'."""
        self.assertEqual(P.rank("2099-01-01"), -1)
        self.assertFalse(P.is_at_least("2099-01-01", P.STATELESS_FROM))

    def test_is_at_least(self):
        self.assertTrue(P.is_at_least("2026-07-28", "2024-11-05"))
        self.assertFalse(P.is_at_least("2024-11-05", "2026-07-28"))

    def test_negotiate_prefers_meta_over_header(self):
        body = {"params": {"_meta": {P.META_PROTOCOL: "2026-07-28"}}}
        rev, bad = P.negotiate(body, {"MCP-Protocol-Version": "2024-11-05"})
        self.assertEqual(rev, "2026-07-28")
        self.assertFalse(bad)

    def test_negotiate_falls_back_to_oldest(self):
        """An unversioned request is an old client, so assume the old shape."""
        rev, bad = P.negotiate({}, {})
        self.assertEqual(rev, P.LEGACY_REVISION)
        self.assertFalse(bad)

    def test_negotiate_flags_unknown_revision(self):
        body = {"params": {"_meta": {P.META_PROTOCOL: "2099-01-01"}}}
        _rev, bad = P.negotiate(body, {})
        self.assertTrue(bad)

    def test_decorate_only_touches_new_revisions(self):
        new = P.decorate_result({"tools": []}, "2026-07-28", "tools/list", "1.0")
        self.assertEqual(new["resultType"], "complete")
        self.assertEqual(new["ttlMs"], P.LIST_TTL_MS)
        self.assertEqual(new["cacheScope"], "private")

        old = P.decorate_result({"tools": []}, "2024-11-05", "tools/list", "1.0")
        self.assertNotIn("resultType", old)
        self.assertNotIn("ttlMs", old)

    def test_decorate_does_not_cache_tool_calls(self):
        """Only list/read results are cacheable — a tools/call result is not."""
        out = P.decorate_result({"content": []}, "2026-07-28", "tools/call", "1.0")
        self.assertEqual(out["resultType"], "complete")
        self.assertNotIn("ttlMs", out)

    # ==================================================================
    # HTTP surface
    # ==================================================================
    def test_discover_is_unauthenticated(self):
        """A client must be able to pick a revision before it has credentials."""
        body = self._call("server/discover", token=False)
        result = body["result"]
        self.assertEqual(result["protocolVersions"], list(P.SUPPORTED_REVISIONS))
        self.assertIn("serverInfo", result)

    def test_stateless_call_without_initialize(self):
        """2026-07-28 has no handshake: tools/list must work on its own."""
        body = self._call("tools/list", revision="2026-07-28")
        result = body["result"]
        self.assertEqual(result["resultType"], "complete")
        self.assertEqual(result["cacheScope"], "private")
        self.assertIn(P.META_SERVER_INFO, result["_meta"])
        self.assertTrue(result["tools"])

    def test_legacy_client_gets_no_new_fields(self):
        body = self._call("tools/list")
        result = body["result"]
        self.assertNotIn("resultType", result)
        self.assertNotIn("ttlMs", result)

    def test_tools_are_deterministically_ordered(self):
        names = [t["name"] for t in self._call("tools/list")["result"]["tools"]]
        self.assertEqual(names, sorted(names))

    def test_destructive_tool_is_annotated(self):
        tools = {t["name"]: t for t in self._call("tools/list")["result"]["tools"]}
        self.assertTrue(tools["odoo_unlink"]["annotations"]["destructiveHint"])
        self.assertTrue(tools["odoo_search"]["annotations"]["readOnlyHint"])
        self.assertFalse(tools["odoo_create"]["annotations"]["readOnlyHint"])

    def test_unknown_revision_is_rejected(self):
        body = self._call("tools/list", revision="2099-01-01")
        self.assertEqual(body["error"]["code"], -32022)
        self.assertIn("supported", body["error"]["data"])

    def test_header_contradicting_body_is_rejected(self):
        body = self._call("tools/list", revision="2026-07-28",
                          headers={"Mcp-Method": "tools/call"})
        self.assertEqual(body["error"]["code"], -32020)

    def test_absent_routing_headers_are_tolerated(self):
        """Missing headers must not break otherwise-compliant clients."""
        body = self._call("tools/list", revision="2026-07-28")
        self.assertIn("result", body)

    def test_ping_removed_on_new_revision_only(self):
        self.assertEqual(
            self._call("ping", revision="2026-07-28")["error"]["code"], -32601)
        self.assertIn("result", self._call("ping"))

    def test_initialize_still_serves_old_clients(self):
        body = self._call("initialize", params={"protocolVersion": "2024-11-05"})
        result = body["result"]
        self.assertEqual(result["protocolVersion"], "2024-11-05")
        self.assertIn("logging", result["capabilities"])

    def test_initialize_echoes_a_new_revision_when_asked(self):
        body = self._call("initialize", revision="2026-07-28")
        self.assertEqual(body["result"]["protocolVersion"], "2026-07-28")

    def test_tool_call_still_works(self):
        body = self._call("tools/call", revision="2026-07-28", params={
            "name": "odoo_search_count", "arguments": {"model": "res.partner"},
        })
        self.assertEqual(body["result"]["resultType"], "complete")
        self.assertTrue(body["result"]["content"])

    def test_bad_token_is_rejected(self):
        hdr = {"Content-Type": "application/json", "Authorization": "Bearer nope"}
        response = self.url_open("/mcp", data=json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}), headers=hdr)
        self.assertEqual(response.json()["error"]["code"], P.ERR_AUTH)

    def test_notification_gets_no_body(self):
        """A JSON-RPC notification carries no id and must not be answered."""
        hdr = {"Content-Type": "application/json",
               "Authorization": f"Bearer {self.token}"}
        response = self.url_open("/mcp", data=json.dumps(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}), headers=hdr)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.text, "")
