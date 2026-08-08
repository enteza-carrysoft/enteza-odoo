/** @odoo-module **/

import { Component } from "@odoo/owl";

/**
 * Punto de color del semáforo de disponibilidad (PRP §6.3). Nunca recibe ni muestra la
 * cantidad libre: solo el color que ya decidió el servidor.
 */
export class AvailabilityDot extends Component {
    static template = "enteza_portal_pedidos.AvailabilityDot";
    static props = {
        color: { type: String, optional: true },
    };

    static ETIQUETAS = {
        green: "Disponible",
        amber: "Puede que no haya todo",
        red: "Sin disponibilidad",
        grey: "",
    };

    get color() {
        return this.props.color || "grey";
    }

    get etiqueta() {
        return AvailabilityDot.ETIQUETAS[this.color] || "";
    }
}
