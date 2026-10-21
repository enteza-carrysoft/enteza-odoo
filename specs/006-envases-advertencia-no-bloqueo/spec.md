# 006 — Cantidad no múltiplo del envase: advertencia, no bloqueo

## Context

La spec 005 (desplegada en `rental_custom` 19.0.1.19.0) rechaza al guardar una línea de alquiler cuya
cantidad no es múltiplo del envase del artículo. Medido en producción el 2026-10-22, un 4 % de las
líneas reales de alquiler con artículos con envase no son múltiplo, y eso afecta a un 46 % de los
pedidos creados desde agosto (el 43 % de los migrados). La aplicación `new-machu`, que importa a
Odoo por la API (`/json/2`, `create` de `sale.order` con sus líneas) los pedidos de alquiler que
vienen del sistema legacy, no envía unidad ni envase y manda la cantidad tal cual. Con la regla
actual, esos pedidos no se podrían importar.

Decisión del usuario (2026-10-22): la obligación de múltiplos se desactiva y queda como
**advertencia**, de momento, hasta que la empresa decida si realmente alquila siempre por envases
completos. No se modifica `new-machu`.

Alcance: `rental_custom` y `enteza_portal_pedidos`. Se mantiene el campo «Nº envases», la columna en
la lista de líneas y el desglose del parte de recogida (spec 005). Se mantiene también el rechazo de
una unidad de la línea distinta de la unidad base en artículos con envase (AC11 de la 005): la
integración nunca fija la unidad, y esa regla protege el precio.

## Acceptance Criteria

- [ ] AC1: Crear o modificar, por API o por pantalla, una línea de alquiler con un artículo con
  envase y una cantidad que no es múltiplo (30 uds con envase de 25) **no lanza error**: la línea se
  guarda y el pedido completo se crea igual que antes de la spec 005.
- [ ] AC2: En el formulario del pedido de alquiler, al elegir el artículo o cambiar la cantidad de una
  línea con artículo con envase y cantidad no múltiplo, aparece una advertencia no bloqueante con el
  texto «BOL BARCO (25): 30 uds no es múltiplo del envase de 25. Prueba con 25 o 50.»; el usuario
  puede guardar igualmente.
- [ ] AC3: No aparece advertencia con una cantidad múltiplo, en artículos sin envase, en líneas de
  venta normal ni en líneas de pedidos de faltas (`order_id.rental_order_id`).
- [ ] AC4: La restricción de unidad base se mantiene: una línea de alquiler de un artículo con envase
  con una unidad distinta de la base sigue rechazándose con el mensaje de la 005 (AC11), y las líneas
  existentes con otra unidad no se tocan.
- [ ] AC5: En el portal de clientes, guardar una cantidad no múltiplo no rechaza el guardado: se
  guarda lo tecleado y se muestra el aviso con el texto de AC2, como hacía el portal antes de la spec
  005. El envío de la solicitud tampoco se rechaza por este motivo.
- [ ] AC6: «Repetir pedido» en el portal ya no omite las líneas por no ser múltiplo: copia todas y, si
  alguna no lo es, avisa de cuáles.
- [ ] AC7: El campo «Nº envases», su columna en la lista de líneas y el desglose «Q uds (M envases de
  N)» del parte de recogida siguen funcionando igual que en la spec 005.
- [ ] AC8: Los tests de la 005 que afirman el rechazo por múltiplo (backend y portal) se reescriben
  para afirmar el nuevo comportamiento; la documentación (`USAGE.md`, `HISTORY.md`, README del
  portal) y las versiones de los manifiestos reflejan el cambio.

## Constraints

- No se toca `new-machu`, la integración sigue sin enviar contexto especial.
- Sin permisos, modelos ni rutas nuevas.
- Las pruebas se escriben pero no se pueden ejecutar en esta instancia (producción); se entregan
  validadas por sintaxis y no ejecutadas.
- Mensajes en castellano directamente en el código.
- Nada se despliega sin confirmación del usuario; commit y push se piden por separado.
- La obligación podrá volver a activarse más adelante con una spec nueva si la empresa lo decide.

## Target Odoo Version

19.0 Enterprise. Instancia: `enteza` (producción).
