# 007 — Aviso de envase: indicador de color en la línea, sin ventana emergente

## Context

La spec 006 convirtió en advertencia (onchange con ventana emergente) la cantidad no múltiplo del
envase. En uso real, al elegir un artículo con envase en la línea del pedido la cantidad vale 1 por
defecto, que casi nunca es múltiplo, así que la ventana salta al añadir cada línea y el comercial
tiene que aceptarla cada vez (observado por el usuario el 2026-10-22).

Decisión del usuario: se elimina la ventana y el aviso pasa a ser visual, en la propia línea.

Alcance: `rental_custom` (modelo y vista de la lista de líneas del pedido de alquiler). No cambia el
comportamiento por API, la restricción de unidad base, el campo «Nº envases», el parte de recogida ni
el portal.

## Acceptance Criteria

- [ ] AC1: Elegir un artículo con envase en una línea de alquiler, o cambiar su cantidad, no muestra
  ninguna ventana emergente ni advertencia modal (el onchange de la spec 006 desaparece).
- [ ] AC2: En la lista de líneas del pedido de alquiler, la celda «Nº envases» se muestra con el color
  de advertencia (naranja) cuando la línea es de alquiler, el artículo tiene envase y la cantidad no
  es múltiplo del envase (p. ej. 1 ud con envase de 25 → 0,04 en naranja).
- [ ] AC3: La celda no se colorea con una cantidad múltiplo (50 → 2), en artículos sin envase, en
  líneas de venta normal, en secciones y notas ni en líneas de pedidos de faltas
  (`order_id.rental_order_id`).
- [ ] AC4: El indicador usa la misma comparación que la regla de la 006 (respeta la precisión de la
  unidad: 25,0000001 con envase de 25 no se colorea) y es un campo calculado, no almacenado, sin
  `inverse`, de solo lectura y sin `sudo`.
- [ ] AC5: Pasar el ratón sobre la cabecera de la columna «Nº envases» explica el significado: cuántos
  envases hay en la línea y que el naranja indica una cantidad que no es múltiplo del envase.
- [ ] AC6: Por API (`create`, `write`, `copy`) una cantidad no múltiplo sigue guardándose sin error, y
  la restricción de unidad base de la spec 005 (AC11) se mantiene sin cambios.
- [ ] AC7: El portal, el parte de recogida y el campo «Nº envases» no cambian.
- [ ] AC8: Los tests de la spec 006 que afirman el aviso del onchange se reescriben para afirmar que
  no hay aviso y que el indicador es correcto; `USAGE.md`, `HISTORY.md` y el manifiesto
  (`rental_custom` 19.0.1.21.0) reflejan el cambio.

## Constraints

- Sin permisos, modelos, ACL ni rutas nuevas.
- No se modifica `enteza_portal_pedidos`.
- Las pruebas se escriben pero no se pueden ejecutar en esta instancia (producción); se entregan
  validadas por sintaxis y no ejecutadas. El color solo se comprueba en pantalla tras desplegar.
- Textos en castellano directamente en el código.
- Nada se despliega sin confirmación; commit y push se piden por separado.

## Target Odoo Version

19.0 Enterprise. Instancia: `enteza` (producción).
