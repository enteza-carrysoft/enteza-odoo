/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { RequestService } from "../services/request_service";
import { buildTextIndex, buildTagIndex, matchesText, searchWords } from "../services/catalog_index";
import { FilterBar } from "../filters/filter_bar";
import { QtyCell } from "./qty_cell";
import { AvailabilityDot } from "./availability_dot";

// Al filtrar o cambiar fechas/almacén, cuántas filas visibles se precargan en segundo plano
// (PRP §6.2). No es un verdadero IntersectionObserver por fila -viable, pero no se puede
// verificar contra `enteza26` sin instancia de pruebas-: cubre el caso normal (menos de 150
// artículos visibles a la vez tras filtrar) sin recorrer el catálogo entero de golpe.
const PRECARGA_DISPONIBILIDAD_MAX = 150;

/**
 * Rejilla de solicitud (PRP §9). Raíz montada como componente público del portal -no del
 * backend-, registrada en `public_components` (PRP §9.1).
 */
export class RequestGrid extends Component {
    static template = "enteza_portal_pedidos.RequestGrid";
    static components = { FilterBar, QtyCell, AvailabilityDot };
    static props = {};

    setup() {
        this.orderId = this._leerOrderId();
        this.service = new RequestService(this.orderId);

        // Índices y catálogo: NO son reactivos a propósito (PRP §9.5). Se construyen una
        // sola vez al cargar y no cambian mientras el cliente filtra o teclea cantidades;
        // envolverlos en `useState` solo obligaría a Owl a vigilar 1.025 objetos sin ningún
        // beneficio, porque nada en la plantilla los lee directamente -solo los métodos.
        this.textIndex = new Map();
        this.tagIndex = new Map();
        this._productsById = new Map();
        this._searchWords = [];

        this.state = useState({
            cargando: true,
            error: null,
            order: {},
            categories: [],
            facets: [],
            products: [],
            lines: {}, // productId -> cantidad
            availability: {}, // productId -> 'green'|'amber'|'red'|'grey'
            boxWarnings: {}, // productId -> aviso de múltiplo devuelto por el servidor
            totals: { untaxed: 0, tax: 0, total: 0 },
            visibleProductIds: [],
            filters: {
                text: "",
                categoryIds: [],
                facetTagIds: {}, // facetId -> [tagId, ...]
                onlyHabitual: false,
                onlyWithQty: false,
                hideUnavailable: false,
            },
            customerNote: "",
            guardando: false,
            enviando: false,
            mensaje: null, // {tipo: 'success'|'danger', texto: '...'}
        });

        onWillStart(() => this._cargar());
    }

    _leerOrderId() {
        // El id viaja por un <script type="application/json">, no por el mecanismo de
        // `props` de `owl-component` (PRP §9.1, ver portal_templates.xml para el porqué).
        const elemento = document.getElementById("enteza_portal_pedidos_data");
        if (!elemento) {
            return 0;
        }
        try {
            return JSON.parse(elemento.textContent).orderId || 0;
        } catch {
            return 0;
        }
    }

    async _cargar() {
        try {
            const payload = await this.service.catalogo();
            this.state.order = payload.order;
            this.state.categories = payload.categories;
            this.state.facets = payload.facets;
            this.state.products = payload.products;
            this.state.totals = payload.totals;
            this.state.customerNote = payload.order.customer_note || "";

            const lineas = {};
            for (const linea of payload.lines) {
                lineas[linea.product_id] = linea.qty;
            }
            this.state.lines = lineas;

            this._productsById = new Map(payload.products.map((p) => [p.id, p]));
            this.textIndex = buildTextIndex(payload.products);
            this.tagIndex = buildTagIndex(payload.products);

            this._recomputeVisible();
            this._precargarDisponibilidad();
        } catch (error) {
            this.state.error = "No se ha podido cargar el catálogo. Recarga la página.";
            console.error(error); // eslint-disable-line no-console
        } finally {
            this.state.cargando = false;
        }
    }

    // ------------------------------------------------------------------
    // Filtrado (PRP §9.3, §9.5)
    // ------------------------------------------------------------------

    _matchesFilters(producto, { excludeCategory = false, excludeFacetId = null } = {}) {
        const f = this.state.filters;
        if (this._searchWords.length && !matchesText(producto, this.textIndex, this._searchWords)) {
            return false;
        }
        if (!excludeCategory && f.categoryIds.length &&
                !f.categoryIds.includes(producto.category_id)) {
            return false;
        }
        for (const facetIdStr of Object.keys(f.facetTagIds)) {
            const tagIds = f.facetTagIds[facetIdStr];
            if (!tagIds || !tagIds.length) {
                continue;
            }
            if (excludeFacetId !== null && String(facetIdStr) === String(excludeFacetId)) {
                continue;
            }
            const productTagIds = producto.tag_ids || [];
            if (!tagIds.some((id) => productTagIds.includes(id))) {
                return false;
            }
        }
        if (f.onlyHabitual && !producto.habitual) {
            return false;
        }
        if (f.onlyWithQty && !(this.state.lines[producto.id] > 0)) {
            return false;
        }
        if (f.hideUnavailable && this.state.availability[producto.id] === "red") {
            return false;
        }
        return true;
    }

    _recomputeVisible() {
        this._searchWords = searchWords(this.state.filters.text);
        const visibles = [];
        for (const producto of this.state.products) {
            if (this._matchesFilters(producto, {})) {
                visibles.push(producto.id);
            }
        }
        this.state.visibleProductIds = visibles;
    }

    /** Contador de una opción de categoría con el resto de filtros aplicados (PRP §9.3). */
    categoryOptionCount(categoryId) {
        let n = 0;
        for (const producto of this.state.products) {
            if (producto.category_id === categoryId &&
                    this._matchesFilters(producto, { excludeCategory: true })) {
                n++;
            }
        }
        return n;
    }

    /** Ídem para una opción de faceta, excluyendo su propia dimensión del filtrado. */
    facetOptionCount(facetId, tagId) {
        let n = 0;
        for (const producto of this.state.products) {
            if ((producto.tag_ids || []).includes(tagId) &&
                    this._matchesFilters(producto, { excludeFacetId: facetId })) {
                n++;
            }
        }
        return n;
    }

    get visibleCount() {
        return this.state.visibleProductIds.length;
    }

    get totalCount() {
        return this.state.products.length;
    }

    get lineCount() {
        return Object.values(this.state.lines).filter((qty) => qty > 0).length;
    }

    /** Líneas con cantidad que el filtro activo esconde (PRP §9.3): el pie avisa siempre. */
    get hiddenWithQtyCount() {
        const visibles = new Set(this.state.visibleProductIds);
        let n = 0;
        for (const clave of Object.keys(this.state.lines)) {
            const productId = parseInt(clave, 10);
            if (this.state.lines[clave] > 0 && !visibles.has(productId)) {
                n++;
            }
        }
        return n;
    }

    onTextChange(texto) {
        this.state.filters = { ...this.state.filters, text: texto };
        this._recomputeVisible();
    }

    onCategoryChange(ids) {
        this.state.filters = { ...this.state.filters, categoryIds: ids };
        this._recomputeVisible();
        this._precargarDisponibilidad();
    }

    onFacetChange(facetId, ids) {
        this.state.filters = {
            ...this.state.filters,
            facetTagIds: { ...this.state.filters.facetTagIds, [facetId]: ids },
        };
        this._recomputeVisible();
        this._precargarDisponibilidad();
    }

    onToggleChange(clave, valor) {
        this.state.filters = { ...this.state.filters, [clave]: valor };
        this._recomputeVisible();
    }

    /** «Limpiar todo» (PRP §9.3): solo categoría y facetas -lo que genera chips-, no los
     * conmutadores ni la búsqueda de texto, que el cliente puede querer conservar. */
    onClearAllFilters() {
        this.state.filters = { ...this.state.filters, categoryIds: [], facetTagIds: {} };
        this._recomputeVisible();
    }

    // ------------------------------------------------------------------
    // Disponibilidad (PRP §6.2)
    // ------------------------------------------------------------------

    async _precargarDisponibilidad(idsForzados = null) {
        if (!this.state.order.semaforo_activo) {
            return;
        }
        if (!(this.state.order.warehouse_id && this.state.order.pickup_date &&
                this.state.order.return_date)) {
            return;
        }
        let candidatos;
        if (idsForzados) {
            candidatos = idsForzados.filter((id) => !(id in this.state.availability));
        } else {
            candidatos = this.state.visibleProductIds
                .filter((id) => !(id in this.state.availability))
                .slice(0, PRECARGA_DISPONIBILIDAD_MAX);
        }
        if (!candidatos.length) {
            return;
        }
        const resultado = await this.service.disponibilidad(candidatos);
        this.state.availability = { ...this.state.availability, ...resultado };
    }

    // ------------------------------------------------------------------
    // Cabecera (PRP §8.2 /cabecera)
    // ------------------------------------------------------------------

    async onHeaderChange(campo, valor) {
        const resultado = await this.service.cabecera(
            { [campo]: valor }, this.state.order.write_date);
        if (resultado.error) {
            this.state.mensaje = { tipo: "danger", texto: this._errorLegible(resultado.error) };
            return;
        }
        this.state.order = resultado;
        // Fechas o almacén distintos invalidan todo lo que hubiera en caché (PRP §6.2).
        this.state.availability = {};
        this._precargarDisponibilidad();
    }

    _errorLegible(error) {
        if (error === "stale") {
            return "La solicitud se ha actualizado en otra pestaña. Recarga la página.";
        }
        return error;
    }

    // ------------------------------------------------------------------
    // Líneas (PRP §7, §8.2 /lineas)
    // ------------------------------------------------------------------

    onQtyChange(productId, qty) {
        if (qty > 0) {
            this.state.lines = { ...this.state.lines, [productId]: qty };
        } else {
            const restantes = { ...this.state.lines };
            delete restantes[productId];
            this.state.lines = restantes;
        }

        this._recalcularTotalesProvisional();

        this.service.encolarCambioLinea(
            productId, qty, this.state.order.write_date,
            (resultado) => this._aplicarResultadoLineas(resultado),
        );

        if (this.state.filters.onlyWithQty) {
            this._recomputeVisible();
        }
        if (this.state.order.semaforo_activo && !(productId in this.state.availability)) {
            this._precargarDisponibilidad([productId]);
        }
    }

    /** Estimación optimista mientras se espera la confirmación del servidor (sin
     * impuestos: reproducir el cálculo de IVA en el navegador no compensa el riesgo de
     * que discrepe con lo que factura Odoo). */
    _recalcularTotalesProvisional() {
        let untaxed = 0;
        for (const clave of Object.keys(this.state.lines)) {
            const producto = this._productsById.get(parseInt(clave, 10));
            if (producto) {
                untaxed += this.state.lines[clave] * producto.price;
            }
        }
        this.state.totals = { ...this.state.totals, untaxed, provisional: true };
    }

    _aplicarResultadoLineas(resultado) {
        if (!resultado) {
            return;
        }
        if (resultado.error) {
            this.state.mensaje = { tipo: "danger", texto: this._errorLegible(resultado.error) };
            return;
        }
        this.state.totals = { ...resultado.totals, provisional: false };
        this.state.order = { ...this.state.order, write_date: resultado.write_date };

        const nuevasLineas = { ...this.state.lines };
        for (const linea of resultado.lines) {
            nuevasLineas[linea.product_id] = linea.qty;
        }
        this.state.lines = nuevasLineas;

        const avisos = {};
        for (const aviso of resultado.warnings || []) {
            avisos[aviso.product_id] = aviso;
        }
        this.state.boxWarnings = avisos;
    }

    // ------------------------------------------------------------------
    // Guardar / Enviar / Cancelar (PRP §4.1, §8.2)
    // ------------------------------------------------------------------

    async onGuardar() {
        this.state.guardando = true;
        this.state.mensaje = null;
        try {
            const resultado = await this.service.flushLineasAhora(this.state.order.write_date);
            if (resultado) {
                this._aplicarResultadoLineas(resultado);
            }
            if (!this.state.mensaje) {
                this.state.mensaje = { tipo: "success", texto: "Guardado." };
            }
        } finally {
            this.state.guardando = false;
        }
    }

    async onEnviar() {
        this.state.enviando = true;
        this.state.mensaje = null;
        try {
            const previas = await this.service.flushLineasAhora(this.state.order.write_date);
            if (previas) {
                this._aplicarResultadoLineas(previas);
            }
            const resultado = await this.service.enviar(
                this.state.customerNote, this.state.order.write_date);
            if (resultado.error) {
                this.state.mensaje = { tipo: "danger", texto: this._errorLegible(resultado.error) };
                return;
            }
            window.location.href = resultado.redirect;
        } finally {
            this.state.enviando = false;
        }
    }

    async onCancelar() {
        // eslint-disable-next-line no-alert
        if (!window.confirm(
                "¿Seguro que quieres cancelar esta solicitud? Se perderá lo que hayas montado.")) {
            return;
        }
        await this.service.cancelar();
        window.location.href = "/my/solicitudes";
    }

    // ------------------------------------------------------------------
    // Formato
    // ------------------------------------------------------------------

    formatoMoneda(valor) {
        const moneda = this.state.order.currency || { symbol: "€", position: "after", decimals: 2 };
        const numero = (valor || 0).toFixed(moneda.decimals);
        return moneda.position === "before" ? `${moneda.symbol}${numero}` : `${numero} ${moneda.symbol}`;
    }
}

registry.category("public_components").add("enteza_portal_pedidos.RequestGrid", RequestGrid);
