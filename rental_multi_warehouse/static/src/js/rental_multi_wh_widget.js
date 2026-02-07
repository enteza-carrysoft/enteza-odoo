/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart, onWillUpdateProps } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * Widget que muestra la disponibilidad multi-almacén de una línea
 * de alquiler. Reemplaza el campo rental_availability_json por una
 * visualización interactiva con semáforo y detalle expandible.
 */
class RentalMultiWhWidget extends Component {
    static template = "rental_multi_warehouse.RentalMultiWhWidget";
    static props = { ...standardFieldProps };

    setup() {
        this.state = useState({
            expanded: false,
            data: null,
        });
    }

    get availabilityData() {
        const raw = this.props.record.data.rental_availability_json;
        if (!raw || raw === '{}') return null;
        try {
            return JSON.parse(raw);
        } catch {
            return null;
        }
    }

    get status() {
        return this.availabilityData?.status || false;
    }

    get statusConfig() {
        const configs = {
            ok: {
                color: "text-success",
                bgClass: "bg-success-subtle",
                icon: "fa-check-circle",
                label: "Disponible en almacén preferente",
            },
            transfer_needed: {
                color: "text-info",
                bgClass: "bg-info-subtle",
                icon: "fa-truck",
                label: "Requiere traslado inter-almacén",
            },
            deficit: {
                color: "text-danger",
                bgClass: "bg-danger-subtle",
                icon: "fa-times-circle",
                label: "Stock insuficiente",
            },
        };
        return configs[this.status] || configs.ok;
    }

    get totalAvailable() {
        return this.availabilityData?.total_available || 0;
    }

    get deficit() {
        return this.availabilityData?.deficit || 0;
    }

    get assignments() {
        return this.availabilityData?.assignments || [];
    }

    get qtyNeeded() {
        return this.availabilityData?.qty_needed || 0;
    }

    toggleExpanded() {
        this.state.expanded = !this.state.expanded;
    }
}

registry.category("fields").add("rental_multi_wh_availability", {
    component: RentalMultiWhWidget,
});
