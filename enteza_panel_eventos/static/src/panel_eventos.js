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
    return (texto || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
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
            almacenes: [],
            totales: { pedidos: 0, borradores: 0, importe: "", unidades: 0, sobreventa: 0 },
            contadores: { evento: 0, salida: 0, devolucion: 0 },
            // Bloque de material: filtro por descripción y vista, como en la aplicación
            // anterior. `sobreventa` deja solo los artículos de los que no hay bastante.
            filtroArticulo: "",
            vistaMaterial: "consumos",
            // Un presupuesto sin confirmar todavía puede no ocurrir. Se ve por defecto —hay
            // que saber que está ahí— pero se puede quitar del material, de la sobreventa y
            // del parte, para no cargar un camión con lo que nadie ha vendido.
            soloConfirmados: false,
            // Fila de material pinchada (`'almacenId-productoId'`): filtra los pedidos.
            articuloSeleccionado: null,
            cargando: true,
            error: "",
        });

        onWillStart(() => this.recargar());
    }

    // ------------------------------------------------------------------
    // Carga de datos
    // ------------------------------------------------------------------

    /**
     * Envoltorio de toda carga: marca «cargando» y recoge el error.
     *
     * El error se guarda en `state.error` en vez de dejarlo subir. Una excepción dentro de
     * `onWillStart` deja la pantalla en blanco sin decir nada, y el panel se usa desde el
     * almacén: allí nadie va a abrir la consola del navegador para enterarse.
     *
     * El indicador lo lleva **solo** este método, no cada carga por su cuenta: si `cargarMes`
     * y `cargarDia` lo tocaran las dos, la primera en terminar lo apagaría con la otra aún en
     * vuelo y la pantalla diría que ya está cuando no lo está.
     */
    async _conCarga(trabajo) {
        this.state.cargando = true;
        this.state.error = "";
        try {
            await trabajo();
        } catch (error) {
            this.state.error = error.data?.message || error.message || String(error);
        } finally {
            this.state.cargando = false;
        }
    }

    /** Recarga el mes y el día a la vez: el modo y el interruptor afectan a los dos. */
    recargar() {
        return this._conCarga(
            () => Promise.all([this.cargarMes(), this.cargarDia(this.state.diaSeleccionado)])
        );
    }

    async cargarMes() {
        this.state.cargaMes = await this.orm.call(
            "sale.order",
            "enteza_panel_carga_mes",
            [this.state.anio, this.state.mes, this.state.modo, this.state.soloConfirmados]
        );
    }

    async cargarDia(clave) {
        // La selección de artículo es del día que se estaba mirando: al cambiar de día
        // apuntaría a un artículo que quizá ya no está en la lista.
        this.state.articuloSeleccionado = null;
        const datos = await this.orm.call(
            "sale.order",
            "enteza_panel_dia",
            [clave, this.state.modo, this.state.soloConfirmados]
        );
        this.state.pedidos = datos.pedidos;
        this.state.articulos = datos.articulos;
        this.state.almacenes = datos.almacenes;
        this.state.totales = datos.totales;
        this.state.contadores = datos.contadores;
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
            const pedidos = carga ? carga.pedidos : 0;
            celdas.push({
                dia,
                clave,
                pedidos,
                nivel: this.nivelCarga(pedidos),
                // El importe del día ya viene calculado: sirve para comparar dos sábados sin
                // tener que abrirlos uno a uno.
                titulo: pedidos
                    ? _t("%(pedidos)s pedidos · %(importe)s", {
                          pedidos,
                          importe: carga.importe,
                      })
                    : _t("Sin pedidos"),
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

    /**
     * La columna de almacén solo aparece si el día mezcla varios.
     *
     * Con un solo almacén repetiría el mismo valor en todas las filas y quitaría sitio a las
     * columnas que sí cambian. Hoy en `enteza26` solo el 2026-08-01 mezcla Sevilla y Jerez,
     * pero el cliente ha confirmado que habrá más almacenes.
     */
    get mostrarAlmacen() {
        return this.state.almacenes.length > 1;
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

    /** Unidades del material que se está viendo, no del día entero: el filtro también suma. */
    get unidadesVisibles() {
        return this.articulosVisibles.reduce((total, articulo) => total + articulo.unidades, 0);
    }

    /** La fila de material pinchada, o `undefined`. `state.articuloSeleccionado` es su clave. */
    get articuloActivo() {
        return this.state.articulos.find(
            (fila) => fila.clave === this.state.articuloSeleccionado
        );
    }

    /**
     * Pedidos de abajo, filtrados al artículo pinchado si lo hay.
     *
     * Se compara también el almacén: la misma referencia en Sevilla y en Jerez son dos filas
     * distintas del bloque de material, y pinchar la de Jerez no debe sacar los pedidos de
     * Sevilla.
     *
     * El filtro se hace aquí y no en el servidor porque cada pedido ya trae las unidades de
     * sus artículos: son decenas de pedidos como mucho y la respuesta tiene que ser inmediata.
     */
    get pedidosVisibles() {
        const articulo = this.articuloActivo;
        if (!articulo) {
            return this.state.pedidos;
        }
        const producto = String(articulo.producto_id);
        return this.state.pedidos.filter(
            (pedido) => pedido.almacen_id === articulo.almacen_id && pedido.productos[producto]
        );
    }

    /** Unidades del artículo seleccionado que lleva un pedido, para la columna «Uds.». */
    unidadesDelPedido(pedido) {
        const articulo = this.articuloActivo;
        return articulo ? pedido.productos[String(articulo.producto_id)] || 0 : 0;
    }

    /** Columnas de la tabla de pedidos, para el `colspan` de la fila de «no hay nada». */
    get columnasPedidos() {
        return 8
            + (this.state.modo === "evento" ? 0 : 1)
            + (this.mostrarAlmacen ? 1 : 0)
            + (this.articuloActivo ? 1 : 0);
    }

    get columnasMaterial() {
        return this.mostrarAlmacen ? 6 : 5;
    }

    seleccionarArticulo(clave) {
        this.state.articuloSeleccionado =
            this.state.articuloSeleccionado === clave ? null : clave;
    }

    quitarFiltroArticulo() {
        this.state.articuloSeleccionado = null;
    }

    cambiarVistaMaterial(vista) {
        this.state.vistaMaterial = vista;
        // Un artículo seleccionado que la nueva vista ya no muestra dejaría los pedidos
        // filtrados por algo que no se ve en ninguna parte.
        this.olvidarSeleccionInvisible();
    }

    /** Filtro por descripción. Si esconde la fila pinchada, deja de filtrar los pedidos. */
    alFiltrarArticulos(ev) {
        this.state.filtroArticulo = ev.target.value;
        this.olvidarSeleccionInvisible();
    }

    olvidarSeleccionInvisible() {
        if (
            this.state.articuloSeleccionado
            && !this.articulosVisibles.some(
                (fila) => fila.clave === this.state.articuloSeleccionado
            )
        ) {
            this.state.articuloSeleccionado = null;
        }
    }

    // ------------------------------------------------------------------
    // Interacción
    // ------------------------------------------------------------------

    seleccionarDia(clave) {
        this.state.diaSeleccionado = clave;
        return this._conCarga(() => this.cargarDia(clave));
    }

    async cambiarModo(modo) {
        if (this.state.modo === modo) {
            return;
        }
        this.state.modo = modo;
        await this.recargar();
    }

    /** Quita o devuelve los presupuestos sin confirmar. Afecta a los tres bloques y al parte. */
    async alternarSoloConfirmados() {
        this.state.soloConfirmados = !this.state.soloConfirmados;
        await this.recargar();
    }

    cambiarMes(desplazamiento) {
        const referencia = new Date(this.state.anio, this.state.mes - 1 + desplazamiento, 1);
        this.state.anio = referencia.getFullYear();
        this.state.mes = referencia.getMonth() + 1;
        return this._conCarga(async () => {
            await this.cargarMes();
            // Si el día seleccionado se queda fuera del mes que se está mirando, los bloques
            // de abajo hablarían de un mes que el calendario ya no enseña.
            if (!this.state.diaSeleccionado.startsWith(this.prefijoMes)) {
                this.state.diaSeleccionado = aClaveDia(referencia);
                await this.cargarDia(this.state.diaSeleccionado);
            }
        });
    }

    async irAHoy() {
        const hoy = new Date();
        this.state.anio = hoy.getFullYear();
        this.state.mes = hoy.getMonth() + 1;
        this.state.diaSeleccionado = this.claveHoy;
        await this.recargar();
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
            [this.state.diaSeleccionado, this.state.modo, this.state.soloConfirmados]
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
                this.state.soloConfirmados,
            ]
        );
        await this.action.doAction(accion);
    }
}

registry.category("actions").add("enteza_panel_eventos.panel", PanelEventos);
