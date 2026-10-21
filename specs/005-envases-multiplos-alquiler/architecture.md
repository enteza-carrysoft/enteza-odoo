# Architecture

Módulos: `rental_custom` `19.0.1.18.0` → **`19.0.1.19.0`** y `enteza_portal_pedidos` `19.0.2.0.2` →
**`19.0.2.1.0`**. Odoo 19.0 Enterprise, instancia `enteza` (producción). Todo es aditivo: sin
columnas nuevas en base de datos (el campo nuevo no se almacena), sin modelos nuevos, sin ACL.

AC8 se lee **ampliado** por la decisión #2 del logbook (2026-10-21, el usuario): el «Pickup and
Return Receipt» imprime TODAS las líneas de alquiler y gana una columna «Pedido».

## Fuentes

| Hecho | Fuente |
|---|---|
| `report_rental_order_document` (vista 1712, informe 634) sin `inherit_id`; recorre `doc.order_line.filtered('qty_delivered')`; columnas Descripción, Fecha recogida, Devolución prevista, Recogido, Devuelto | RPC (orquestador), 2026-10-21 |
| `sale.order.line` sin `product_qty`; `allowed_uom_ids` de BOL BARCO (25) = [1 «Units», 31 «Envase de 25»]; `uom.uom` con `relative_uom_id`, `relative_factor`, `factor`; `product.template.uom_ids` m2m «Packagings»; `uom.group_uom` activo | RPC (orquestador) |
| `uom.uom` 19: `rounding` calculado desde la precisión «Product Unit», métodos `compare`, `round`, `is_zero`, `_compute_quantity(qty, to_unit, round=True, rounding_method='UP', raise_if_failure=True)` | `odoo/odoo` 19.0 `addons/uom/models/uom_uom.py`, leído hoy |
| `FloatField` 19 admite `options="{'hide_trailing_zeros': true}"` (1,20 → 1,2) | `addons/web/static/src/views/fields/float/float_field.js` 19.0, leído hoy |
| `@api.constrains` salta en `create` y en `write` solo si el campo está en `vals` (también al recalcular un campo almacenado calculado); Odoo 19 no propone el envase como unidad al teclear | researchers (Community 19 en GitHub), **no verificado en la instancia** |
| `rental_order_primary_form_view` es una vista `primary` de `sale.view_order_form`; `rental_custom` ya la hereda con xpaths dentro de `order_line/list` (`qty_returned` → `qty_lost`) | código local (`rental_custom/views/sale_order_views.xml`, `enteza_prestamo_intercompania/views/sale_order_product_search_views.xml`) |
| El portal ya calcula el mismo envase (`product.template.enteza_box_uom_id` / `enteza_units_per_box`, almacenados, misma definición que la spec) y hoy GUARDA cantidades no múltiplo con aviso y solo bloquea al enviar | `enteza_portal_pedidos/models/product_template.py`, `models/sale_order.py` l.413-500 y 615-631, `tests/test_packaging.py` |
| Los endpoints JSON del portal capturan `UserError`/`ValidationError` y **devuelven normalmente**: la transacción se confirma con lo que se hubiera escrito antes del error | `enteza_portal_pedidos/controllers/common.py` l.66-94 |

No verificado en esta sesión: el MCP `odoo_execute` no tiene credenciales configuradas, así que no se
pudo leer el `arch_db` de la vista 1712 ni confirmar el id 1699 de `rental_order_primary_form_view`.
Ver «Riesgos y preguntas abiertas», punto 1.

## Models

### Definición de envase (un solo sitio, `rental_custom`)

Fichero nuevo `rental_custom/models/product_envase.py`:

- `product.template._enteza_envase_uom()` → `uom.uom` (vacío si no hay). Candidatas: `uom_ids`
  con `relative_uom_id == uom_id` y `relative_factor > 1`; se elige `min` por
  `(relative_factor, id)` (desempate determinista). Las demás se ignoran (AC16).
- `product.product._enteza_envase_uom()` → `self.product_tmpl_id._enteza_envase_uom()` (los
  métodos de la plantilla no se heredan por `_inherits`).
- `product.product._enteza_envase_error_multiplo(qty, uom)` → `str` con el mensaje o `False`.
  Sin envase → `False`. Convierte `qty` a la unidad base con
  `uom._compute_quantity(qty, base, round=False)`. Con `N = envase.relative_factor`:
  - `qty_base < 0` (con `base.compare(qty_base, 0) < 0`) → «BOL BARCO (25): la cantidad no
    puede ser negativa (-5 uds).»
  - `k = round(qty_base / N)`; múltiplo si `base.compare(k * N, qty_base) == 0` (respeta la
    precisión «Product Unit»: 50,0000001 se acepta, AC3). El cero es múltiplo (AC3).
  - si no: `inferior = floor(qty_base / N) * N`, `superior = inferior + N` → «BOL BARCO (25):
    30 uds no es múltiplo del envase de 25. Prueba con 25 o 50.» Si `inferior == 0`: «… Prueba
    con 25.» (no se propone 0).
- `product.product._enteza_envase_error_unidad(uom)` → `str` o `False`. Con envase y
  `uom != uom_id` → «BOL BARCO (25): este artículo se alquila por envases de 25 y la línea
  tiene que ir en Units, su unidad base, no en Envase de 25. El número de envases se calcula
  solo.» (AC11).
- Nombre del artículo en los mensajes:
  `product.with_context(display_default_code=False).display_name` (sin `[referencia]`, como en
  el ejemplo de AC3).
- Función de módulo `fmt_num(value, digits=2)`: redondea a `digits`, quita ceros finales y usa
  coma decimal («30», «1,2», «12,5»). La usan los mensajes y la etiqueta del informe.
  Módulos no traducidos: textos en castellano con `_()` igualmente, como el resto del módulo.

### `sale.order.line` (fichero nuevo `rental_custom/models/sale_order_line_envase.py`)

`models/sale.py` ya tiene 510 líneas: no se le añade nada.

- Campo `enteza_envase_count = fields.Float(string="Nº envases",
  compute="_compute_enteza_envase_count", digits=(16, 2))`. `store=False`, sin `inverse`,
  por tanto `readonly` (AC10). `compute_sudo` por defecto (`False`): se calcula con los
  derechos del usuario, que es lo que AC18 tiene que demostrar.
- `@api.depends('product_id', 'product_uom_qty', 'product_uom_id',
  'product_id.product_tmpl_id.uom_id', 'product_id.product_tmpl_id.uom_ids.relative_factor',
  'product_id.product_tmpl_id.uom_ids.relative_uom_id')`.
- `_compute_enteza_envase_count`: siempre asigna (0.0 por defecto; un compute no almacenado
  sin asignar lanza `ValueError`, lección ya escrita en `_compute_total_availability`). Con
  `display_type` o sin producto o sin envase → 0.0. Si no → `qty_base / N` redondeado a 2
  decimales (AC1, AC2, AC16). Se calcula en cualquier línea con producto, también en venta y
  faltas: es solo lectura y no altera nada (AC6); la columna solo se muestra en alquiler (AC9).
- `@api.constrains('product_id', 'product_uom_id', 'product_uom_qty', 'is_rental')`
  `_check_enteza_envase_multiplo` → `ValidationError(product._enteza_envase_error_multiplo(
  line.product_uom_qty, line.product_uom_id))` (AC3, AC4, AC12, AC14, AC16).
- `@api.constrains('product_id', 'product_uom_id', 'is_rental')` `_check_enteza_envase_unidad`
  → `ValidationError(product._enteza_envase_error_unidad(line.product_uom_id))` (AC11). Va
  separada para que cambiar SOLO la cantidad de una línea antigua en otra unidad no la
  dispare («las líneas existentes con otra unidad no se tocan»); su cantidad se valida
  convertida a la unidad base.
- Filtro común de las dos (`_enteza_envase_lineas_a_validar`): `is_rental` y producto y no
  `display_type` y **no `order_id.rental_order_id`** (AC5, AC6). Se excluye por la marca del
  pedido de faltas y no por `is_rental`, porque `_enteza_keep_missing_line_as_sale` pone
  `is_rental=False` DESPUÉS de `super().create()`, cuando la restricción ya se ha evaluado.
- Ningún cambio en `create`/`write`/`copy`: las restricciones bastan. `copy` del pedido crea
  las líneas por `create` → AC14 sale gratis con el mensaje de AC3. Entregar, devolver y
  facturar escriben `qty_delivered`/`qty_returned`/factura, no los campos vigilados → AC13.
  Asignar un envase escribe en `product.template`, no en las líneas → AC13.
- `_get_pricelist_price` y el resto del precio no se tocan (AC7): la línea sigue en unidades y
  la tarifa se pide por la unidad de la línea.
- `_enteza_envase_label()` (para el informe) → «50 uds (2 envases de 25)», «30 uds (1,2
  envases de 25)», «25 uds (1 envase de 25)»; sin envase, solo la cantidad: «40 uds». La
  unidad se escribe «uds» si la línea está en `uom.product_uom_unit`; si no, el nombre de la
  unidad («3 kg»).

### `sale.order` (mismo fichero nuevo)

- `_enteza_pickup_lines()` → `order_line.filtered(lambda l: l.is_rental or l.qty_delivered)`,
  en el orden del pedido. Todas las líneas de alquiler (decisión #2) más las que el informe ya
  imprimía (líneas no de alquiler con algo entregado), para no quitar nada de lo que salía
  antes. Secciones y notas quedan fuera (ni alquiler ni entregadas).

### `enteza_portal_pedidos`

`models/sale_order.py` ya tiene 947 líneas (incumplimiento previo, no se arregla aquí): la lógica
nueva va en el fichero nuevo `models/sale_order_envases.py` (`_inherit = 'sale.order'`) y en los
métodos existentes solo se cambian las llamadas.

- `_enteza_portal_errores_envase(cambios)` → lista de mensajes. `cambios` = pares
  `(producto, qty)` que se van a crear o cuya cantidad cambia. Usa
  `producto._enteza_envase_error_multiplo(qty, producto.uom_id)`.
- `_enteza_portal_reconciliar_lineas` (existente):
  1. Tras construir `cesto`, y ANTES de cualquier `unlink`/`write`/`create`, calcula los
     cambios (líneas nuevas o con cantidad distinta según `float_compare`) y, si
     `_enteza_portal_errores_envase` devuelve algo, lanza
     `UserError("\n".join(mensajes))`. Las líneas guardadas que no cambian no se validan (mismo
     criterio que AC12). El endpoint la convierte en la alerta roja que ya existe, con el
     texto de AC3 (AC15).
  2. Los `unlink`/`write`/`create` van dentro de `with self.env.cr.savepoint():`. Motivo: el
     endpoint captura la excepción y la transacción se confirma; si la restricción del ORM
     saltase igualmente (por un caso que la validación previa no cubra), sin savepoint quedaría
     confirmada media reconciliación con la línea inválida dentro.
  - `box_warnings` y `_enteza_portal_check_multiplo` se mantienen (la rejilla los usa); en la
    práctica solo los producirán líneas antiguas.
- `action_enteza_portal_submit` (existente): el bloque de `violaciones` (l.615-631) pasa a usar
  `_enteza_portal_errores_envase` sobre las líneas del pedido, para que el mensaje al enviar sea
  también el de AC3 (solicitudes antiguas con cantidades no múltiplo guardadas antes del
  despliegue).
- `action_enteza_portal_repetir(self, omitidas=None)` (existente; firma compatible, devuelve
  `destino` como hoy): antes de crear cada línea, la descarta si
  `_enteza_envase_error_multiplo(qty, uom)` o `_enteza_envase_error_unidad(uom)` dan mensaje, y
  añade ese mensaje a `omitidas` si se pasó una lista (mismo patrón que `warnings` en
  `_enteza_portal_reconciliar_lineas`). No se redondea nada: se omite (decisión #2).
- `product.template._compute_enteza_box`: pasa a delegar en `plantilla._enteza_envase_uom()`
  (misma definición, DRY). Mismos `depends`; el valor almacenado no cambia.

## Views

`rental_custom/views/sale_order_views.xml`, record existente `view_order_form` (hereda
`sale_renting.rental_order_primary_form_view`, id 1699 según el orquestador, pendiente de
confirmar), xpath nuevo:

```
//field[@name='order_line']/list/field[@name='product_uom_qty']  position="after"
  field enteza_envase_count  string="Nº envases"  optional="show"
        options="{'hide_trailing_zeros': true}"  invisible="not enteza_envase_count"
```

- Solo en la vista de alquiler (vista `primary`): el pedido de venta normal no la tiene (AC9).
- `invisible` a nivel de celda: con 0 (sin envase, cantidad 0, sección/nota) la celda queda
  vacía (AC1, AC2). `hide_trailing_zeros`: «1,2» y «2», no «1,20» / «2,00».
- Etiqueta «Nº envases» para no confundirla con el campo «Envases» (`uom_ids`) de la ficha.
- Sin `readonly` explícito: el campo ya lo es. Sin `@string` en xpaths, sin `attrs`/`states`.

Resto de modelos: sin vistas nuevas. **form + list only** no aplica: no hay modelos nuevos. Sin
menús ni acciones.

Portal (`enteza_portal_pedidos/views/portal_templates.xml`, plantilla propia
`portal_solicitud_grid`): un bloque `t-if="omitidas"` con `alert alert-warning` antes del
`owl-component`: «Al repetir el pedido se han omitido estas líneas porque ya no cumplen los
envases:» + lista con `t-esc` de cada mensaje (AC15). Sin JS nuevo.

Controlador (`controllers/portal.py`):
- `portal_solicitud_repetir`: `omitidas = []`; `origen.action_enteza_portal_repetir(omitidas)`;
  si hay, `request.session['enteza_portal_omitidas'] = {'order_id': nueva.id, 'lineas':
  omitidas}`; redirige como hoy.
- `portal_solicitud`: `request.session.pop('enteza_portal_omitidas', None)`; si su `order_id`
  coincide, pasa `omitidas` a la plantilla. Se muestra una vez.

## Reports

Herencia de `sale_renting.report_rental_order_document` (vista 1712, informe 634). Fichero nuevo
`rental_custom/report/rental_order_report_templates.xml`:

```
<template id="report_rental_order_document_envases"
          inherit_id="sale_renting.report_rental_order_document">
```

1. **Bucle**: xpath al nodo del `t-foreach` que contiene `filtered('qty_delivered')`,
   `position="attributes"`, `<attribute name="t-foreach">doc._enteza_pickup_lines()</attribute>`.
   Se cambia solo el atributo; la variable del bucle (p. ej. `line`) y el cuerpo quedan igual.
2. **Cabecera**: `<th>` nuevo «Pedido» `position="before"` del `<th>` de «Recogido».
3. **Celda**: `<td>` nuevo `<span t-out="line._enteza_envase_label()"/>` `position="before"`
   del `<td>` que pinta `qty_delivered`. Orden final: Descripción, Fecha recogida, Devolución
   prevista, **Pedido**, Recogido, Devuelto.

Anclas: por contenido y no por posición, por ejemplo
`//t[contains(@t-foreach, "filtered('qty_delivered')")]` y
`//td[.//*[contains(@t-field, 'qty_delivered') or contains(@t-out, 'qty_delivered') or contains(@t-esc, 'qty_delivered')]]`.
Las expresiones exactas, el nombre de la variable del bucle, la cabecera de «Recogido» y
cualquier `colspan` de pie de tabla se fijan en IMPLEMENT leyendo el `arch_db` de la vista 1712 y
sus `inherit_children_ids` (por si `sale_stock_renting` la hereda para lotes/series y toca el
mismo bucle). Toda la lógica está en Python (`_enteza_pickup_lines`, `_enteza_envase_label`)
para poder probarla sin renderizar el PDF.

Medio: PDF existente (botón Imprimir del pedido de alquiler). Disparador: el de siempre. Sin
informes nuevos.

## Security

- **Grupos**: ninguno nuevo. Sin `groups_id`/`category_id` en `res.groups`.
- **`ir.model.access.csv`**: sin filas nuevas en ninguno de los dos módulos. No hay modelos
  nuevos. Matriz efectiva sin cambios: quien hoy puede crear/editar `sale.order.line`
  (ventas) sigue pudiendo; quien no, sigue sin poder (AC10). El campo nuevo no tiene `inverse`:
  escribirlo no cambia `product_uom_qty`.
- **Record rules**: ninguna nueva. Los envases son `uom.uom` (sin compañía) y los artículos
  compartidos tienen `company_id` vacío: un usuario de Stileum los lee con sus propios derechos
  (AC18). Por eso el compute NO lleva `compute_sudo`.
- **`sudo()`**: ninguno nuevo en `rental_custom`. En el portal se mantienen los existentes
  (`action_enteza_portal_repetir` y `_enteza_portal_reconciliar_lineas` crean líneas con
  `sudo()` porque el grupo Portal no escribe en `sale.order.line`; ya justificados en el
  módulo). La validación nueva corre en ese mismo contexto y no amplía lo que el cliente puede
  tocar: solo rechaza u omite.
- **Rutas públicas**: ninguna nueva; `/my/solicitudes/<id>/repetir` y `/my/solicitud/<id>` ya
  son `auth='user'` con comprobación de propiedad. La sesión solo guarda textos de error del
  propio pedido del cliente.

## Manifest

`rental_custom/__manifest__.py`:
- `version`: `19.0.1.19.0`.
- `depends`: sin cambios (`uom` llega por `sale_management` → `product`; el informe por
  `sale_renting`).
- `data`: se añade `'report/rental_order_report_templates.xml'` justo después de
  `'views/sale_order_views.xml'`. Resto igual y en el mismo orden.
- `models/__init__.py`: `from . import ..., product_envase, sale_order_line_envase`.
- `tests/__init__.py`: `from . import test_envases`.

`enteza_portal_pedidos/__manifest__.py`:
- `version`: `19.0.2.1.0`. `depends` y `data` sin cambios (la plantilla del portal se edita en su
  fichero actual).
- `models/__init__.py`: `from . import sale_order_envases`.
- `tests/__init__.py`: `from . import test_envases_portal`.

Despliegue: commit → push → `invoke git-aggregate` → Actualizar lista → actualizar
`rental_custom` y después `enteza_portal_pedidos` → confirmar `state` y `latest_version` por RPC.

## Tours

No tours needed. Las pruebas HttpCase no se pueden ejecutar en este hosting; lo visual (columna,
alerta del portal, PDF) se comprueba en pantalla.

## Demo data

No demo data. Los envases y su asignación a los artículos son datos de producción y se cargan
aparte (fuera de esta spec). Las pruebas crean sus propios envases y artículos.

## Documentation

Castellano. Fragmentos OCA en `rental_custom/readme/`:
- `DESCRIPTION.md`: sección nueva «Envases en las líneas de alquiler (desde la `19.0.1.19.0`)»:
  qué es un envase, regla de múltiplos, «Nº envases», el parte de recogida con la columna
  «Pedido» y todas las líneas, y qué NO cambia (precio por unidad suelta, venta normal, faltas).
- `CONFIGURE.md` (nuevo): crear la unidad «Envase de N» (`Unidad de referencia` = Units,
  `Contiene` = N) y añadirla en «Envases» de la ficha del artículo. Qué envases se ignoran y
  que con dos válidos manda el menor.
- `USAGE.md` (nuevo): qué mensaje sale y cómo corregirlo; líneas antiguas (siguen funcionando;
  solo se validan al cambiar cantidad/producto/unidad); duplicar pedidos antiguos.
- `HISTORY.md` (nuevo): entrada `19.0.1.19.0`.

`enteza_portal_pedidos/README.md` (el módulo no usa `readme/`): en el apartado de cajas, que ahora
el guardado rechaza las cantidades no múltiplo con el mismo mensaje del backend y que «Repetir
pedido» omite y avisa. Docstrings de los métodos nuevos/cambiados con el porqué.

## Tests

Escritos y **no ejecutados** (producción sin `odoo -u` ni `--test-enable`): se entregan validados
por sintaxis. `rental_custom/tests/test_envases.py` (`TransactionCase`, `post_install`,
`-at_install`): crea «Envase de 25» (`relative_uom_id` = `uom.product_uom_unit`,
`relative_factor` 25), «Envase de 10», envases inválidos (factor 1, factor 0,5, referencia
distinta), artículos «BOL BARCO (25)» y sin envase (`rent_ok`, `type='consu'`), un pedido de
alquiler (`is_rental_order`, fechas) y un pedido de faltas (`rental_order_id`). Para tener líneas
«antiguas» fuera de regla se crean ANTES de asignar el envase al artículo.
`enteza_portal_pedidos/tests/test_envases_portal.py` para AC15, y se reescribe
`test_packaging.test_lines_update_reports_warning_without_blocking`, cuyo comportamiento (guardar
90 con caja de 25) deja de ser válido por AC15: pasa a comprobar el rechazo.

Estático: `odoo_validate` de los dos módulos y los scripts de validación del repo (vistas y
módulo) antes de desplegar.

## Riesgos y preguntas abiertas (para el desarrollador)

1. **Anclas del informe sin leer.** En esta sesión el MCP no tiene credenciales: no se ha leído el
   `arch_db` de la vista 1712 ni sus herederas, ni confirmado el id 1699. Antes de implementar,
   leerlos (`python .claude/skills/odoo19-dev/scripts/odoo19.py` o el MCP ya configurado) y fijar
   las expresiones exactas del xpath.
2. **Cantidades negativas**: propuesta, rechazarlas solo en líneas de alquiler de artículos con
   envase (el ámbito de AC3). ¿O en todas las líneas de alquiler?
3. **«1 envase» en singular** («25 uds (1 envase de 25)»). La spec no lo dice; ¿vale así?
4. **Líneas que no son de alquiler en el parte**: propuesta, seguir imprimiendo las que ya salían
   (entregadas) además de todas las de alquiler. ¿O solo las de alquiler, estrictamente?
5. **Cambio de comportamiento del portal**: hoy el autoguardado acepta 90 con caja de 25 y solo
   avisa; con AC15 el guardado entero se rechaza y la rejilla muestra «Sin guardar» con el
   mensaje. Lo tecleado no se pierde (sigue en pantalla y en el borrador local). Se reescribe
   una prueba existente que afirmaba lo contrario.
6. **Catálogo de productos del pedido (botón «+»)**: si se usa en alquiler, suma de 1 en 1 y
   guarda al momento; con envase el primer «+» (1 ud) se rechazará. Teclear la cantidad (25, 50)
   en el catálogo sí funciona. No lo cubre ningún AC; avisar a los comerciales.
7. **`is_rental` recalculado**: si `sale_renting` recalcula `is_rental` de líneas existentes
   (p. ej. al cambiar `rent_ok` de un artículo), la restricción saltaría en líneas antiguas fuera
   de regla. No verificado (código EE no legible). Riesgo bajo; si aparece, el mensaje dice qué
   línea es.
8. **Módulos no instalados que escriben cantidades** (`rental_portal_change_request`): si se
   reinstalan, sus aprobaciones quedarían sujetas a la regla. Hoy no afecta.
9. **Precisión del portal**: el código existente usa `precision_get('Product Unit of Measure')`,
   nombre de la 18; en la 19 es «Product Unit» y la llamada cae al valor por defecto (2). Lo
   nuevo usa `uom.compare`, que lee la precisión correcta. No se corrige lo antiguo aquí.
10. **Datos**: al asignar envases, las solicitudes del portal en composición con cantidades no
    múltiplo ya guardadas no cambian, pero al enviarlas saldrá el mensaje de AC3.
