/** @odoo-module **/

import { Component, useRef, onMounted, onWillUpdateProps, onWillUnmount, useState } from "@odoo/owl";

const DEBOUNCE_AVISO_MS = 300;

/**
 * Celda de cantidad de la rejilla (PRP §7, §9.5; PRP v2 §5.1, F2).
 *
 * 🔴 Input NO controlado: es la causa directa de uno de los tres síntomas reportados
 * ("se renderiza otra vez mientras introduzco unidades"). Con `t-att-value="state.texto"`
 * ligado a estado reactivo, Owl volvía a escribir el valor en el DOM en cada tecla y el
 * cursor saltaba al final -insertar un dígito en medio de "100" era imposible. Aquí el
 * valor del `<input>` lo lee/escribe el DOM directamente (`t-ref`); Owl solo entra a
 * tocarlo cuando la fila NO está en edición (`onWillUpdateProps`), es decir, cuando el
 * cambio viene de fuera (el servidor confirmó otra cantidad, o se pulsó un redondeo).
 *
 * El aviso de caja ya no se recalcula en cada `onInput`: se difiere 300 ms tras la última
 * tecla y siempre se confirma en `blur`, así que no aparece y desaparece bajo el input
 * letra a letra. Vive en un contenedor de altura reservada (SCSS) para que la fila no
 * cambie de alto mientras se teclea.
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
        this.inputRef = useRef("input");
        this.state = useState({ aviso: null });
        this._editando = false;
        this._avisoTimer = null;

        onMounted(() => {
            this._pintar(this.props.qty);
        });
        onWillUpdateProps((siguiente) => {
            if (!this._editando && siguiente.qty !== this.props.qty) {
                this._pintar(siguiente.qty);
            }
        });
        onWillUnmount(() => clearTimeout(this._avisoTimer));
    }

    _pintar(qty) {
        if (this.inputRef.el) {
            this.inputRef.el.value = this._formatear(qty);
        }
        this.state.aviso = null;
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

    _calcularAviso(qty) {
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
        // fallar más tarde al parsear. Se corrige el propio DOM, no un estado reactivo.
        const limpio = ev.target.value.replace(/[^0-9.,]/g, "");
        if (limpio !== ev.target.value) {
            ev.target.value = limpio;
        }
        clearTimeout(this._avisoTimer);
        this._avisoTimer = setTimeout(() => {
            this.state.aviso = this._calcularAviso(this._parsear(this.inputRef.el.value));
        }, DEBOUNCE_AVISO_MS);
    }

    onBlur() {
        this._editando = false;
        clearTimeout(this._avisoTimer);
        this._confirmar();
    }

    onKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this._confirmar();
            this._moverFila(1);
        } else if (ev.key === "Escape") {
            ev.preventDefault();
            this._pintar(this.props.qty);
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
        const qty = this._parsear(this.inputRef.el.value);
        this.state.aviso = this._calcularAviso(qty);
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
        this._pintar(valor);
        this.props.onChange(this.props.productId, valor);
    }
}
