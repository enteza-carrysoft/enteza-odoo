/** @odoo-module **/

import { registry } from "@web/core/registry";

const COMPANY_COLORS = {
    0: "transparent",
    1: "#F06050",
    2: "#F4A460",
    3: "#F7CD1F",
    4: "#6CC1ED",
    5: "#814968",
    6: "#EB7E7F",
    7: "#2C8397",
    8: "#475577",
    9: "#D6145F",
    10: "#30C381",
    11: "#9365B8",
};

function ensureStrip() {
    let strip = document.querySelector(".o_company_top_color_strip");
    if (!strip) {
        strip = document.createElement("div");
        strip.className = "o_company_top_color_strip";
        strip.setAttribute("aria-hidden", "true");
        document.body.appendChild(strip);
    }
    return strip;
}

function applyColor(companyName, colorIndex) {
    const strip = ensureStrip();
    const color = COMPANY_COLORS[colorIndex] || "transparent";
    strip.style.setProperty("--company-top-color", color);
    strip.title = companyName ? `Empresa activa: ${companyName}` : "";
}

export const companyTopColorService = {
    dependencies: ["orm", "user"],

    async start(env, { orm, user }) {
        const ids = user.context.allowed_company_ids || [];
        const companyId = ids[0];

        if (!companyId) {
            applyColor("", 0);
            return {};
        }

        try {
            const companies = await orm.read(
                "res.company",
                [companyId],
                ["name", "top_bar_color"]
            );
            const company = companies[0];
            if (company) {
                applyColor(company.name, company.top_bar_color || 0);
            }
        } catch (error) {
            console.warn("Company Top Color: could not load company color.", error);
            applyColor("", 0);
        }

        return {};
    },
};

registry.category("services").add("company_top_color", companyTopColorService);
