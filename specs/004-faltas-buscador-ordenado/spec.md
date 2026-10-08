# Spec 004-faltas-buscador-ordenado

<!-- mode: create. This file becomes IMMUTABLE once approved (READ_SPEC gate). -->

## Context

«Registrar faltas» (`rental.missing.wizard`, `rental_custom` 19.0.1.16.1) muestra una línea por
artículo de alquiler del pedido, en orden de creación, dentro de un diálogo. Lo habitual son
muchas líneas y pocas faltas, y el usuario copia las faltas de un papel que las identifica por
la **referencia interna** del artículo. Hoy hay que recorrer la lista a ojo.

Datos medidos por RPC el 2026-10-08:
- Las 1.029 referencias de material de alquiler (`rent_ok`, `type='consu'`) son numéricas de
  4 cifras; 46 artículos no tienen referencia.
- Líneas de material por pedido de alquiler confirmado: mediana 34, p90 71, máximo 94.
  **742 de 1.589 pedidos superan las 40 líneas**, que es el tamaño de página por defecto de una
  lista dentro de un formulario: el resto queda en una segunda página.

Código del cliente web leído en `odoo/odoo` rama 19.0
(`web/static/src/views/list/list_renderer.js`): en una lista editable, mientras se edita una
casilla, Intro baja a la fila siguiente, pero **las flechas arriba/abajo no hacen nada**.

Glosario: «aplicar el valor» = el valor queda en la línea **en el cliente**, sin llamada de
escritura al servidor; todo se envía al pulsar «Facturar las faltas», como hoy.

## Acceptance Criteria

- [ ] AC1: Al abrir «Registrar faltas», las líneas se crean en el servidor ordenadas por
  referencia interna ascendente (comparación de texto), con desempate por id de la línea del
  pedido. Las líneas sin referencia van al final, ordenadas por nombre del producto.
- [ ] AC2: La lista tiene una columna «Referencia» (related no almacenado a
  `product_id.default_code` en la línea transitoria, solo lectura), antes del producto, y la
  columna del producto muestra el nombre sin la referencia entre corchetes.
- [ ] AC3: Todas las líneas del pedido se ven en una sola página, sin paginador: la lista del
  asistente declara `limit` de al menos 500.
- [ ] AC4: Encima de la lista hay un buscador. Al teclear, solo se ven las filas cuya
  referencia **empieza** por el texto o cuyo nombre de producto (sin la referencia) lo
  **contiene**, sin distinguir mayúsculas ni acentos. Con el buscador vacío se ven todas. El
  filtrado es en el cliente, sin RPC.
- [ ] AC5: Intro en el buscador, con al menos una fila visible, pone en edición la casilla
  «Faltas» de la primera fila visible. Sin filas visibles, no hace nada.
- [ ] AC6: Con texto en el buscador, Intro en «Faltas» aplica el valor, vacía el buscador y
  devuelve el foco a él. Con el buscador vacío, Intro conserva el comportamiento nativo (baja a
  la fila siguiente).
- [ ] AC7: Flecha abajo / flecha arriba en «Faltas» aplican el valor y pasan a la casilla
  «Faltas» de la fila **visible** siguiente / anterior, en el orden en que se ven en pantalla
  (también si el usuario ha reordenado pulsando una cabecera). Flecha arriba en la primera fila
  visible lleva al buscador. Flecha abajo en la última no hace nada. Las flechas en el
  buscador no hacen nada especial.
- [ ] AC8: Un interruptor «Solo con faltas» deja visibles solo las filas con faltas mayor que
  0; se combina con el buscador y se reevalúa cuando se aplica un valor (una fila que baja a 0
  desaparece al salir de su casilla, no mientras se teclea). Junto a él, un contador
  «N líneas · M con faltas», donde N es el total de líneas del asistente y M las que tienen
  faltas mayor que 0, sin depender de los filtros.
- [ ] AC9: Filtrar no pierde datos: las faltas escritas en filas que quedan ocultas se
  conservan y se facturan al pulsar «Facturar las faltas», igual que las visibles.
- [ ] AC10: Teclado seguro: Escape en el buscador **con texto** lo vacía y no cierra el
  diálogo; con el buscador vacío, Escape conserva el comportamiento nativo. Ninguna tecla del
  buscador ni de la navegación (Intro, Escape con texto, flechas) lanza «Facturar las faltas»
  ni envía el formulario.
- [ ] AC11: Nada más cambia: mismas validaciones y mismo resultado de `action_confirm`, mismos
  permisos (`ir.model.access.csv` con las mismas filas, sin `sudo()` nuevo). El widget se
  registra con nombre propio y solo se **usa** (`widget="..."`) en esta vista; no hay `patch()`
  de `ListRenderer` ni de `X2ManyField`, así que ninguna otra lista cambia.
  `custom_qty_extension.js` y `rental_availability_popup.*`, que hoy no se cargan, siguen sin
  cargarse. Las pruebas existentes siguen válidas y el módulo pasa `odoo_validate`,
  `validar_vistas.py` y `validar_modulo.py`.

## Constraints

- Odoo 19.0 EE. `enteza` es producción y no hay `--test-enable`: las pruebas Python se escriben
  y **no se ejecutan**. Solo pueden cubrir AC1, AC2 (campo), AC3 (atributo de la vista), AC9 y
  AC11; AC4–AC8 y AC10 se verifican **solo en pantalla** tras desplegar y quedan anotados como
  verificación manual.
- El buscador y la navegación son un widget de campo propio sobre el One2many del asistente,
  que extiende por herencia el nativo (`X2ManyField` / `ListRenderer`). No es una pantalla
  nueva.
- El bundle de assets solo incluye los ficheros nuevos de este widget, nunca un glob sobre todo
  `static/src`. Los textos del widget van con `_t`.
- Versión `19.0.1.16.1` → `19.0.1.17.0`. Sin cambios de esquema en modelos persistentes.

## Target Odoo Version

19.0
