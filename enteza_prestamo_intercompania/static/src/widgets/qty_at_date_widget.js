/** @odoo-module **/

/**
 * Añade al widget nativo de disponibilidad los campos del aviso de préstamo (PRP §10.3).
 *
 * No hay componente propio ni widget nuevo: el de alquiler es `qty_at_date` de `sale_stock`,
 * que `sale_stock_renting` ya extiende. Aquí se hace lo mismo un escalón más arriba, que es
 * mucho menos código y sobre todo mucho menos que mantener cuando Odoo lo cambie.
 *
 * Lo único que hace este fichero es declarar los campos: sin `fieldDependencies` el cliente
 * web no se los trae del servidor y la plantilla los vería vacíos, sin ningún error que lo
 * explique.
 */

import { patch } from "@web/core/utils/patch";
import { qtyAtDateWidget } from "@sale_stock/widgets/qty_at_date_widget";

patch(qtyAtDateWidget, {
    // 🔴 Hay que ARRASTRAR las dependencias que ya había, no fijar una lista nueva.
    // `patch` sustituye la propiedad entera, y `sale_stock_renting` mete aquí `start_date` y
    // `return_date`, de los que dependen las fechas que muestra el propio popover nativo
    // (`calcData.stock_start_date` / `stock_end_date`). Escribir la lista a pelo las borra y
    // rompe el widget de alquiler sin tocar una sola línea suya.
    //
    // El `spread` se evalúa cuando carga este fichero, que es DESPUÉS del de
    // `sale_stock_renting` porque este módulo depende de él: recoge su lista ya parcheada.
    fieldDependencies: [
        ...qtyAtDateWidget.fieldDependencies,
        { name: "enteza_falta", type: "float" },
        { name: "enteza_prestable_otra", type: "float" },
        { name: "enteza_origen_prestamo", type: "char" },
    ],
});
