/** @odoo-module **/

import { Component, useState, useRef, useExternalListener } from "@odoo/owl";

/**
 * UN desplegable genérico y reutilizable (PRP §9.3, §13): «Categoría», «Marca», «Modelo» y
 * «Color» son el mismo componente con datos distintos. Es lo que permite que una faceta
 * nueva («Estilo») aparezca en el portal sin escribir ni una línea de código.
 */
export class FacetDropdown extends Component {
    static template = "enteza_portal_pedidos.FacetDropdown";
    static props = {
        label: { type: String },
        options: { type: Array }, // [{id, name}]
        selectedIds: { type: Array },
        multi: { type: Boolean, optional: true },
        getCount: { type: Function }, // (optionId) => number
        onChange: { type: Function }, // (nuevosIds) => void
    };

    setup() {
        this.state = useState({ open: false, buscar: "" });
        this.rootRef = useRef("root");
        useExternalListener(document, "click", (ev) => this._cerrarSiFuera(ev), {
            capture: true,
        });
    }

    get muchasOpciones() {
        return this.props.options.length > 12;
    }

    /**
     * Con contador se ordena primero lo seleccionado, luego lo disponible, y al final -
     * atenuado, no oculto (PRP §9.3)- lo que quedaría a cero con el resto de filtros.
     *
     * 🔴 PRP v2 §5.2/F2: con el desplegable CERRADO no se recorre nada -ni `filter`, ni
     * `map`, ni `sort`, ni `getCount` (que es O(productos) por opción). Antes se
     * recalculaba en cada render del padre aunque el desplegable estuviera cerrado y nadie
     * pudiera ver el resultado.
     */
    get opcionesOrdenadas() {
        if (!this.state.open) {
            return [];
        }
        const texto = this.state.buscar.trim().toLowerCase();
        const filtradas = this.props.options.filter(
            (opcion) => !texto || opcion.name.toLowerCase().includes(texto)
        );
        const conCuenta = filtradas.map((opcion) => ({
            ...opcion,
            count: this.state.open ? this.props.getCount(opcion.id) : 0,
            selected: this.props.selectedIds.includes(opcion.id),
        }));
        conCuenta.sort((a, b) => {
            if (a.selected !== b.selected) {
                return a.selected ? -1 : 1;
            }
            if ((a.count > 0) !== (b.count > 0)) {
                return a.count > 0 ? -1 : 1;
            }
            return 0;
        });
        return conCuenta;
    }

    get resumen() {
        const n = this.props.selectedIds.length;
        return n ? `${this.props.label} (${n})` : this.props.label;
    }

    toggle() {
        this.state.open = !this.state.open;
    }

    _cerrarSiFuera(ev) {
        if (this.state.open && this.rootRef.el && !this.rootRef.el.contains(ev.target)) {
            this.state.open = false;
        }
    }

    toggleOpcion(optionId) {
        const actuales = this.props.selectedIds;
        let siguientes;
        if (this.props.multi === false) {
            siguientes = actuales.includes(optionId) ? [] : [optionId];
            this.state.open = false;
        } else {
            siguientes = actuales.includes(optionId)
                ? actuales.filter((id) => id !== optionId)
                : [...actuales, optionId];
        }
        this.props.onChange(siguientes);
    }

    onKeydown(ev) {
        if (ev.key === "Escape") {
            this.state.open = false;
        }
    }
}
