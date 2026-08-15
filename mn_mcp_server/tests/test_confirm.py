# -*- coding: utf-8 -*-
"""Confirm-before-write tests.

The interesting cases are not "does the prompt appear" — they are the ways a
model or a malicious client could get past it: replaying a confirmation onto a
larger action, forging the state, or answering "no" and having it run anyway.
"""
import json

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestConfirm(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Key = cls.env["mn.mcp.api_key"]
        vals = {"name": "confirm-test", "user_id": cls.env.ref("base.user_admin").id}
        if "allow_all_models" in Key._fields:
            vals["allow_all_models"] = True
        for perm in ("perm_read", "perm_write", "perm_create", "perm_unlink"):
            if perm in Key._fields:
                vals[perm] = True
        cls.key = Key.create(vals)
        cls.token = cls.key.token
        cls.meta = {
            "io.modelcontextprotocol/protocolVersion": "2026-07-28",
            "io.modelcontextprotocol/clientCapabilities": {"elicitation": {}},
        }

    # ------------------------------------------------------------------
    def _call(self, name, arguments, extra=None, caps=True):
        meta = dict(self.meta)
        if not caps:
            meta.pop("io.modelcontextprotocol/clientCapabilities")
        params = {"name": name, "arguments": arguments, "_meta": meta}
        params.update(extra or {})
        response = self.url_open("/mcp", data=json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params,
        }), headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.token}"})
        return response.json().get("result", response.json())

    def _partner(self, name="Confirm Test"):
        created = self._call("odoo_create",
                             {"model": "res.partner", "values": {"name": name}})
        return json.loads(created["content"][0]["text"])["id"]

    def _accept(self, state):
        return {"requestState": state,
                "inputResponses": {"mcp_confirm": {"action": "accept",
                                                   "content": {"confirm": True}}}}

    # ==================================================================
    def test_delete_is_stopped_until_confirmed(self):
        pid = self._partner()
        first = self._call("odoo_unlink", {"model": "res.partner", "ids": [pid]})
        self.assertEqual(first["resultType"], "input_required")
        self.assertTrue(first["requestState"])
        self.assertIn("mcp_confirm", first["inputRequests"])
        self.assertTrue(
            self.env["res.partner"].browse(pid).exists(),
            "the record must still be there while confirmation is pending")

    def test_confirmed_delete_runs(self):
        pid = self._partner()
        first = self._call("odoo_unlink", {"model": "res.partner", "ids": [pid]})
        done = self._call("odoo_unlink", {"model": "res.partner", "ids": [pid]},
                          extra=self._accept(first["requestState"]))
        self.assertEqual(done["resultType"], "complete")
        self.assertFalse(self.env["res.partner"].browse(pid).exists())

    def test_declining_does_not_run(self):
        pid = self._partner()
        first = self._call("odoo_unlink", {"model": "res.partner", "ids": [pid]})
        again = self._call("odoo_unlink", {"model": "res.partner", "ids": [pid]},
                           extra={"requestState": first["requestState"],
                                  "inputResponses": {"mcp_confirm": {"action": "decline"}}})
        self.assertEqual(again["resultType"], "input_required")
        self.assertTrue(self.env["res.partner"].browse(pid).exists())

    def test_answering_false_does_not_run(self):
        """An accepted form that says confirm=false is still a no."""
        pid = self._partner()
        first = self._call("odoo_unlink", {"model": "res.partner", "ids": [pid]})
        again = self._call(
            "odoo_unlink", {"model": "res.partner", "ids": [pid]},
            extra={"requestState": first["requestState"],
                   "inputResponses": {"mcp_confirm": {"action": "accept",
                                                      "content": {"confirm": False}}}})
        self.assertEqual(again["resultType"], "input_required")
        self.assertTrue(self.env["res.partner"].browse(pid).exists())

    def test_state_cannot_be_replayed_onto_a_bigger_action(self):
        """Approving 'delete 1' must not authorise 'delete 2'.

        This is the attack the argument digest exists to stop.
        """
        one = self._partner("Replay A")
        two = self._partner("Replay B")
        small = self._call("odoo_unlink", {"model": "res.partner", "ids": [one]})
        bigger = self._call("odoo_unlink", {"model": "res.partner", "ids": [one, two]},
                            extra=self._accept(small["requestState"]))
        self.assertEqual(bigger["resultType"], "input_required")
        self.assertTrue(self.env["res.partner"].browse(two).exists())

    def test_forged_state_is_rejected(self):
        pid = self._partner()
        forged = self._call("odoo_unlink", {"model": "res.partner", "ids": [pid]},
                            extra=self._accept("bm90LWEtcmVhbC1zdGF0ZQ=="))
        self.assertEqual(forged["resultType"], "input_required")
        self.assertTrue(self.env["res.partner"].browse(pid).exists())

    def test_client_without_elicitation_is_told_how_to_proceed(self):
        pid = self._partner()
        first = self._call("odoo_unlink", {"model": "res.partner", "ids": [pid]},
                           caps=False)
        self.assertEqual(first["resultType"], "input_required")
        self.assertNotIn("inputRequests", first,
                         "must not send an elicitation the client cannot answer")
        self.assertIn("confirm", first["content"][0]["text"])

    def test_confirm_argument_works_for_old_clients(self):
        pid = self._partner()
        done = self._call("odoo_unlink",
                          {"model": "res.partner", "ids": [pid], "confirm": True})
        self.assertEqual(done["resultType"], "complete")
        self.assertFalse(self.env["res.partner"].browse(pid).exists())

    def test_confirm_never_reaches_the_orm(self):
        """`confirm` is ours, not a field — it must be stripped before write."""
        pid = self._partner()
        done = self._call("odoo_write", {
            "model": "res.partner", "ids": [pid],
            "values": {"comment": "ok"}, "confirm": True})
        self.assertEqual(done["resultType"], "complete")
        self.assertEqual(self.env["res.partner"].browse(pid).comment, "<p>ok</p>")

    def test_reads_are_never_gated(self):
        result = self._call("odoo_search_count", {"model": "res.partner"})
        self.assertEqual(result["resultType"], "complete")

    def test_small_write_is_not_gated(self):
        pid = self._partner()
        result = self._call("odoo_write", {"model": "res.partner", "ids": [pid],
                                           "values": {"comment": "small"}})
        self.assertEqual(result["resultType"], "complete")

    def test_bulk_write_over_threshold_is_gated(self):
        self.env["ir.config_parameter"].sudo().set_param("mn_mcp.confirm_write_over", "2")
        ids = [self._partner(f"Bulk {i}") for i in range(4)]
        result = self._call("odoo_write", {"model": "res.partner", "ids": ids,
                                           "values": {"comment": "bulk"}})
        self.assertEqual(result["resultType"], "input_required")

    def test_guard_can_be_switched_off(self):
        self.env["ir.config_parameter"].sudo().set_param("mn_mcp.confirm_enabled", "False")
        pid = self._partner()
        result = self._call("odoo_unlink", {"model": "res.partner", "ids": [pid]})
        self.assertEqual(result["resultType"], "complete")
        self.env["ir.config_parameter"].sudo().set_param("mn_mcp.confirm_enabled", "True")

    def test_guarded_tools_advertise_the_confirm_argument(self):
        response = self.url_open("/mcp", data=json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/list",
            "params": {"_meta": self.meta},
        }), headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.token}"})
        tools = {t["name"]: t for t in response.json()["result"]["tools"]}
        self.assertIn("confirm", tools["odoo_unlink"]["inputSchema"]["properties"])
        self.assertNotIn("confirm", tools["odoo_search"]["inputSchema"]["properties"])
