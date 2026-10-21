# 005 — Envases y múltiplos en las líneas de alquiler

## Context

Muchos artículos alquilables de Enteza se alquilan por envases completos (bandejas, cestas, cajas). El
número de unidades por envase figura entre paréntesis en el nombre del artículo, por ejemplo
«BOL BARCO (25)». En Odoo 19 un envase es una unidad de medida (`uom.uom`, p. ej. «Envase de 25»,
`relative_factor` = 25 respecto a «Units») enlazada al artículo en `product.template.uom_ids`
(etiqueta «Packagings»/«Envases»).

Odoo 19 no obliga a vender en múltiplos del envase y no muestra cuántos envases hay en una línea.
Además el alquiler nativo (`sale_renting`) no convierte el precio según la unidad elegida: elegir
«Envase de 25» como unidad de la línea daría el precio de una unidad. El cliente quiere seguir como
en su aplicación anterior: la línea va en **unidades**, el precio es el de la **unidad suelta**, y el
almacén necesita saber cuántos **envases** tiene que coger.

Alcance: `rental_custom` (modelo, vistas, parte de recogida) y, solo para el portal de clientes,
`enteza_portal_pedidos` (mensaje legible y «Repetir pedido»). Los envases y su asignación a los
artículos son datos y se cargan aparte, no en esta spec. Un artículo sin envase no cambia en nada.

**Envase de un artículo (definición operativa).** Entre las unidades de `product.template.uom_ids`
se consideran válidas las que tienen `relative_uom_id` igual a la unidad base del artículo
(`uom_id`) y `relative_factor` > 1. Si hay varias válidas se usa la de menor factor. Las demás
(factor ≤ 1, otra unidad de referencia, encadenadas) se ignoran. El tamaño del envase, N, es ese
factor.

## Acceptance Criteria

- [ ] AC1: En una línea de alquiler con un artículo con envase de N unidades, el campo calculado de
  solo lectura «Nº envases» muestra cantidad ÷ N (50 uds con envase de 25 → 2). Si la cantidad no es
  múltiplo muestra el decimal (30 → 1,2); con cantidad 0, o en líneas sin producto (secciones, notas)
  queda vacío.
- [ ] AC2: Con un artículo sin envase válido, «Nº envases» queda vacío y la línea se comporta igual
  que antes.
- [ ] AC3: Al crear una línea de alquiler, o cambiar su `product_uom_qty`, `product_id` o
  `product_uom_id`, con un artículo con envase de N unidades y una cantidad que no es múltiplo de N
  (30 con envase de 25), el guardado se rechaza con un error en castellano que indica el artículo, la
  cantidad, el tamaño del envase y los múltiplos más cercanos: «BOL BARCO (25): 30 uds no es múltiplo
  del envase de 25. Prueba con 25 o 50.» La comparación respeta la precisión de la unidad (50,0000001
  se acepta). Se rechazan además las cantidades negativas; el cero se acepta.
- [ ] AC4: Una cantidad múltiplo de N (25, 50, 75…) se acepta.
- [ ] AC5: La restricción solo se aplica a líneas de alquiler (`is_rental`). Las líneas de venta
  normal del mismo artículo no se ven afectadas.
- [ ] AC6: Las líneas de un pedido de faltas (pedido con `rental_order_id`) no se bloquean ni se
  alteran por AC3 ni por AC11, aunque lleven `is_rental=True` de forma transitoria, incluido añadir o
  editar a mano una línea en un pedido de faltas abierto desde la app de Alquiler.
- [ ] AC7: Para una línea de 50 uds de un artículo con envase de 25, `price_unit` es el mismo que da
  la tarifa para 1 ud y `price_subtotal = 50 × price_unit` (descuento 0). Esta funcionalidad no
  modifica el cálculo de precios.
- [ ] AC8: El impreso «Pickup and Return Receipt» (parte de recogida) muestra en cada línea con envase
  «50 uds (2 envases de 25)»; si no es múltiplo muestra «30 uds (1,2 envases de 25)». Las líneas sin
  envase se imprimen igual que antes.
- [ ] AC9: La lista de líneas del pedido de alquiler (`sale_renting.rental_order_primary_form_view`)
  muestra la columna «Nº envases» junto a la cantidad. En el pedido de venta normal no se añade.
- [ ] AC10: El campo «Nº envases» es `compute`, `store=False`, sin `inverse` y de solo lectura. Un
  `write` con ese campo no modifica `product_uom_qty`, y un usuario sin derechos de escritura en
  `sale.order.line` sigue sin poder modificar líneas.
- [ ] AC11: Al crear una línea de alquiler, o cambiar su producto o su unidad, con un artículo con
  envase y `product_uom_id` distinto de la unidad base del artículo, el guardado se rechaza con un
  mensaje en castellano que pide usar la unidad base. Las líneas existentes con otra unidad no se
  tocan.
- [ ] AC12: Editar en una línea antigua cualquier campo que no sea cantidad, producto, unidad o
  `is_rental` (precio, descripción, fechas, descuento) no dispara la restricción aunque su cantidad no
  sea múltiplo. Cambiar su cantidad sí la dispara (AC3).
- [ ] AC13: Los pedidos ya confirmados con líneas fuera de regla se pueden seguir entregando,
  devolviendo y facturando. Asignar un envase a un artículo con líneas vivas no bloquea esas líneas.
- [ ] AC14: Duplicar (`copy`) un pedido con líneas no múltiplo se rechaza con el mensaje de AC3.
- [ ] AC15: En el portal de clientes, una cantidad no múltiplo se rechaza con el mensaje de AC3 en
  castellano, sin error técnico. «Repetir pedido» omite las líneas de pedidos antiguos que ya no
  cumplen la regla y avisa al cliente de cuáles ha omitido y por qué.
- [ ] AC16: Si un artículo tiene dos envases válidos (10 y 25) se usa el de menor factor: 30 uds se
  acepta y «Nº envases» muestra 3. Un envase con factor ≤ 1, o con unidad de referencia distinta de
  la base, se ignora.
- [ ] AC17: Al elegir un artículo con envase y teclear una cantidad múltiplo (50), Odoo no cambia la
  unidad de la línea a un envase: sigue en la unidad base.
- [ ] AC18: Un usuario de Stileum, sin sudo, ve «Nº envases» correctamente en artículos compartidos
  entre las dos compañías.

## Constraints

- Las líneas de pedidos ya existentes no se modifican; la regla actúa solo al crear o editar según
  AC3, AC11 y AC12.
- Sin dependencias nuevas salvo las ya declaradas en `rental_custom` y `enteza_portal_pedidos`.
- Las pruebas automatizadas se escriben pero no pueden ejecutarse en esta instancia (producción, sin
  `odoo -u` ni `--test-enable`); se entregan validadas por sintaxis y no ejecutadas.
- Los mensajes de error van en castellano directamente en el código; los módulos no están
  traducidos.
- La instancia `enteza` es producción: nada se despliega sin confirmación del usuario.
- Pendiente de verificar en la 19 durante ARCHITECTURE: nombre y plantilla del informe «Pickup and
  Return Receipt», campos `relative_uom_id`/`relative_factor`, y que Odoo no propone el envase como
  unidad de la línea (AC17).

## Target Odoo Version

19.0 Enterprise. Instancia: `enteza` (producción).
