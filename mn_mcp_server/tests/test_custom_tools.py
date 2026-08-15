# -*- coding: utf-8 -*-
"""Custom tool tests.

Two things matter here. First that a tool defined in the database behaves like
a built-in — appears in tools/list, runs, respects the key's scope. Second, and
more important, that a *parameter* cannot escape the domain it is substituted
into: that would let anyone who can talk to the AI read any row of the model.
"""
import json

from odoo.exceptions import ValidationError
from odoo.tests import HttpCase, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCustomToolModel(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_model = cls.env["ir.model"]._get_id("res.partner")

    def _tool(self, **overrides):
        vals = {
            "name": "find_partner",
            "description": "Find a partner by name.",
            "kind": "query",
            "model_id": self.partner_model,
            "domain": '[("name","ilike",{term})]',
            "param_ids": [(0, 0, {"name": "term", "param_type": "string"})],
        }
        vals.update(overrides)
        return self.env["mn.mcp.tool"].create(vals)

    # ------------------------------------------------------------------
    def test_name_must_be_client_safe(self):
        """Clients reject dots and spaces, so we reject them at the source."""
        for bad in ("has.dot", "has space", "", "x" * 65):
            with self.assertRaises(ValidationError):
                self._tool(name=bad)

    def test_odoo_prefix_is_reserved(self):
        with self.assertRaises(ValidationError):
            self._tool(name="odoo_search")

    def test_broken_domain_is_caught_on_save(self):
        with self.assertRaises(ValidationError):
            self._tool(domain='[("name","ilike"')

    def test_domain_must_be_a_list(self):
        with self.assertRaises(ValidationError):
            self._tool(domain='{"not": "a list"}')

    def test_group_needs_a_groupby(self):
        with self.assertRaises(ValidationError):
            self._tool(kind="group", groupby=False)

    def test_action_needs_an_action(self):
        with self.assertRaises(ValidationError):
            self._tool(kind="action")

    # ------------------------------------------------------------------
    def test_parameter_cannot_escape_the_domain(self):
        """The whole security story for custom tools.

        A string parameter is inserted as a Python literal, so a value that
        looks like domain syntax stays a search term instead of becoming one.
        """
        tool = self._tool()
        hostile = 'x"),("id",">",0),("id",">",'
        domain = tool._resolve_domain({"term": hostile})
        self.assertEqual(len(domain), 1, "the domain must still have one clause")
        self.assertEqual(domain[0][2], hostile,
                         "the payload must survive as a plain search term")

    def test_missing_parameter_falls_back_to_default(self):
        tool = self._tool(
            domain='[("name","ilike",{term})]',
            param_ids=[(0, 0, {"name": "term", "param_type": "string",
                               "default_value": "fallback"})])
        self.assertEqual(tool._resolve_domain({})[0][2], "fallback")

    def test_date_default_today(self):
        tool = self._tool(
            domain='[("create_date",">",{since})]',
            param_ids=[(0, 0, {"name": "since", "param_type": "date",
                               "default_value": "today"})])
        value = tool._resolve_domain({})[0][2]
        self.assertRegex(value, r"^\d{4}-\d{2}-\d{2}$")

    def test_numeric_parameter_is_cast(self):
        tool = self._tool(
            domain='[("id","=",{pid})]',
            param_ids=[(0, 0, {"name": "pid", "param_type": "integer"})])
        self.assertEqual(tool._resolve_domain({"pid": "42"})[0][2], 42)

    def test_bad_numeric_parameter_is_refused(self):
        tool = self._tool(
            domain='[("id","=",{pid})]',
            param_ids=[(0, 0, {"name": "pid", "param_type": "integer"})])
        with self.assertRaises(ValidationError):
            tool._resolve_domain({"pid": "not-a-number"})

    def test_unknown_placeholder_is_reported(self):
        tool = self._tool(domain='[("name","=",{nope})]', param_ids=[])
        with self.assertRaises(ValidationError):
            tool._resolve_domain({})

    def test_schema_marks_reads_as_read_only(self):
        self.assertTrue(self._tool().to_schema()["annotations"]["readOnlyHint"])
        action = self.env["ir.actions.server"].create({
            "name": "noop", "model_id": self.partner_model, "state": "code",
            "code": "pass",
        })
        tool = self._tool(name="run_it", kind="action", action_id=action.id)
        self.assertFalse(tool.to_schema()["annotations"]["readOnlyHint"])

    def test_required_parameter_with_a_default_is_not_required(self):
        """If we can fill it in, the model should not be forced to."""
        tool = self._tool(param_ids=[(0, 0, {
            "name": "term", "param_type": "string",
            "required": True, "default_value": "x"})])
        self.assertEqual(tool.to_schema()["inputSchema"]["required"], [])


@tagged("post_install", "-at_install")
class TestCustomToolEndpoint(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Key = cls.env["mn.mcp.api_key"]
        vals = {"name": "tool-test", "user_id": cls.env.ref("base.user_admin").id}
        if "allow_all_models" in Key._fields:
            vals["allow_all_models"] = True
        vals["perm_read"] = True
        cls.key = Key.create(vals)
        cls.token = cls.key.token
        cls.env["mn.mcp.tool"].create({
            "name": "endpoint_find_partner",
            "description": "Find a partner by name.",
            "kind": "query",
            "model_id": cls.env["ir.model"]._get_id("res.partner"),
            "domain": '[("name","ilike",{term})]',
            "field_names": "name",
            "limit": 3,
            "param_ids": [(0, 0, {"name": "term", "param_type": "string",
                                  "required": True})],
        })

    def _rpc(self, method, params=None):
        return self.url_open("/mcp", data=json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": method, "params": params or {},
        }), headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.token}"}).json()

    def test_custom_tool_is_listed_and_sorted(self):
        tools = self._rpc("tools/list")["result"]["tools"]
        names = [t["name"] for t in tools]
        self.assertIn("endpoint_find_partner", names)
        self.assertEqual(names, sorted(names))

    def test_custom_tool_runs(self):
        result = self._rpc("tools/call", {
            "name": "endpoint_find_partner", "arguments": {"term": "a"}})["result"]
        payload = json.loads(result["content"][0]["text"])
        self.assertIn("records", payload)
        self.assertLessEqual(payload["count"], 3, "the tool's limit must hold")

    def test_custom_tool_respects_the_key_scope(self):
        """A tool cannot widen what its key is allowed to see."""
        self.key.write({"allow_all_models": False,
                        "allowed_model_ids": [(6, 0, [])]})
        body = self._rpc("tools/call", {
            "name": "endpoint_find_partner", "arguments": {"term": "a"}})
        self.assertIn("error", body)
        self.assertIn("out of scope", body["error"]["message"])
