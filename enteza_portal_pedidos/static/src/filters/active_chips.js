/** @odoo-module **/

import { Component } from "@odoo/owl";

/**
 * Filtros activos como *chips* con su ✕, más «Limpiar todo» (PRP §9.3). Sin esto, con
 * cuatro desplegables el cliente pierde de vista por qué solo ve 38 artículos.
 */
export class ActiveChips extends Component {
    static template = "enteza_portal_pedidos.ActiveChips";
    static props = {
        chips: { type: Array }, // [{id, label}]
        onRemove: { type: Function },
        onClearAll: { type: Function },
    };
}
