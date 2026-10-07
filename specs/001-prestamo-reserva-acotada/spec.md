# Spec 001-prestamo-reserva-acotada

<!-- mode: bug. This file becomes IMMUTABLE once approved (READ_SPEC gate). -->

## Context

Módulo `enteza_prestamo_intercompania` (instalado en `enteza`, versión 19.0.10.0.3). Al
confirmar un pedido de alquiler que el almacén propio no puede servir, el diálogo «Falta
material para este pedido» propone reservar material de otra compañía del grupo.

**Fallo principal, medido por RPC el 2026-10-07** con el pedido id 2648 (`11250529`,
Stileum, almacén Jerez, alquiler el 2026-10-02): en 42 líneas el pedido pide 4.265 unidades y
el diálogo propone reservar 20.381 en Sevilla (Vimaple). Ejemplo: `[2626] VASO MACETA MAXI
50CL`, se piden 400, `enteza_falta` = 5.280. Causa: `enteza_falta = cantidad - disponible -
cubierto`, y `disponible` es negativo (−4.880) cuando otros pedidos confirmados del mismo
almacén ya superan sus existencias. El pedido nuevo hereda el déficit de todos los demás y
bloquea en la prestamista material que no necesita.

Fallos adicionales detectados en la revisión del módulo, incluidos por decisión del usuario:

1. Cancelar un préstamo **aprobado** (`action_cancelar`) deja vivos sus dos albaranes: el
   almacén podría mover material de un préstamo anulado.
2. **Entregas parciales**: el backorder de un albarán del préstamo pierde `enteza_loan_id`
   (y sus movimientos, `enteza_loan_line_id`), porque ambos campos son `copy=False`. Lo
   enviado en el backorder nunca se suma a `qty_sent` y la devolución propone de menos.
   Además `qty_sent` se sobrescribe en vez de acumularse.
3. **Devolución duplicada**: proponer la devolución dos veces antes de recibir la primera
   genera albaranes por más de lo pendiente, porque `qty_pending` solo baja al recibir.
4. Menores: el mensaje de `_revalidar_disponibilidad` puede decir «solo hay -50 libres»;
   `tests/test_buscador_producto.py` no está registrado en `tests/__init__.py` y no se
   ejecuta nunca.

Decisión del usuario (2026-10-07): un pedido cuyo alquiler **ya ha empezado** no propone
préstamo: el traslado ya no puede ocurrir.

## Acceptance Criteria

- [ ] AC1: En una línea de alquiler, `enteza_falta` nunca supera `product_uom_qty` menos lo ya
  cubierto por préstamos de esa línea. Con disponible negativo en el almacén propio (otros
  pedidos confirmados ya lo superan), una línea de 400 uds tiene `enteza_falta` = 400.
- [ ] AC2: Con disponible positivo pero insuficiente, el cálculo no cambia: 80 libres y
  95 pedidas → `enteza_falta` = 15 (comportamiento actual conservado).
- [ ] AC3: Al aceptar el diálogo, la cantidad reservada en cada línea de préstamo
  (`qty_reserved`) es ≤ `product_uom_qty` de su línea de pedido.
- [ ] AC4: `enteza.disponibilidad.deficit()` devuelve como máximo la cantidad pedida para cada
  producto, aunque el disponible sea negativo; el mensaje de `_revalidar_disponibilidad`
  nunca muestra una cantidad libre negativa.
- [ ] AC5: Confirmar un pedido cuyas líneas con déficit tienen todas `start_date` ≤ ahora
  confirma directamente, sin abrir el diálogo ni crear préstamos. Si el pedido mezcla líneas
  ya empezadas y futuras, el diálogo solo incluye las futuras.
- [ ] AC6: `action_cancelar` sobre un préstamo `approved` deja en `cancel` sus albaranes de
  ida que no estén `done`, además de pasar el préstamo a `cancelled`.
- [ ] AC7: Validar parcialmente el albarán de salida con backorder: el backorder conserva
  `enteza_loan_id` y sus movimientos `enteza_loan_line_id`; `qty_sent` refleja lo validado;
  al validar después el backorder, `qty_sent` suma lo nuevo (total = lo enviado en ambos).
- [ ] AC8: Con una devolución propuesta y aún no recibida por la prestamista, proponer otra
  devolución solo ofrece lo no comprometido ya en devoluciones en curso; si no queda nada,
  avisa. Aceptar un asistente no genera albaranes por encima de lo realmente devolvible en
  ese momento.
- [ ] AC9: `tests/test_buscador_producto.py` está importado en `tests/__init__.py`.
- [ ] AC10: Sin cambios de seguridad: mismos grupos, ACL y reglas; el módulo pasa
  `odoo_validate` y los validadores del repositorio (`validar_vistas.py`,
  `validar_modulo.py`).

## Constraints

- Odoo 19.0 Enterprise (`sale_renting`, `sale_stock_renting`). Instancia `enteza` =
  **producción**, sin staging ni `--test-enable`: las pruebas se escriben pero **no se pueden
  ejecutar**; se entregan validadas por sintaxis. El plugin no muta la instancia.
- Despliegue manual (commit → push → `invoke git-aggregate` → actualizar módulo), con
  confirmación del usuario en cada paso. Commits nunca automáticos.
- Sin cambios de esquema que exijan migración de datos; versión del manifiesto a 19.0.10.1.0.
- No se tocan préstamos existentes en producción. Los préstamos ya reservados con
  cantidades infladas (si los hay) se revisan aparte, con aprobación humana.
- Textos en castellano, sin traducciones.

## Target Odoo Version

19.0
