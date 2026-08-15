/** @odoo-module **/
import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class McpDashboard extends Component {
    static template = "mn_mcp_server.Dashboard";
    setup() {
        this.orm = useService("orm");
        this.state = useState({ loading: true, data: null });
        this.canvas = useRef("trend");
        this._timer = null;
        onMounted(async () => {
            await this.refresh();
            this._timer = setInterval(() => this.refresh(), 8000);
        });
        onWillUnmount(() => { if (this._timer) clearInterval(this._timer); });
    }
    async refresh() {
        const d = await this.orm.call("mn.mcp.dashboard", "get_data", []);
        this.state.data = d;
        this.state.loading = false;
        setTimeout(() => this._chart(d.trend), 60);
    }
    _chart(trend) {
        if (typeof window.Chart === "undefined" || !this.canvas.el) return;
        if (this._c) this._c.destroy();
        this._c = new window.Chart(this.canvas.el, {
            type: "line",
            data: {
                labels: trend.map(t => t.hour),
                datasets: [{
                    label: "Calls",
                    data: trend.map(t => t.count),
                    borderColor: "#8B5CF6",
                    backgroundColor: "rgba(139,92,246,0.18)",
                    tension: 0.4, fill: true,
                }],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { labels: { color: "#FAFAFA" } } },
                scales: {
                    x: { ticks: { color: "#A1A1AA" }, grid: { color: "#1F1F22" } },
                    y: { ticks: { color: "#A78BFA" }, grid: { color: "#1F1F22" } },
                },
            },
        });
    }
}
registry.category("actions").add("mn_mcp_dashboard", McpDashboard);
