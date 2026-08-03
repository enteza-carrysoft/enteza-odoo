/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";

// Lunes primero: es el orden de la aplicación que se está reproduciendo y el habitual aquí.
const DIAS_SEMANA = ["L", "M", "X", "J", "V", "S", "D"];

const MESES = [
    _t("Enero"), _t("Febrero"), _t("Marzo"), _t("Abril"), _t("Mayo"), _t("Junio"),
    _t("Julio"), _t("Agosto"), _t("Septiembre"), _t("Octubre"), _t("Noviembre"), _t("Diciembre"),
];

/**
 * Los tres días distintos que tiene un pedido de alquiler.
 *
 * `rental_custom` deja la salida la víspera del evento y la devolución el día siguiente, así
 * que los eventos de hoy y el trabajo de hoy en el almacén casi nunca son lo mismo. Cada
 * modo recolorea el calendario y recarga los dos bloques.
 */
const MODOS = [
    { clave: "evento", etiqueta: _t("Eventos"), material: _t("Material del evento") },
    { clave: "salida", etiqueta: _t("Sale hoy"), material: _t("Material que sale") },
    { clave: "devolucion", etiqueta: _t("Vuelve hoy"), material: _t("Material que vuelve") },
];

/**
 * Cortes de la escala de color, medidos sobre la carga real de `enteza26` (150 días con
 * actividad, agosto de 2026): mediana 3 pedidos/día, p85 = 14, p90 = 23, p95 = 46, máximo 57.
 *
 * Los cortes anteriores (3 y 6) saturaban la escala: todos los sábados de temporada pintaban
 * igual y el calendario dejaba de informar justo en los días que más importan.
 */
const CORTES_CARGA = [3, 10, 30];

/**
 * Fecha -> 'AAAA-MM-DD' en hora local.
 *
 * Deliberadamente NO se usa toISOString(): convierte a UTC y en zonas al este de Greenwich
 * devuelve el día anterior a partir de cierta hora, que es justo el error que haría que el
 * panel mostrase los pedidos del día equivocado.
 */
function aClaveDia(fecha) {
    const mes = String(fecha.getMonth() + 1).padStart(2, "0");
    const dia = String(fecha.getDate()).padStart(2, "0");
    return `${fecha.getFullYear()}-${mes}-${dia}`;
}

/**
 * Minúsculas y sin tildes, para que «bambalina» encuentre «BAMBALINA BEIGE» y «mantel»
 * encuentre «MANTELERÍA». El rango U+0300-U+036F son los acentos que NFD deja sueltos.
 */
function normalizar(texto) {
    return (texto || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

export class PanelEventos extends Component {
    static template = "enteza_panel_eventos.PanelEventos";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        const hoy = new Date();
        this.claveHoy = aClaveDia(hoy);

        this.state = useState({
            anio: hoy.getFullYear(),
            mes: hoy.getMonth() + 1,
            modo: "evento",
            diaSeleccionado: this.claveHoy,
            cargaMes: {},
            pedidos: [],
            articulos: [],
            totales: { pedidos: 0, importe: "", unidades: 0, sobreventa: 0 },
            contadores: { evento: 0, salida: 0, devolucion: 0 },
            // Bloque de material: filtro por descripción y vista, como en la aplicación
            // anterior. `sobreventa` deja solo los artículos de los que no hay bastante.
            filtroArticulo: "",
            vistaMaterial: "consumos",
            // Artículo pinchado: filtra los pedidos de abajo a los que lo llevan.
            articuloSeleccionado: null,
            cargando: true,
        });

        onWillStart(async () => {
            await Promise.all([this.cargarMes(), this.cargarDia(this.state.diaSeleccionado)]);
        });
    }

    // ------------------------------------------------------------------
    // Carga de datos
    // ------------------------------------------------------------------

    async cargarMes() {
        this.state.cargaMes = await this.orm.call(
            "sale.order",
            "enteza_panel_carga_mes",
            [this.state.anio, this.state.mes, this.state.modo]
        );
    }

    async cargarDia(clave) {
        this.state.cargando = true;
        // La selección de artículo es del día que se estaba mirando: al cambiar de día
        // apuntaría a un artículo que quizá ya no está en la lista.
        this.state.articuloSeleccionado = null;
        try {
            const datos = await this.orm.call(
                "sale.order", "enteza_panel_dia", [clave, this.state.modo]
            );
            this.state.pedidos = datos.pedidos;
            this.state.articulos = datos.articulos;
            this.state.totales = datos.totales;
            this.state.contadores = datos.contadores;
        } finally {
            this.state.cargando = false;
        }
    }

    // ------------------------------------------------------------------
    // Rejilla del calendario
    // ------------------------------------------------------------------

    get diasSemana() {
        return DIAS_SEMANA;
    }

    get modos() {
        return MODOS;
    }

    get nombreMes() {
        return `${MESES[this.state.mes - 1]} ${this.state.anio}`;
    }

    get prefijoMes() {
        return `${this.state.anio}-${String(this.state.mes).padStart(2, "0")}`;
    }

    /**
     * Celdas de la rejilla mensual, incluidos los huecos iniciales para que el día 1 caiga
     * en su columna. Los huecos son `null`.
     */
    get celdas() {
        const { anio, mes } = this.state;
        const primero = new Date(anio, mes - 1, 1);
        // getDay() da 0 para domingo; aquí la semana empieza en lunes.
        const hueco = (primero.getDay() + 6) % 7;
        const diasDelMes = new Date(anio, mes, 0).getDate();

        const celdas = new Array(hueco).fill(null);
        for (let dia = 1; dia <= diasDelMes; dia++) {
            const clave = aClaveDia(new Date(anio, mes - 1, dia));
            const carga = this.state.cargaMes[clave];
            celdas.push({
                dia,
                clave,
                pedidos: carga ? carga.pedidos : 0,
                nivel: this.nivelCarga(carga ? carga.pedidos : 0),
                esHoy: clave === this.claveHoy,
                seleccionado: clave === this.state.diaSeleccionado,
            });
        }
        return celdas;
    }

    /** Intensidad del color de un día según cuántos pedidos tenga. Ver CORTES_CARGA. */
    nivelCarga(pedidos) {
        if (!pedidos) {
            return 0;
        }
        return CORTES_CARGA.filter((corte) => pedidos >= corte).length + 1;
    }

    // ------------------------------------------------------------------
    // Bloque de material
    // ------------------------------------------------------------------

    get tituloMaterial() {
        return MODOS.find((modo) => modo.clave === this.state.modo).material;
    }

    /** Artículos tras aplicar el filtro por descripción y la vista elegida. */
    get articulosVisibles() {
        const busqueda = normalizar(this.state.filtroArticulo);
        const soloSobreventa = this.state.vistaMaterial === "sobreventa";
        return this.state.articulos.filter((articulo) => {
            if (soloSobreventa && !articulo.sobreventa) {
                return false;
            }
            if (!busqueda) {
                return true;
            }
            return normalizar(articulo.articulo).includes(busqueda)
                || normalizar(articulo.categoria).includes(busqueda);
        });
    }

    /**
     * Pedidos de abajo, filtrados al artículo pinchado si lo hay.
     *
     * El filtro se hace aquí y no en el servidor porque cada pedido ya trae la lista de sus
     * artículos: son decenas de pedidos como mucho y la respuesta tiene que ser inmediata.
     */
    get pedidosVisibles() {
        const producto = this.state.articuloSeleccionado;
        if (!producto) {
            return this.state.pedidos;
        }
        return this.state.pedidos.filter((pedido) => pedido.productos.includes(producto));
    }

    get nombreArticuloSeleccionado() {
        const articulo = this.state.articulos.find(
            (fila) => fila.id === this.state.articuloSeleccionado
        );
        return articulo ? articulo.articulo : "";
    }

    /** La columna del día del evento solo aporta cuando no es el día que se está mirando. */
    get columnasPedidos() {
        return this.state.modo === "evento" ? 8 : 9;
    }

    seleccionarArticulo(idArticulo) {
        this.state.articuloSeleccionado =
            this.state.articuloSeleccionado === idArticulo ? null : idArticulo;
    }

    quitarFiltroArticulo() {
        this.state.articuloSeleccionado = null;
    }

    cambiarVistaMaterial(vista) {
        this.state.vistaMaterial = vista;
        // Un artículo seleccionado que la nueva vista ya no muestra dejaría los pedidos
        // filtrados por algo que no se ve en ninguna parte.
        if (
            this.state.articuloSeleccionado
            && !this.articulosVisibles.some((fila) => fila.id === this.state.articuloSeleccionado)
        ) {
            this.state.articuloSeleccionado = null;
        }
    }

    // ------------------------------------------------------------------
    // Interacción
    // ------------------------------------------------------------------

    async seleccionarDia(clave) {
        this.state.diaSeleccionado = clave;
        await this.cargarDia(clave);
    }

    async cambiarModo(modo) {
        if (this.state.modo === modo) {
            return;
        }
        this.state.modo = modo;
        await Promise.all([this.cargarMes(), this.cargarDia(this.state.diaSeleccionado)]);
    }

    async cambiarMes(desplazamiento) {
        const referencia = new Date(this.state.anio, this.state.mes - 1 + desplazamiento, 1);
        this.state.anio = referencia.getFullYear();
        this.state.mes = referencia.getMonth() + 1;
        await this.cargarMes();
        // Si el día seleccionado se queda fuera del mes que se está mirando, los bloques de
        // abajo hablarían de un mes que el calendario ya no enseña.
        if (!this.state.diaSeleccionado.startsWith(this.prefijoMes)) {
            await this.seleccionarDia(aClaveDia(referencia));
        }
    }

    async irAHoy() {
        const hoy = new Date();
        this.state.anio = hoy.getFullYear();
        this.state.mes = hoy.getMonth() + 1;
        await this.cargarMes();
        await this.seleccionarDia(this.claveHoy);
    }

    abrirPedido(idPedido) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "sale.order",
            res_id: idPedido,
            views: [[false, "form"]],
            target: "current",
            context: { in_rental_app: 1 },
        });
    }

    /**
     * Abre los pedidos del día en una lista normal, para poder filtrar y exportar.
     *
     * El dominio lo arma Python: en los modos de almacén hay que convertir los límites del
     * día a UTC y esa conversión no debe estar duplicada aquí.
     */
    async verPedidosDelDia() {
        const accion = await this.orm.call(
            "sale.order",
            "enteza_panel_accion_lista",
            [this.state.diaSeleccionado, this.state.modo]
        );
        await this.action.doAction(accion);
    }

    /** Parte del día en PDF. Sale lo que se está viendo: si la vista es «Sobre venta», la
     *  hoja es la lista de lo que hay que comprar o subcontratar. */
    async imprimirParte() {
        const accion = await this.orm.call(
            "sale.order",
            "enteza_panel_imprimir",
            [
                this.state.diaSeleccionado,
                this.state.modo,
                this.state.vistaMaterial === "sobreventa",
            ]
        );
        await this.action.doAction(accion);
    }
}

registry.category("actions").add("enteza_panel_eventos.panel", PanelEventos);
