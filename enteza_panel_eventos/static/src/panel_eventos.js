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
            diaSeleccionado: this.claveHoy,
            cargaMes: {},
            pedidos: [],
            articulos: [],
            totales: { pedidos: 0, importe: "" },
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
            [this.state.anio, this.state.mes]
        );
    }

    async cargarDia(clave) {
        this.state.cargando = true;
        try {
            const datos = await this.orm.call("sale.order", "enteza_panel_dia", [clave]);
            this.state.pedidos = datos.pedidos;
            this.state.articulos = datos.articulos;
            this.state.totales = datos.totales;
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

    get nombreMes() {
        return `${MESES[this.state.mes - 1]} ${this.state.anio}`;
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

    /**
     * Intensidad del color de un día según cuántos pedidos tenga.
     *
     * Los cortes (3 y 6) son una primera aproximación pensada para el negocio de Enteza, muy
     * concentrado en fines de semana. Conviene ajustarlos cuando haya datos reales de carga.
     */
    nivelCarga(pedidos) {
        if (!pedidos) {
            return 0;
        }
        if (pedidos < 3) {
            return 1;
        }
        return pedidos < 6 ? 2 : 3;
    }

    // ------------------------------------------------------------------
    // Interacción
    // ------------------------------------------------------------------

    async seleccionarDia(clave) {
        this.state.diaSeleccionado = clave;
        await this.cargarDia(clave);
    }

    async cambiarMes(desplazamiento) {
        const referencia = new Date(this.state.anio, this.state.mes - 1 + desplazamiento, 1);
        this.state.anio = referencia.getFullYear();
        this.state.mes = referencia.getMonth() + 1;
        await this.cargarMes();
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

    /** Abre los pedidos del día en una lista normal, para poder filtrar y exportar. */
    verPedidosDelDia() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Pedidos del día"),
            res_model: "sale.order",
            domain: [
                ["is_rental_order", "=", true],
                ["state", "!=", "cancel"],
                ["event_date", "=", this.state.diaSeleccionado],
            ],
            views: [[false, "list"], [false, "form"]],
            target: "current",
            context: { in_rental_app: 1 },
        });
    }
}

registry.category("actions").add("enteza_panel_eventos.panel", PanelEventos);
