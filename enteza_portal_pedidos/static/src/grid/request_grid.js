/** @odoo-module **/

import { Component, useState, useRef, onWillStart, onMounted, onPatched, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { RequestService } from "../services/request_service";
import { buildTextIndex, buildTagIndex, matchesText, searchWords } from "../services/catalog_index";
import { FilterBar } from "../filters/filter_bar";
import { QtyCell } from "./qty_cell";
import { AvailabilityDot } from "./availability_dot";

// Ventana de render (PRP v2 §5.2, §7.2, F2): cuántas filas se pintan en el DOM de una vez.
// Antes se pintaban las 1.025 de golpe -con 0 facetas configuradas (verificado por RPC), el
// cliente estaba casi siempre ante el catálogo entero-, y cada confirmación de cantidad
// repintaba las 1.025 filas y sus componentes hijos. Cambiar cualquier filtro reinicia la
// ventana: es progressive disclosure, no solo rendimiento.
const FILAS_INICIALES = 60;
const FILAS_INCREMENTO = 60;

// Autoguardado: tiempo de inactividad tras la última tecla antes de reconciliar el cesto
// completo con el servidor (PRP v2 §2.2, F1/F2).
const AUTOSAVE_DEBOUNCE_MS = 2500;

const DIAS_CORTOS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];

/**
 * Rejilla de solicitud (PRP §9). Raíz montada como componente público del portal -no del
 * backend-, registrada en `public_components` (PRP §9.1).
 *
 * PRP v2 (2026-08-08): reescrita sobre el guardado idempotente del cesto completo (F1), la
 * ventana de render (F2), la fecha única derivada (D2) y el almacén fijo del cliente (D3).
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
        this._autosaveTimer = null;

        // Referencias para medir en tiempo real la altura del bloque superior fijo
        // (toolbar + avisos + cabecera + filtros) y pegar la cabecera de la tabla justo
        // debajo -en vez de sumar estimaciones en rem a mano, que dejaron de cuadrar en
        // cuanto la cabecera creció (PRP v2, corrección reportada en real el 2026-08-08).
        this.rootRef = useRef("root");
        this.stickyTopRef = useRef("stickyTop");
        this._resizeObserver = null;

        this.state = useState({
            cargando: true,
            error: null,
            order: {},
            eventDateInput: "",
            ajustando: false,
            pickupInput: "",
            returnInput: "",
            categories: [],
            facets: [],
            products: [],
            lines: {}, // productId -> cantidad
            availability: {}, // productId -> 'green'|'amber'|'red'|'grey'
            boxWarnings: {}, // productId -> aviso de múltiplo devuelto por el servidor
            avisos: [], // avisos NO bloqueantes del último guardado (antelación, ignorados)
            totals: { untaxed: 0, tax: 0, total: 0 },
            visibleProductIds: [],
            renderWindow: FILAS_INICIALES,
            filters: {
                text: "",
                categoryIds: [],
                facetTagIds: {}, // facetId -> [tagId, ...]
                onlyHabitual: false,
                onlyWithQty: false,
                hideUnavailable: false,
            },
            customerNote: "",
            estadoGuardado: null, // null|'pendiente'|'guardando'|'guardado'|'error'
            guardandoManual: false,
            enviando: false,
            mensaje: null, // {tipo: 'success'|'danger', texto: '...'}
            borrador: null, // cesto encontrado en localStorage, distinto del servidor
        });

        onWillStart(() => this._cargar());
        // `onMounted` no basta por sí solo: mientras `state.cargando` es `true` la
        // plantilla muestra el spinner y `.enteza_sticky_top` ni existe en el DOM todavía
        // -se monta más tarde, en un PATCH cuando `_cargar()` termina-. `onPatched` reintenta
        // en cada repintado, pero `_intentarObservarSticky` es idempotente (no hace nada si
        // ya hay un observer activo), así que no cuesta nada de más.
        onMounted(() => this._intentarObservarSticky());
        onPatched(() => this._intentarObservarSticky());
        onWillUnmount(() => {
            clearTimeout(this._autosaveTimer);
            if (this._resizeObserver) {
                this._resizeObserver.disconnect();
            }
        });
    }

    _intentarObservarSticky() {
        if (this._resizeObserver || !this.stickyTopRef.el || !this.rootRef.el) {
            return;
        }
        if (typeof ResizeObserver === "undefined") {
            // Navegador sin soporte (residual): se queda con el valor de arranque de
            // `--enteza-sticky-h` del SCSS -peor que medido, pero no rompe nada.
            return;
        }
        this._resizeObserver = new ResizeObserver(() => {
            const alto = this.stickyTopRef.el.getBoundingClientRect().height;
            this.rootRef.el.style.setProperty("--enteza-sticky-h", `${Math.ceil(alto)}px`);
        });
        this._resizeObserver.observe(this.stickyTopRef.el);
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
            const resultado = await this.service.catalogo();
            if (!resultado.ok) {
                this.state.error = resultado.error;
                return;
            }
            this.state.order = resultado.order;
            this.state.eventDateInput = resultado.order.event_date || "";
            this.state.categories = resultado.categories;
            this.state.facets = resultado.facets;
            this.state.products = resultado.products;
            this.state.totals = resultado.totals;
            this.state.customerNote = resultado.order.customer_note || "";

            const lineasServidor = {};
            for (const linea of resultado.lines) {
                lineasServidor[linea.product_id] = linea.qty;
            }
            this.state.lines = lineasServidor;

            this._productsById = new Map(resultado.products.map((p) => [p.id, p]));
            this.textIndex = buildTextIndex(resultado.products);
            this.tagIndex = buildTagIndex(resultado.products);

            // Entrada por el camino corto (PRP v2 §7.1): si el cliente tiene artículos
            // habituales, el filtro arranca activado -para quien repite, eso ES su pedido.
            this.state.filters.onlyHabitual = resultado.products.some((p) => p.habitual);

            this._recomputeVisible();
            this._precargarDisponibilidad();

            const borradorLocal = this._leerBorradorLocal();
            if (borradorLocal && JSON.stringify(borradorLocal) !== JSON.stringify(lineasServidor)) {
                this.state.borrador = borradorLocal;
            }
        } catch (error) {
            this.state.error = "No se ha podido cargar el catálogo. Recarga la página.";
            console.error(error); // eslint-disable-line no-console
        } finally {
            this.state.cargando = false;
        }
    }

    // ------------------------------------------------------------------
    // Borrador local (PRP v2 §F2): red de seguridad del guardado diferido
    // ------------------------------------------------------------------

    _claveLocalStorage() {
        return `enteza_portal_solicitud_${this.orderId}`;
    }

    _guardarBorradorLocal() {
        try {
            localStorage.setItem(this._claveLocalStorage(), JSON.stringify(this.state.lines));
        } catch {
            // Almacenamiento no disponible (modo privado, cuota llena...): no es crítico,
            // el guardado real sigue yendo al servidor igual.
        }
    }

    _leerBorradorLocal() {
        try {
            const crudo = localStorage.getItem(this._claveLocalStorage());
            return crudo ? JSON.parse(crudo) : null;
        } catch {
            return null;
        }
    }

    _limpiarBorradorLocal() {
        try {
            localStorage.removeItem(this._claveLocalStorage());
        } catch {
            // no-op
        }
    }

    onRecuperarBorrador() {
        this.state.lines = { ...this.state.borrador };
        this.state.borrador = null;
        this._recalcularTotalesProvisional();
        if (this.state.filters.onlyWithQty) {
            this._recomputeVisible();
        }
        this._scheduleAutosave();
    }

    onDescartarBorrador() {
        this.state.borrador = null;
        this._limpiarBorradorLocal();
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
        this.state.renderWindow = FILAS_INICIALES;
    }

    /** Contador de una opción de categoría con el resto de filtros aplicados (PRP §9.3).
     * Solo se llama mientras el desplegable correspondiente está abierto -ver
     * `facet_dropdown.js`-, así que el coste O(productos) no se paga en cada render. */
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

    // ------------------------------------------------------------------
    // Ventana de render (PRP v2 §5.2, §7.2, F2)
    // ------------------------------------------------------------------

    get renderedProductIds() {
        return this.state.visibleProductIds.slice(0, this.state.renderWindow);
    }

    get hayMasFilas() {
        return this.state.visibleProductIds.length > this.state.renderWindow;
    }

    get filasRestantes() {
        return Math.max(this.state.visibleProductIds.length - this.state.renderWindow, 0);
    }

    onMostrarMas() {
        this.state.renderWindow += FILAS_INCREMENTO;
    }

    onVerTodoElCatalogo() {
        this.state.filters = {
            ...this.state.filters,
            text: "", categoryIds: [], facetTagIds: {}, onlyHabitual: false,
        };
        this._recomputeVisible();
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
        if (!(this.state.order.pickup_date && this.state.order.return_date)) {
            return;
        }
        let candidatos;
        if (idsForzados) {
            candidatos = idsForzados;
        } else {
            const enVentana = this.renderedProductIds;
            const conCantidad = Object.keys(this.state.lines).map((k) => parseInt(k, 10));
            candidatos = [...new Set([...enVentana, ...conCantidad])];
        }
        candidatos = candidatos.filter((id) => !(id in this.state.availability));
        if (!candidatos.length) {
            return;
        }
        const items = candidatos.map((id) => ({ productId: id, qty: this.state.lines[id] || 0 }));
        const resultado = await this.service.disponibilidad(items);
        if (!resultado.ok) {
            // El semáforo es orientativo (PRP §6.4): un fallo aquí no merece un banner de
            // error, se deja simplemente sin colorear esas filas.
            return;
        }
        this.state.availability = { ...this.state.availability, ...resultado.colors };
        if (this.state.filters.hideUnavailable) {
            // PRP v2 §5.6: sin esto, "ocultar sin disponibilidad" quedaba desfasado hasta
            // la siguiente interacción -los colores llegaban después del filtrado.
            this._recomputeVisible();
        }
    }

    // ------------------------------------------------------------------
    // Cabecera: fecha única derivada (D2), sin selector de almacén (D3)
    // ------------------------------------------------------------------

    formatoFechaCorta(iso) {
        if (!iso) {
            return "";
        }
        const [y, m, d] = iso.split("-").map(Number);
        const fecha = new Date(y, m - 1, d);
        return `${DIAS_CORTOS[fecha.getDay()]} ${String(d).padStart(2, "0")}`;
    }

    _construirHeader() {
        const header = { event_date: this.state.eventDateInput || null };
        if (this.state.ajustando) {
            header.pickup_date = this.state.pickupInput || null;
            header.return_date = this.state.returnInput || null;
        }
        return header;
    }

    async _guardarHeaderAhora() {
        const resultado = await this.service.guardar({ header: this._construirHeader() });
        if (!resultado.ok) {
            this.state.mensaje = { tipo: "danger", texto: resultado.error };
            return;
        }
        this.state.order = resultado.order;
        this.state.eventDateInput = resultado.order.event_date || "";
        this.state.avisos = resultado.warnings || [];
        // Fechas distintas invalidan todo lo que hubiera en caché (PRP §6.2).
        this.state.availability = {};
        this._precargarDisponibilidad();
    }

    async onEventDateChange(valor) {
        this.state.eventDateInput = valor;
        await this._guardarHeaderAhora();
    }

    onAjustarAbrir() {
        this.state.pickupInput = this.state.order.pickup_date || "";
        this.state.returnInput = this.state.order.return_date || "";
        this.state.ajustando = true;
    }

    onAjustarCancelar() {
        this.state.ajustando = false;
    }

    async onAjustarConfirmar() {
        await this._guardarHeaderAhora();
        this.state.ajustando = false;
    }

    async onUsarFechasAutomaticas() {
        this.state.ajustando = false;
        this.state.pickupInput = "";
        this.state.returnInput = "";
        await this._guardarHeaderAhora();
    }

    // ------------------------------------------------------------------
    // Líneas (PRP §7) — guardado idempotente del cesto completo (PRP v2 §2.2, F1)
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
        this._guardarBorradorLocal();
        this._scheduleAutosave();

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

    _construirLineas() {
        return Object.entries(this.state.lines)
            .filter(([, qty]) => qty > 0)
            .map(([productId, qty]) => ({ product_id: parseInt(productId, 10), qty }));
    }

    _aplicarResultadoGuardado(resultado) {
        this.state.totals = { ...resultado.totals, provisional: false };
        this.state.avisos = resultado.warnings || [];

        const nuevasBoxWarnings = {};
        for (const aviso of resultado.box_warnings || []) {
            nuevasBoxWarnings[aviso.product_id] = aviso;
        }
        this.state.boxWarnings = nuevasBoxWarnings;

        // El servidor reconcilia el cesto ENTERO en cada llamada, así que su respuesta ya
        // es autoritativa para toda línea con cantidad -no hace falta fusionar, se
        // reemplaza (PRP v2 §5.9a: con guardado incremental esto habría sido una
        // divergencia silenciosa; con el cesto completo es sencillamente el estado real).
        const nuevasLineas = {};
        for (const linea of resultado.lines) {
            nuevasLineas[linea.product_id] = linea.qty;
        }
        this.state.lines = nuevasLineas;
    }

    _scheduleAutosave() {
        clearTimeout(this._autosaveTimer);
        this.state.estadoGuardado = "pendiente";
        this._autosaveTimer = setTimeout(() => this._autoguardarAhora(), AUTOSAVE_DEBOUNCE_MS);
    }

    async _autoguardarAhora() {
        this.state.estadoGuardado = "guardando";
        const resultado = await this.service.guardar({ lines: this._construirLineas() });
        if (!resultado.ok) {
            this.state.estadoGuardado = "error";
            this.state.mensaje = { tipo: "danger", texto: resultado.error };
            return;
        }
        this._aplicarResultadoGuardado(resultado);
        this.state.estadoGuardado = "guardado";
        this._limpiarBorradorLocal();
    }

    get indicadorGuardado() {
        switch (this.state.estadoGuardado) {
            case "guardando":
                return "Guardando…";
            case "guardado":
                return "Guardado";
            case "error":
                return "Sin guardar: hubo un error. Pulsa «Guardar».";
            case "pendiente":
                return "Cambios sin guardar";
            default:
                return "";
        }
    }

    // ------------------------------------------------------------------
    // Guardar / Enviar / Cancelar (PRP §4.1, §8.2)
    // ------------------------------------------------------------------

    async onGuardar() {
        clearTimeout(this._autosaveTimer);
        this.state.guardandoManual = true;
        this.state.mensaje = null;
        await this._autoguardarAhora();
        if (this.state.estadoGuardado === "guardado") {
            this.state.mensaje = { tipo: "success", texto: "Guardado." };
        }
        this.state.guardandoManual = false;
    }

    async onEnviar() {
        clearTimeout(this._autosaveTimer);
        this.state.enviando = true;
        this.state.mensaje = null;
        const resultado = await this.service.enviar({
            header: this._construirHeader(),
            lines: this._construirLineas(),
            customerNote: this.state.customerNote,
        });
        if (!resultado.ok) {
            this.state.mensaje = { tipo: "danger", texto: resultado.error };
            this.state.enviando = false;
            return;
        }
        this._limpiarBorradorLocal();
        window.location.href = resultado.redirect;
    }

    async onCancelar() {
        // eslint-disable-next-line no-alert
        if (!window.confirm(
                "¿Seguro que quieres cancelar esta solicitud? Se perderá lo que hayas montado.")) {
            return;
        }
        clearTimeout(this._autosaveTimer);
        const resultado = await this.service.cancelar();
        if (!resultado.ok) {
            this.state.mensaje = { tipo: "danger", texto: resultado.error };
            return;
        }
        this._limpiarBorradorLocal();
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
