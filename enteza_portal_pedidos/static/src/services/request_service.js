/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";

/**
 * Capa de llamadas al backend del portal (PRP §8.2; PRP v2 §2.2, F1).
 *
 * 🔴 Ya no hay cola de cambios por línea ni bloqueo optimista por `write_date`: el backend
 * reconcilia el CESTO COMPLETO en cada `guardar`/`enviar` (§9 del PRP v2), así que repetir
 * la misma llamada dos veces no duplica nada. Esto elimina la causa raíz de dos de los tres
 * síntomas reportados: el bloqueo que se autoinvalidaba solo (crear una línea podía tocar
 * la cabecera vía `_rental_set_dates` y mover el candado que la propia petición usaba) y la
 * pérdida de cantidades cuando el guardado fallaba a medio camino (`_cambiosPendientes` se
 * vaciaba ANTES de saber si el POST había funcionado).
 *
 * Ninguna llamada de este fichero lanza: todas devuelven `{ok: true, ...}` o
 * `{ok: false, error, error_code}`. El componente que llama decide qué hacer con el
 * fallo -nunca hay una promesa rechazada sin atender (PRP v2 §5.5).
 */
const DEBOUNCE_DISPONIBILIDAD_MS = 400;
const LOTE_DISPONIBILIDAD = 50;

export class RequestService {
    constructor(orderId) {
        this.orderId = orderId;
        this._enVuelo = null; // Promise de la escritura en curso, o null.
        this._pendiente = null; // último `{header, lines, customerNote}` a enviar tras la actual.
        this._dispDebounceTimer = null;
    }

    async _rpcSeguro(ruta, params) {
        try {
            const resultado = await rpc(ruta, params);
            if (resultado && resultado.error) {
                return { ok: false, error: resultado.error, error_code: resultado.error_code };
            }
            return { ok: true, ...resultado };
        } catch (excepcion) {
            console.error(excepcion); // eslint-disable-line no-console
            return {
                ok: false,
                error: "No se ha podido conectar con el servidor. Comprueba tu conexión e "
                    + "inténtalo de nuevo.",
                error_code: 'red',
            };
        }
    }

    catalogo() {
        return this._rpcSeguro("/enteza_portal/solicitud/catalogo", { order_id: this.orderId });
    }

    /**
     * Guarda el cesto completo. Serializa las escrituras: si ya hay una en vuelo, la
     * siguiente no se dispara en paralelo -se coalesce con la más reciente y se envía en
     * cuanto la anterior termine, así nunca hay dos escrituras compitiendo por reconciliar
     * el mismo pedido a la vez.
     */
    async guardar({ header = null, lines = null, customerNote = null } = {}) {
        const payload = { header, lines, customer_note: customerNote };
        if (this._enVuelo) {
            this._pendiente = payload;
            return this._enVuelo.then(() => this._enVuelo);
        }
        return this._ejecutarGuardado(payload);
    }

    async _ejecutarGuardado(payload) {
        this._enVuelo = this._rpcSeguro("/enteza_portal/solicitud/guardar", {
            order_id: this.orderId,
            header: payload.header,
            lines: payload.lines,
            customer_note: payload.customer_note,
        });
        const resultado = await this._enVuelo;
        this._enVuelo = null;
        if (this._pendiente) {
            const siguiente = this._pendiente;
            this._pendiente = null;
            return this._ejecutarGuardado(siguiente);
        }
        return resultado;
    }

    guardadoPendiente() {
        return Boolean(this._enVuelo || this._pendiente);
    }

    enviar({ header = null, lines = null, customerNote = null } = {}) {
        return this._rpcSeguro("/enteza_portal/solicitud/enviar", {
            order_id: this.orderId,
            header,
            lines,
            customer_note: customerNote,
        });
    }

    cancelar() {
        return this._rpcSeguro("/enteza_portal/solicitud/cancelar", { order_id: this.orderId });
    }

    /**
     * Disponibilidad por lotes (PRP §6.2), con *debounce* de 400 ms: un cambio de filtro no
     * dispara varios lotes seguidos sin pausa. `items` es `[{productId, qty}]` -la cantidad
     * tecleada, no la de base de datos: con guardado diferido puede no estar escrita
     * todavía (PRP v2 §9).
     */
    disponibilidad(items) {
        clearTimeout(this._dispDebounceTimer);
        return new Promise((resolve) => {
            this._dispDebounceTimer = setTimeout(async () => {
                resolve(await this._disponibilidadAhora(items));
            }, DEBOUNCE_DISPONIBILIDAD_MS);
        });
    }

    async _disponibilidadAhora(items) {
        if (!items.length) {
            return { ok: true, colors: {} };
        }
        const colores = {};
        for (let i = 0; i < items.length; i += LOTE_DISPONIBILIDAD) {
            const lote = items.slice(i, i + LOTE_DISPONIBILIDAD).map(
                ({ productId, qty }) => ({ product_id: productId, qty }));
            const resultado = await this._rpcSeguro(
                "/enteza_portal/solicitud/disponibilidad",
                { order_id: this.orderId, items: lote },
            );
            if (!resultado.ok) {
                return resultado;
            }
            Object.assign(colores, resultado.colors);
        }
        return { ok: true, colors: colores };
    }
}
