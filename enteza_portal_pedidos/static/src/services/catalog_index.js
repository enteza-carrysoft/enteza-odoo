/** @odoo-module **/

/**
 * Índices y normalización de texto sobre el catálogo del portal (PRP §9.3, §9.5).
 *
 * Todo esto se construye UNA VEZ al cargar el catálogo, no en cada pulsación: filtrar 1.025
 * productos por cuatro dimensiones a la vez solo es instantáneo si no se recalculan
 * normalizaciones de texto ni se recorre el catálogo entero por cada opción de cada
 * desplegable en cada repintado.
 */

// Rango Unicode de las marcas diacriticas combinantes (U+0300-U+036F). Escape \uXXXX
// explicito a proposito: un caracter combinante crudo dentro del fichero fuente es fragil
// (depende de que el editor/terminal que lo escriba no lo normalice), un escape ASCII no.
const DIACRITICOS = /[̀-ͯ]/g;

/** Minúsculas y sin acentos, para que «bambu» encuentre «Bambú» (PRP §9.3). */
export function normalizeText(texto) {
    return (texto || "")
        .toLowerCase()
        .normalize("NFD")
        .replace(DIACRITICOS, "");
}

export function searchWords(texto) {
    return normalizeText(texto).split(/\s+/).filter(Boolean);
}

/** `{productId: "silla bambu blanca sil-bam-01"}`, precalculado una sola vez. */
export function buildTextIndex(products) {
    const indice = new Map();
    for (const producto of products) {
        indice.set(producto.id, normalizeText(`${producto.name} ${producto.code}`));
    }
    return indice;
}

export function matchesText(producto, textIndex, palabras) {
    if (!palabras.length) {
        return true;
    }
    const pajar = textIndex.get(producto.id) || "";
    return palabras.every((palabra) => pajar.includes(palabra));
}

/** `{tagId: Set(productId...)}`, para contar opciones de faceta sin recorrer todo. */
export function buildTagIndex(products) {
    const indice = new Map();
    for (const producto of products) {
        for (const tagId of producto.tag_ids || []) {
            if (!indice.has(tagId)) {
                indice.set(tagId, new Set());
            }
            indice.get(tagId).add(producto.id);
        }
    }
    return indice;
}
