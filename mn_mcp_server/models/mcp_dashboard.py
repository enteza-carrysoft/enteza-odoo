# -*- coding: utf-8 -*-
"""Live monitor dashboard — feeds the OWL view."""
from datetime import timedelta
from odoo import api, fields, models


class McpDashboard(models.TransientModel):
    _name = "mn.mcp.dashboard"
    _description = "MCP Live Monitor"

    @api.model
    def get_data(self):
        Audit = self.env["mn.mcp.audit"].sudo()
        Key = self.env["mn.mcp.api_key"].sudo()
        now = fields.Datetime.now()
        today = fields.Date.today()
        today_s = f"{today} 00:00:00"
        today_e = f"{today} 23:59:59"

        # KPIs
        calls_today = Audit.search_count([("create_date", ">=", today_s), ("create_date", "<=", today_e)])
        ok_today = Audit.search_count([
            ("create_date", ">=", today_s), ("create_date", "<=", today_e),
            ("status", "=", "ok"),
        ])
        err_today = calls_today - ok_today
        success_pct = (ok_today / calls_today * 100) if calls_today else 100
        avg_latency = 0
        latencies = Audit.search([
            ("create_date", ">=", today_s), ("create_date", "<=", today_e),
            ("status", "=", "ok"),
        ], limit=500).mapped("latency_ms")
        if latencies:
            avg_latency = sum(latencies) // len(latencies)
        active_keys = Key.search_count([("state", "=", "active")])

        # Per-hour trend (last 24h)
        trend = []
        for i in range(23, -1, -1):
            h_start = now - timedelta(hours=i + 1)
            h_end = now - timedelta(hours=i)
            c = Audit.search_count([
                ("create_date", ">=", h_start),
                ("create_date", "<", h_end),
            ])
            trend.append({"hour": h_start.strftime("%H:00"), "count": c})

        # Top tools
        tools = {}
        recent = Audit.search([("create_date", ">=", today_s),
                                ("create_date", "<=", today_e)], limit=2000)
        for a in recent:
            m = a.method or "?"
            if m == "tools/call":
                # Unfortunately we don't store the tool name; use model_target as proxy
                m = f"call/{a.model_target or '?'}"
            tools[m] = tools.get(m, 0) + 1
        top_tools = sorted(tools.items(), key=lambda x: -x[1])[:8]
        top_tools = [{"name": k, "count": v} for k, v in top_tools]

        # Top keys
        keys = {}
        for a in recent:
            if a.api_key_id:
                keys[a.api_key_id.name] = keys.get(a.api_key_id.name, 0) + 1
        top_keys = sorted(keys.items(), key=lambda x: -x[1])[:5]
        top_keys = [{"name": k, "count": v} for k, v in top_keys]

        # Recent events
        last20 = Audit.search([], limit=20, order="create_date desc")
        recent_events = [{
            "id": a.id,
            "when": a.create_date.strftime("%H:%M:%S") if a.create_date else "",
            "method": a.method,
            "target": a.model_target or "",
            "key": a.api_key_id.name if a.api_key_id else "—",
            "latency": a.latency_ms,
            "status": a.status,
        } for a in last20]

        return {
            "calls_today": calls_today,
            "success_pct": round(success_pct, 1),
            "errors_today": err_today,
            "avg_latency": avg_latency,
            "active_keys": active_keys,
            "trend": trend,
            "top_tools": top_tools,
            "top_keys": top_keys,
            "recent_events": recent_events,
            "now": now.strftime("%H:%M:%S"),
        }
