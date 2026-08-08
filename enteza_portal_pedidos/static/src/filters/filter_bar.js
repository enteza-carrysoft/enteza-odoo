/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { FacetDropdown } from "./facet_dropdown";
import { ActiveChips } from "./active_chips";

const DEBOUNCE_TEXTO_MS = 150;

/**
 * La banda de filtros (PRP §9.3): búsqueda + categoría + un desplegable por faceta +
 * conmutadores + chips activos. Todo se resuelve en el navegador sobre el catálogo ya
 * cargado -esta banda solo traduce la interacción del cliente a cambios de estado, no
 * vuelve a preguntar nada al servidor.
 */
export class FilterBar extends Component {
    static template = "enteza_portal_pedidos.FilterBar";
    static components = { FacetDropdown, ActiveChips };
    static props = {
        filters: { type: Object },
        categories: { type: Array },
        facets: { type: Array },
        categoryOptionCount: { type: Function },
        facetOptionCount: { type: Function },
        semaforoActivo: { type: Boolean },
        onTextChange: { type: Function },
        onCategoryChange: { type: Function },
        onFacetChange: { type: Function }, // (facetId, ids) => void
        onToggleChange: { type: Function }, // (clave, valor) => void
        onClearAll: { type: Function },
    };

    setup() {
        this.state = useState({ textoLocal: this.props.filters.text || "" });
        this._debounceTimer = null;
    }

    onInputTexto(ev) {
        this.state.textoLocal = ev.target.value;
        clearTimeout(this._debounceTimer);
        this._debounceTimer = setTimeout(() => {
            this.props.onTextChange(this.state.textoLocal);
        }, DEBOUNCE_TEXTO_MS);
    }

    getCategoryCount(id) {
        return this.props.categoryOptionCount(id);
    }

    getFacetCount(facetId, tagId) {
        return this.props.facetOptionCount(facetId, tagId);
    }

    facetSeleccion(facetId) {
        return this.props.filters.facetTagIds[facetId] || [];
    }

    get chips() {
        const chips = [];
        for (const catId of this.props.filters.categoryIds) {
            const categoria = this.props.categories.find((c) => c.id === catId);
            if (categoria) {
                chips.push({ id: `cat:${catId}`, label: categoria.name });
            }
        }
        for (const faceta of this.props.facets) {
            for (const tagId of this.facetSeleccion(faceta.id)) {
                const tag = faceta.tags.find((t) => t.id === tagId);
                if (tag) {
                    chips.push({
                        id: `facet:${faceta.id}:${tagId}`,
                        label: `${faceta.name}: ${tag.name}`,
                    });
                }
            }
        }
        return chips;
    }

    onRemoveChip(chipId) {
        const [tipo, a, b] = chipId.split(":");
        if (tipo === "cat") {
            const catId = parseInt(a, 10);
            this.props.onCategoryChange(
                this.props.filters.categoryIds.filter((id) => id !== catId)
            );
        } else if (tipo === "facet") {
            const facetId = parseInt(a, 10);
            const tagId = parseInt(b, 10);
            const actuales = this.facetSeleccion(facetId);
            this.props.onFacetChange(facetId, actuales.filter((id) => id !== tagId));
        }
    }

    onToggle(clave, ev) {
        this.props.onToggleChange(clave, ev.target.checked);
    }
}
