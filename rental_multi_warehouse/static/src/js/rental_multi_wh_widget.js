/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { usePopover } from "@web/core/popover/popover_hook";

/**
 * Componente popover con la tabla de detalle multi-almacén.
 */
class RentalMultiWhPopover extends Component {
    static template = "rental_multi_warehouse.RentalMultiWhPopover";
    static props = {
        data: { type: Object },
        close: { type: Function, optional: true },
    };
}

/**
 * Widget que muestra la disponibilidad multi-almacén de una línea
 * de alquiler. Muestra un indicador con semáforo y al hacer clic
 * despliega un popover con el desglose por almacén.
 */
class RentalMultiWhWidget extends Component {
    static template = "rental_multi_warehouse.RentalMultiWhWidget";
    static props = { ...standardFieldProps };

    setup() {
        this.popover = usePopover(RentalMultiWhPopover, {
            position: "bottom",
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
                icon: "fa-check-circle",
                label: "Disponible en almacén preferente",
            },
            transfer_needed: {
                color: "text-info",
                icon: "fa-truck",
                label: "Requiere traslado inter-almacén",
            },
            deficit: {
                color: "text-danger",
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

    onClickDetail(ev) {
        if (this.availabilityData) {
            this.popover.open(ev.currentTarget, {
                data: this.availabilityData,
            });
        }
    }
}

registry.category("fields").add("rental_multi_wh_availability", {
    component: RentalMultiWhWidget,
});
