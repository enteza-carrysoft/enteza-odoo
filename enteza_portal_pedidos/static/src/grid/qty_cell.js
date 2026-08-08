/** @odoo-module **/

import { Component, useState, onWillUpdateProps } from "@odoo/owl";

/**
 * Celda de cantidad de la rejilla (PRP §7, §9.5). Estado propio por fila -no en un objeto
 * global-, o cada pulsación repintaría las 1.025 filas.
 *
 * El aviso de caja se calcula en el navegador con la misma regla que el servidor (PRP §7):
 * redondeo al múltiplo más cercano; si no coincide con lo tecleado, se ofrecen los dos
 * redondeos. El servidor vuelve a validar en el envío -esto es solo para no hacer esperar
 * al cliente hasta ese momento para saberlo.
 */
export class QtyCell extends Component {
    static template = "enteza_portal_pedidos.QtyCell";
    static props = {
        productId: { type: Number },
        qty: { type: Number },
        box: { type: Number, optional: true },
        disabled: { type: Boolean, optional: true },
        onChange: { type: Function },
    };

    setup() {
        this.state = useState({ texto: this._formatear(this.props.qty) });
        this._editando = false;
        onWillUpdateProps((siguiente) => {
            if (!this._editando && siguiente.qty !== this.props.qty) {
                this.state.texto = this._formatear(siguiente.qty);
            }
        });
    }

    _formatear(qty) {
        return qty ? String(qty).replace(".", ",") : "";
    }

    _parsear(texto) {
        const limpio = (texto || "").replace(",", ".").trim();
        const valor = parseFloat(limpio);
        return Number.isFinite(valor) && valor > 0 ? valor : 0;
    }

    get box() {
        return this.props.box || 0;
    }

    /** `null` si la cantidad tecleada ya es múltiplo de caja completa. */
    get avisoCaja() {
        const qty = this._parsear(this.state.texto);
        if (!this.box || !qty) {
            return null;
        }
        const cajasCercano = Math.round(qty / this.box);
        if (Math.abs(cajasCercano * this.box - qty) < 1e-6) {
            return null;
        }
        const cajasAbajo = Math.floor(qty / this.box);
        const cajasArriba = Math.ceil(qty / this.box);
        return {
            abajo: cajasAbajo * this.box,
            arriba: cajasArriba * this.box,
            cajasAbajo,
            cajasArriba,
        };
    }

    onFocus() {
        this._editando = true;
    }

    onInput(ev) {
        // Solo dígitos, coma y punto (PRP §9.5): rechaza el resto en vez de aceptarlo y
        // fallar más tarde al parsear.
        this.state.texto = ev.target.value.replace(/[^0-9.,]/g, "");
    }

    onBlur() {
        this._editando = false;
        this._confirmar();
    }

    onKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this._confirmar();
            this._moverFila(1);
        } else if (ev.key === "Escape") {
            ev.preventDefault();
            this.state.texto = this._formatear(this.props.qty);
            ev.target.blur();
        } else if (ev.key === "ArrowDown") {
            ev.preventDefault();
            this._confirmar();
            this._moverFila(1);
        } else if (ev.key === "ArrowUp") {
            ev.preventDefault();
            this._confirmar();
            this._moverFila(-1);
        }
    }

    _confirmar() {
        const qty = this._parsear(this.state.texto);
        if (qty !== this.props.qty) {
            this.props.onChange(this.props.productId, qty);
        }
    }

    /** Navegación de teclado ↑/↓ (PRP §9.5): a la fila visible anterior/siguiente. */
    _moverFila(delta) {
        const fila = document.activeElement && document.activeElement.closest("tr");
        if (!fila) {
            return;
        }
        const destino = delta > 0 ? fila.nextElementSibling : fila.previousElementSibling;
        const input = destino && destino.querySelector(".enteza_qty_input");
        if (input) {
            input.focus();
            input.select();
        }
    }

    aplicarRedondeo(valor) {
        this.state.texto = this._formatear(valor);
        this.props.onChange(this.props.productId, valor);
    }
}
