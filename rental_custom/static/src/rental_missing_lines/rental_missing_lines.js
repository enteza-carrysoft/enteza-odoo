/** @odoo-module **/
/**
 * Líneas de «Registrar faltas» (rental_custom 19.0.1.17.0, spec 004-faltas-buscador-ordenado).
 *
 * Un pedido de alquiler tiene decenas de líneas y pocas faltas, que se copian de un papel por
 * referencia. Encima de la lista: buscador (referencia que empieza por lo escrito o nombre que
 * lo contiene), «Solo con faltas» y contador. En la columna «Faltas», Intro y las flechas se
 * mueven como en una hoja de cálculo.
 *
 * Las filas que no coinciden solo se ocultan (`d-none`): siguen en la lista y sus valores se
 * envían al facturar. Se usa con `widget="rental_missing_lines"`; no hay `patch()`, así que
 * ninguna otra lista cambia.
 */

import { useRef, useState } from "@odoo/owl";
import { getActiveHotkey } from "@web/core/hotkeys/hotkey_service";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";
import { ListRenderer } from "@web/views/list/list_renderer";

function normalize(text) {
    return (text || "")
        .normalize("NFD")
        .replace(/[̀-ͯ]/g, "")
        .toLowerCase();
}

function productName(value) {
    // Many2one en la 19: `{id, display_name}`; se acepta también `[id, nombre]`.
    if (Array.isArray(value)) {
        return value[1] || "";
    }
    return value?.display_name || "";
}

export function isRecordVisible(record, filter) {
    if (filter.onlyMissing && !(record.data.qty_missing > 0)) {
        return false;
    }
    const term = normalize(filter.search.trim());
    if (!term) {
        return true;
    }
    return (
        normalize(record.data.default_code).startsWith(term) ||
        normalize(productName(record.data.product_id)).includes(term)
    );
}

export class RentalMissingListRenderer extends ListRenderer {
    static props = [...ListRenderer.props, "missingFilter"];

    setup() {
        super.setup();
        this.missingFilter = useState(this.props.missingFilter.state);
    }

    /** Filas visibles en el orden de pantalla (también tras ordenar por una cabecera). */
    get visibleRecords() {
        return this.props.list.records.filter((r) => isRecordVisible(r, this.missingFilter));
    }

    getRowClass(record) {
        const classes = super.getRowClass(record);
        return isRecordVisible(record, this.missingFilter) ? classes : `${classes} d-none`;
    }

    onCellKeydownEditMode(hotkey, cell, group, record) {
        if (record && !group) {
            switch (hotkey) {
                case "arrowdown":
                    this.moveTo(record, 1);
                    return true;
                case "arrowup":
                    this.moveTo(record, -1);
                    return true;
                case "enter":
                    if (this.missingFilter.search.trim()) {
                        this.backToSearch(true);
                        return true;
                    }
                    if (this.missingFilter.onlyMissing) {
                        // La siguiente fila nativa podría estar oculta.
                        this.moveTo(record, 1, true);
                        return true;
                    }
                    break;
            }
        }
        return super.onCellKeydownEditMode(hotkey, cell, group, record);
    }

    /** Aplica el valor (como `editNextRecord`) y edita la fila visible a `step` filas. */
    moveTo(record, step, wrap = false) {
        const visible = this.visibleRecords;
        let target = visible[visible.indexOf(record) + step];
        if (!target && wrap) {
            target = visible[0];
        }
        if (!target) {
            if (step < 0) {
                this.backToSearch(false);
            }
            return;
        }
        const list = this.props.list;
        list.leaveEditMode({ validate: true }).then((canProceed) => {
            if (canProceed) {
                list.enterEditMode(target);
            }
        });
    }

    backToSearch(clear) {
        this.props.list.leaveEditMode({ validate: true }).then((canProceed) => {
            if (canProceed) {
                this.props.missingFilter.focusSearch(clear);
            }
        });
    }
}

export class RentalMissingLinesField extends X2ManyField {
    static template = "rental_custom.RentalMissingLinesField";
    static components = { ...X2ManyField.components, ListRenderer: RentalMissingListRenderer };

    setup() {
        super.setup();
        this.filter = useState({ search: "", onlyMissing: false });
        this.searchRef = useRef("search");
        this.searchPlaceholder = _t("Buscar por referencia o nombre…");
        this.onlyMissingLabel = _t("Solo con faltas");
    }

    get rendererProps() {
        const props = super.rendererProps;
        props.missingFilter = {
            state: this.filter,
            focusSearch: (clear) => this.focusSearch(clear),
        };
        return props;
    }

    /** Totales del asistente, sin depender de los filtros. */
    get countLabel() {
        const records = this.list.records;
        return _t("%(total)s líneas · %(missing)s con faltas", {
            total: records.length,
            missing: records.filter((r) => r.data.qty_missing > 0).length,
        });
    }

    focusSearch(clear) {
        if (clear) {
            this.filter.search = "";
        }
        this.searchRef.el?.focus();
    }

    onSearchKeydown(ev) {
        const hotkey = getActiveHotkey(ev);
        if (hotkey === "enter") {
            // Nunca envía el formulario ni pulsa «Facturar las faltas».
            ev.preventDefault();
            ev.stopPropagation();
            const first = this.list.records.find((r) => isRecordVisible(r, this.filter));
            if (first) {
                this.list.enterEditMode(first);
            }
        } else if (hotkey === "escape" && this.filter.search) {
            // Con texto, Escape solo vacía el buscador: el diálogo no se cierra.
            ev.preventDefault();
            ev.stopPropagation();
            this.filter.search = "";
        }
    }
}

registry.category("fields").add("rental_missing_lines", {
    ...x2ManyField,
    component: RentalMissingLinesField,
});
