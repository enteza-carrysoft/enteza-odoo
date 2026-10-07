# Spec 003-aviso-faltas-canceladas

<!-- mode: bug. This file becomes IMMUTABLE once approved (READ_SPEC gate). -->

## Context

El formulario de alquiler (`rental_custom`) muestra un aviso amarillo «Hay material de este
alquiler no devuelto, facturado como venta en: …» siempre que `compensation_order_ids` no
está vacío. Ese One2many (`sale.order.rental_order_id`) incluye también los pedidos de faltas
**cancelados**. Visto el 2026-10-07: el alquiler 41255027 sigue enseñando el aviso con
S00379, que se canceló tras la prueba.

## Acceptance Criteria

- [ ] AC1: `compensation_order_ids` excluye los pedidos en `state = 'cancel'`. Con un único
  pedido de faltas cancelado, el campo queda vacío y el aviso no se muestra. Con uno cancelado
  y otro vivo, el aviso solo muestra el vivo.
- [ ] AC2: Nada más cambia: `rental_order_id` del pedido de faltas se conserva, las pruebas
  existentes de `test_faltas_desde_pedido.py` y `test_facturar_faltas.py` siguen válidas y el
  módulo pasa `odoo_validate`, `validar_vistas.py` y `validar_modulo.py`.

## Constraints

- Odoo 19.0 EE, producción sin `--test-enable`: prueba escrita y no ejecutada.
- Solo un `domain` en la definición del campo; sin cambios de esquema. Versión
  `19.0.1.16.0` → `19.0.1.16.1`.

## Target Odoo Version

19.0
