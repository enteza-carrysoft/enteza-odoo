# Spec 002-faltas-desde-pedido

<!-- mode: create. This file becomes IMMUTABLE once approved (READ_SPEC gate). -->

## Context

Enteza no gestiona el almacén físico en Odoo: los pedidos se imprimen y se gestionan en papel.
Las existencias solo se tocan con ajustes de inventario (altas al comprar, bajas por faltas).
Los albaranes de alquiler no se validan nunca y falsean toda la disponibilidad (518 albaranes
pasados abiertos, medido el 2026-10-07). Decisión del usuario (2026-10-07), «opción A»:
desactivar el ajuste «Traslado de alquiler» (`group_rental_stock_picking`) para que los
pedidos nuevos no generen albaranes.

Hoy las faltas se facturan desde el albarán de recogida (`rental_custom`, botón «Facturar las
Faltas» en `stock.picking`). Sin albaranes, ese camino desaparece para los pedidos nuevos.
Hace falta un camino equivalente **desde el propio pedido de alquiler**, que conviva con el
del albarán. Así, volver a usar albaranes en el futuro es solo reactivar el ajuste.

Decisiones del usuario (2026-10-07):
- (b) Al **confirmar** el pedido de faltas creado por este camino, su albarán de salida se
  valida solo: la baja del material queda hecha y enlazada a la factura. La baja manual de
  esas unidades deja de hacerse.
- El pedido de alquiler pasa a **Devuelto** al registrar las faltas.
- El botón lo puede usar cualquier usuario de ventas.

## Acceptance Criteria

- [ ] AC1: Un pedido de alquiler confirmado (`state = 'sale'`) **sin albaranes abiertos**
  (ninguno fuera de `done`/`cancel`) muestra el botón «Registrar faltas». Si tiene algún
  albarán abierto, el botón no se muestra y el método rechaza la acción con un mensaje que
  remite al albarán.
- [ ] AC2: El asistente lista una fila por línea de alquiler de producto `type = 'consu'`, con
  producto, cantidad alquilada, faltas ya facturadas (`qty_lost`) y una columna «Faltas»
  editable que empieza en 0.
- [ ] AC3: Con alguna falta > 0, «Facturar las faltas» crea un pedido de venta con la misma
  cabecera que crea hoy el camino del albarán: mismo cliente de facturación, compañía,
  `origin`, `rental_order_id`, diario de faltas de la compañía, `is_rental_order = False`,
  `event_date`, líneas `is_rental = False` sin `price_unit` forzado. Abre ese pedido en
  borrador y deja mensaje en el historial de los dos pedidos.
- [ ] AC4: Las faltas se suman a `qty_lost` de cada línea. No se pueden registrar más faltas
  que `product_uom_qty - qty_lost` (error claro y no se crea nada). Se puede repetir en varias
  tandas.
- [ ] AC5: Tras registrar (con o sin faltas), todas las líneas de alquiler del pedido quedan
  con `qty_delivered = qty_returned = product_uom_qty`, y el pedido en
  `rental_status = 'returned'`. Con todas las faltas a 0 no se crea pedido de faltas: solo se
  marca como devuelto y se deja un mensaje.
- [ ] AC6: Al confirmar un pedido de faltas creado por este camino, sus albaranes de salida
  quedan en `done` con la cantidad pedida, aunque quien confirma no tenga permisos de
  almacén. Un pedido de faltas creado desde el albarán o por importación CSV **no** se valida
  solo (comportamiento actual sin cambios).
- [ ] AC7: El camino del albarán («Facturar las Faltas» en `stock.picking`) se comporta igual
  que antes: las pruebas existentes de `test_facturar_faltas.py` siguen siendo válidas sin
  modificarlas.
- [ ] AC8: El valor que devuelve `sale.order.action_confirm` se propaga tal cual (si la
  cadena devuelve una acción, sigue llegando al navegador).
- [ ] AC9: El asistente es accesible para `sales_team.group_sale_salesman`; un usuario
  interno sin ese grupo no puede crearlo (ACL).
- [ ] AC10: El módulo pasa `odoo_validate`, `validar_vistas.py` y `validar_modulo.py`.

## Constraints

- Odoo 19.0 Enterprise (`sale_renting`, `sale_stock_renting`). `enteza` es **producción**,
  sin staging ni `--test-enable`: las pruebas se escriben y **no se ejecutan**. El plugin no
  muta la instancia.
- Con el ajuste apagado, escribir `qty_delivered`/`qty_returned` en una línea de alquiler hace
  que el nativo cree movimientos `done` stock ↔ ubicación de alquiler (código de la 18 EE,
  `sale_stock_renting`, `_write_rental_lines`). Es el mecanismo previsto y queda registrado
  como movimientos del pedido. Con el ajuste encendido, el nativo solo escribe los campos.
- Solo lógica aditiva: el camino del albarán no se reescribe. La construcción de la cabecera
  del pedido de faltas se comparte entre los dos caminos (DRY), sin cambiar su resultado.
- Versión `19.0.1.15.0` → `19.0.1.16.0`. Despliegue manual con confirmación del usuario.
- Textos en castellano, sin traducciones.

## Target Odoo Version

19.0
