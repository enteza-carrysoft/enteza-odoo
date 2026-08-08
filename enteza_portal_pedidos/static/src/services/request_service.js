/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";

/**
 * Capa de llamadas al backend del portal (PRP §8.2): agrupa las escrituras de línea con
 * *debounce* y trocea la disponibilidad en lotes de 50 (PRP §6.2) para que la rejilla nunca
 * mande al servidor ni el catálogo entero de golpe ni una petición por tecla.
 */
const DEBOUNCE_LINEAS_MS = 600;
const LOTE_DISPONIBILIDAD = 50;

export class RequestService {
    constructor(orderId) {
        this.orderId = orderId;
        this._cambiosPendientes = new Map(); // productId -> qty
        this._flushTimer = null;
    }

    catalogo() {
        return rpc("/enteza_portal/solicitud/catalogo", { order_id: this.orderId });
    }

    cabecera(vals, expectedWriteDate) {
        return rpc("/enteza_portal/solicitud/cabecera", {
            order_id: this.orderId,
            expected_write_date: expectedWriteDate,
            ...vals,
        });
    }

    /**
     * Encola un cambio de cantidad y programa el envío agrupado (PRP §9.5): así 100
     * pulsaciones seguidas en la rejilla no generan 100 peticiones, solo una tras el último
     * cambio. Si el componente necesita el resultado antes (por ejemplo, al enviar la
     * solicitud), usar `flushLineasAhora`.
     */
    encolarCambioLinea(productId, qty, expectedWriteDate, onResultado) {
        this._cambiosPendientes.set(productId, qty);
        clearTimeout(this._flushTimer);
        this._flushTimer = setTimeout(() => {
            this.flushLineasAhora(expectedWriteDate).then((resultado) => {
                if (resultado && onResultado) {
                    onResultado(resultado);
                }
            });
        }, DEBOUNCE_LINEAS_MS);
    }

    async flushLineasAhora(expectedWriteDate) {
        clearTimeout(this._flushTimer);
        if (!this._cambiosPendientes.size) {
            return null;
        }
        const changes = Array.from(this._cambiosPendientes, ([product_id, qty]) => ({
            product_id,
            qty,
        }));
        this._cambiosPendientes.clear();
        return rpc("/enteza_portal/solicitud/lineas", {
            order_id: this.orderId,
            changes,
            expected_write_date: expectedWriteDate,
        });
    }

    hayPendientes() {
        return this._cambiosPendientes.size > 0;
    }

    /** Disponibilidad por lotes (PRP §6.2). Nunca pide más de 50 productos de una vez. */
    async disponibilidad(productIds) {
        if (!productIds.length) {
            return {};
        }
        const resultado = {};
        for (let i = 0; i < productIds.length; i += LOTE_DISPONIBILIDAD) {
            const lote = productIds.slice(i, i + LOTE_DISPONIBILIDAD);
            const parcial = await rpc("/enteza_portal/solicitud/disponibilidad", {
                order_id: this.orderId,
                product_ids: lote,
            });
            Object.assign(resultado, parcial);
        }
        return resultado;
    }

    enviar(customerNote, expectedWriteDate) {
        return rpc("/enteza_portal/solicitud/enviar", {
            order_id: this.orderId,
            customer_note: customerNote,
            expected_write_date: expectedWriteDate,
        });
    }

    cancelar() {
        return rpc("/enteza_portal/solicitud/cancelar", { order_id: this.orderId });
    }
}
