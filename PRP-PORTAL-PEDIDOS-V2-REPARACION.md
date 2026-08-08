# PRP v2 — `enteza_portal_pedidos`: reparación, rendimiento y diálogo con el comercial

**Repositorio:** `enteza-odoo`, rama `19.0` · **Instancia:** `enteza26` (Odoo 19 EE, **producción**)
**Parte de:** `19.0.1.0.1` (instalado) · **Entrega:** `19.0.2.0.0`
**Fecha:** 2026-08-08 · **Estado:** especificación para implementar

> **Antes de escribir una línea:** cargar el skill `odoo19-dev`
> (`.claude/skills/odoo19-dev/SKILL.md`) y leer el PRP original
> `PRP-PORTAL-PEDIDOS-CLIENTE.md`. Este documento **no lo sustituye**: lo corrige en dos
> puntos concretos (§2) y añade el flujo de diálogo (§8). Todo lo demás del PRP original
> sigue vigente y **no se re-litiga**.

> **Regla imperativa del proyecto: _progressive disclosure_.** Se aplica al diseño de las
> pantallas (§7), a los mensajes de error (§6.4) y a la propia estructura de este documento.
> Nada muestra todo de golpe: ni la rejilla, ni el resumen, ni el chat, ni los avisos.

---

## 1. Resumen ejecutivo

Tres síntomas reportados por el usuario, tres causas localizadas, un mismo origen de fondo.

| Síntoma | Causa raíz | Sección |
|---|---|---|
| «Se renderiza otra vez mientras introduzco unidades» | El `input` de cantidad es *controlado* y el aviso de caja aparece bajo la fila en cada tecla; además cada confirmación repinta **1.025 filas** | §5.1, §5.2 |
| «Falla cuando se graba» | La cola de cambios se vacía **antes** de saber si el POST funcionó: un fallo descarta las cantidades para siempre y la pantalla las sigue mostrando | §5.3 |
| «Falla el envío para crear el pedido» | El bloqueo optimista por `write_date` se captura al encolar, no al enviar; y **ningún RPC del JS está dentro de un `try/catch`** | §5.4, §5.5 |

**Origen de fondo:** el módulo escribe en base de datos **en cada pulsación** y arbitra esa
escritura con un bloqueo optimista que la propia maquinaria de alquiler invalida sola. Se
sustituye por **guardado idempotente del cesto completo** (§2.2).

**Dato duro (RPC, 2026-08-08):** la secuencia `enteza.portal.pedido` sigue en
`number_next_actual = 1` y hay **0 pedidos** con `enteza_portal_state != 'none'`.
Ningún envío ha llegado nunca a completarse. Partimos de cero de datos: **no hace falta
migración**.

---

## 2. Veredicto: pivotar el *cómo*, no el *qué*

La funcionalidad propuesta en el PRP original se mantiene íntegra. De las **seis decisiones de
arquitectura** de su §2, **cinco se conservan sin tocar**:

- §2.1 solo `portal`, nunca `website` — **se mantiene**.
- §2.2 la solicitud **ES** un `sale.order` de alquiler en borrador — **se mantiene**.
- §2.4 facetas sobre `product.tag` — **se mantiene**.
- §2.5 la disponibilidad la calcula el motor nativo — **se mantiene**.
- §2.6 las cajas son packaging nativo (`uom_ids`) — **se mantiene**.

Se revocan **dos sub-decisiones**, las dos causantes directas de los fallos.

### 2.1 Revocada: «no hay paginación, se pintan las 1.025 filas» (PRP §2.3)

El PRP original mezcló dos cosas distintas:

- **Servir el catálogo entero al navegador y filtrarlo ahí** — correcto, se mantiene: el JSON
  es pequeño y el filtrado es instantáneo.
- **Pintar el catálogo entero en el DOM** — incorrecto. 1.025 `<tr>` con dos componentes OWL
  cada uno son ~10.000 nodos. Cualquier cambio de estado del padre los repasa todos.

Agravante verificado por RPC: hay **0 facetas configuradas** (`enteza.product.facet` está
vacío). El único desplegable con contenido es «Categoría», así que en la práctica el cliente
está siempre ante las 1.025 filas.

**Sustitución:** el catálogo se sigue sirviendo entero y filtrando en el navegador, pero se
**renderiza por ventana** y se entra por el camino corto (§7). Esto no es solo rendimiento:
es la regla de progressive disclosure aplicada al dominio real — un cliente que repite pide
casi siempre lo mismo.

### 2.2 Revocada: «escritura incremental por línea + bloqueo optimista por `write_date`» (PRP §8.2)

El bloqueo optimista no puede funcionar aquí, y no por un error de implementación sino por el
diseño:

1. Crear una línea de alquiler dispara el cálculo de `price_unit`, que en esta instancia pasa
   por `rental_custom.SaleOrderLine._get_pricelist_price`
   (`rental_custom/models/sale.py:157-179`), que llama a `self.order_id._rental_set_dates()`.
   Es decir: **crear una línea puede escribir en la cabecera del pedido** y mover su
   `write_date` sin que el cliente se entere.
   *(Hipótesis a confirmar en la primera prueba real; el rediseño la hace irrelevante.)*
2. `RequestGrid.onQtyChange` (`static/src/grid/request_grid.js:308`) captura el `write_date`
   **al encolar**, y el POST sale 600 ms después. Cualquier cambio de cabecera intermedio lo
   invalida.
3. `fields.Datetime.to_string` tiene precisión de segundo; PostgreSQL guarda microsegundos.

**Sustitución: guardado idempotente del cesto completo.** Un único endpoint recibe el estado
entero (cabecera + todas las líneas con cantidad) y **reconcilia** en una transacción. Es
idempotente: repetirlo no duplica nada, y reintentarlo tras un fallo de red es seguro. Con
eso el bloqueo optimista sobra: la semántica pasa a ser *last-write-wins* sobre un estado
completo, que es comportamiento **definido**, en lugar de un callejón sin salida
(«recarga la página») ante una carrera que el propio servidor provoca.

> **Por qué no se pivota a un modelo propio `enteza.rental.request`:** se estudió y se
> descarta. Resolvería los mismos problemas, pero obliga a reimplementar tarifas, impuestos,
> conversión a pedido y todas las pantallas de seguimiento — exactamente lo que la §2.2 del
> PRP original evita. Con el guardado diferido, los inconvenientes de usar `sale.order`
> (escrituras constantes, maquinaria de alquiler en cada tecla) desaparecen igual, sin pagar
> ese precio.

### 2.3 Decisiones tomadas con el usuario (2026-08-08)

Cuatro decisiones de negocio que **no se re-litigan** y que modifican el PRP original.

| # | Decisión | Modifica |
|---|---|---|
| **D1** | **Comercial por defecto en Ajustes.** Campo nuevo `res.company.enteza_portal_user_id`. Si el cliente no tiene comercial propio, la solicitud se asigna a ése | PRP §4.1, §10.1 |
| **D2** | **El cliente solo elige la fecha del evento.** Entrega = evento − 1 día, retirada = evento + 1 día, igual que `rental_custom.event_date_change` en el backend. Se muestran calculadas, con un enlace «ajustar» para el caso raro | PRP §8.2, §9.2 |
| **D3** | **El almacén no se elige desde el portal.** Se usa siempre `res.partner.enteza_portal_warehouse_id`. Sin selector | PRP §8.2, §9.2 |
| **D4** | **La disponibilidad la calcula siempre la función nativa** del módulo de alquiler Enterprise. Se elimina el cálculo artesanal de `rental_custom` | PRP §2.5 (lo refuerza) |

**D1 — por qué es obligatorio y no opcional.** Verificado por RPC: `AGRIPINA` (el único
cliente con portal) tiene `user_id = False`. El pedido se crea con `sudo()`, pero `sudo()`
mantiene el `uid`: `self.env.user` sigue siendo **el usuario del portal**. Con el código
actual, `sale.order.user_id` acabaría siendo el propio cliente y el «aviso al comercial» se
lo mandaríamos a él. Ver defecto §5.10.

**D2 — consecuencias.** Desaparecen dos campos de la pantalla y sus validaciones cruzadas
(§5.9d queda reducido a validar el ajuste manual). El derivado se calcula **en el servidor**,
nunca en el navegador: es la misma regla que el backend y tiene que dar el mismo resultado.

**D3 — consecuencias.** Desaparece el bloque `warehouses` del payload de cabecera, el
`<select>` de la plantilla y **todo el problema de cambio de compañía** (§5.8 se resuelve
por eliminación). Si el cliente no tiene almacén habitual en su ficha, la pantalla no se
monta: se le dice que contacte con su comercial. No se elige uno por él — con dos sociedades
distintas, adivinar es peor que no hacer nada.

**D4 — alcance.** Se corrige `rental_custom`, no solo el portal. Detalle en la fase F0 (§6).

---

## 3. Estado verificado hoy (RPC, `enteza26`, 2026-08-08)

Lo que sigue **está comprobado contra la instancia**, no supuesto. El resto de este documento
lo da por cierto.

| Hecho | Valor |
|---|---|
| `enteza_portal_pedidos` | `installed`, `19.0.1.0.1` |
| `rental_custom` | `installed`, `19.0.1.9.1` |
| `sale_renting` / `sale_stock_renting` / `portal` | los tres `installed` |
| Solicitudes del portal existentes | **0** (`enteza_portal_state != 'none'`) |
| Secuencia `enteza.portal.pedido` | `number_next_actual = 1` → ningún envío completado |
| Partners con `enteza_portal_pedidos_ok` | **1** (`AGRIPINA`, id 1858) |
| Facetas `enteza.product.facet` | **0** |
| Catálogo servido (`rent_ok` + `consu` + `portal_ok` + `active`) | **1.025 productos** |
| `sale.order.default_get` con `in_rental_app=True` | devuelve `is_rental_order: True` ✔ |
| `sale.order.line.default_get` con `in_rental_app=True` | devuelve `{}` — **el contexto NO fija `is_rental` en la línea** |
| `is_rental` en líneas de pedidos de alquiler reales | sigue a `product_id.rent_ok` (35.908 `True` / 2.008 `False`, y las `False` son servicios) |
| `product_uom_id` en `sale.order.line` | existe, `many2one` a `uom.uom` ✔ |

🔴 **Corrección al PRP original §8.2.** Dice «crear el pedido y las líneas **siempre** con
`.with_context(in_rental_app=True)`, o `is_rental` sale `False`». Para el **pedido** es
cierto y verificado. Para la **línea** no: ese contexto no aporta ningún valor por defecto.
`is_rental` se deduce del pedido y del producto. Como el campo es escribible
(`readonly: false`, verificado), la línea se creará **fijando `is_rental=True` explícitamente**
(§6.2): el portal solo sirve productos `rent_ok` dentro de un pedido de alquiler, así que el
valor es siempre correcto y se elimina la dependencia de un comportamiento no verificado.

---

## 4. Lo que NO se toca

Para que nadie amplíe el alcance por su cuenta:

- No se instala `website` ni `website_sale`. Ninguna ruta lleva `website=True`.
- No se reimplementa disponibilidad: sigue delegando en
  `product._get_unavailable_qty` / `_get_virtual_unavailable_qty_in_rent`
  (`models/product_product.py`). **Ese fichero no se modifica.**
- No se toca el modelo de facetas ni `product_template.py` / `product_tag.py` /
  `product_facet.py`.
- No se toca `models/res_company.py`, `res_config_settings.py`, `res_partner.py`.
- No se toca el parche `portal_language_selector_fix` de `views/portal_templates.xml`
  (arregla un 500 real, ya verificado en producción).
- No se toca `rental_custom`. Sus defectos se rodean, no se corrigen aquí (§10.3).
- **No se escribe ningún dato en `enteza26`** durante la implementación. La primera prueba
  real la hace el usuario, con la consola del navegador abierta.

---

## 5. Defectos, ordenados por severidad

Cada uno con fichero:línea sobre el código actual.

### 5.1 🔴 CRÍTICO — El `input` de cantidad es controlado

`static/src/grid/qty_cell.xml:5` — `t-att-value="state.texto"` con `state` reactivo, y
`onInput` (`qty_cell.js:72-76`) escribe en ese estado en cada tecla. OWL vuelve a poner el
valor en el DOM → **el cursor salta al final**. Insertar un dígito en medio de «100» es
imposible.

Agravante: el getter `avisoCaja` (`qty_cell.js:49-66`) se evalúa en cada render y el bloque
rojo con dos botones aparece y desaparece **debajo del input**, cambiando la altura de la fila
mientras se teclea. Es el «se renderiza otra vez» que describe el usuario.

### 5.2 🔴 CRÍTICO — Repintado de las 1.025 filas en cada confirmación

`request_grid.js:297-319`: `onQtyChange` reemplaza `state.lines` y `state.totals` enteros.
La plantilla (`request_grid.xml:132`) recorre `state.visibleProductIds` sin ventana. Cada
confirmación repasa todas las filas y todos sus componentes hijos.

Suma a esto:
- `categoryOptionCount` / `facetOptionCount` (`request_grid.js:162-183`) son **O(productos ×
  opciones)** y se llaman desde la plantilla del desplegable en cada render.
- `FacetDropdown.opcionesOrdenadas` (`facet_dropdown.js:38-57`) hace `filter`+`map`+`sort` en
  cada render aunque el desplegable esté cerrado.

### 5.3 🔴 CRÍTICO — Se pierden cantidades al fallar el guardado

`static/src/services/request_service.js:59` — `this._cambiosPendientes.clear()` se ejecuta
**antes** del `rpc()`. Si la llamada falla (stale, 500, corte de red), los cambios ya no
existen en ninguna cola. Quedan en `state.lines`, así que la pantalla los sigue mostrando
como si estuvieran guardados, y el siguiente «Guardar» dice *«Guardado.»* porque no hay nada
pendiente (`request_grid.js:363-377`). El cliente cree que grabó y no grabó.

### 5.4 🔴 CRÍTICO — Bloqueo optimista que se autoinvalida

Ya explicado en §2.2. Efecto visible: `{'error': 'stale'}` → *«La solicitud se ha actualizado
en otra pestaña. Recarga la página.»* sin que haya ninguna otra pestaña.

### 5.5 🔴 CRÍTICO — Ningún RPC del JS está protegido, y el servidor lanza fuera del `try`

- En `controllers/api.py`, `enteza_get_solicitud(order_id, requiere_composing=True)` está
  **fuera** del `try/except` en las cuatro rutas que lo usan (líneas 38, 58, 73, 89). Lanza
  `UserError`, `AccessError` o `MissingError` → error JSON-RPC crudo.
- En el JS, solo `_cargar` tiene `try/catch` (`request_grid.js:82-110`). `onGuardar`,
  `onEnviar`, `onCancelar`, `onHeaderChange`, `_precargarDisponibilidad` y el *flush*
  encolado **no lo tienen**: la promesa se rechaza sin que nadie la atienda y **no pasa
  nada visible**.
- Consecuencia concreta: `action_enteza_portal_submit` se escribió idempotente a propósito
  para tolerar el doble clic (`models/sale_order.py:436-438`), pero `requiere_composing=True`
  en la ruta lo impide: el segundo clic lanza antes de llegar al método.

### 5.6 🟠 GRAVE — `hideUnavailable` miente

`request_grid.js:144` filtra por `state.availability`, pero `_recomputeVisible` no se vuelve a
ejecutar cuando llegan los semáforos (`_precargarDisponibilidad`, líneas 246-267). El filtro
queda desfasado hasta la siguiente interacción.

### 5.7 🟠 GRAVE — «Repetir un pedido anterior» rompe la invariante de una solicitud a la vez

`models/sale_order.py:96-120` crea otra solicitud en `composing` sin comprobar si ya hay una.
Después, `_enteza_portal_get_or_create` (líneas 78-82, `order='id desc'`) devolverá siempre la
más nueva: la anterior queda huérfana en `composing`, invisible y sin cerrar.

### 5.8 🟠 GRAVE — Cambiar de almacén cambia la compañía con líneas ya creadas

`models/sale_order.py:191-195` escribe `company_id` junto con `warehouse_id`. Con líneas ya
grabadas, tarifas, impuestos y diario pueden quedar cruzados entre Vimaple y Stileum.

### 5.9 🟡 MEDIO

| # | Defecto | Sitio |
|---|---|---|
| a | `_aplicarResultadoLineas` fusiona líneas del servidor pero nunca borra las que el servidor ya no tiene → divergencia silenciosa | `request_grid.js:346-350` |
| b | `state.boxWarnings` se reemplaza entero con los avisos del último lote → desaparecen los de otros productos | `request_grid.js:352-356` |
| c | `enteza_portal_dias_minimos` se calcula, se envía al navegador y **no se usa en ningún sitio**. Configuración muerta | `models/res_company.py:14`, `sale_order.py:165` |
| d | Ni `pickup_date <= return_date`, ni `event_date` dentro del periodo, ni antelación mínima: no hay una sola validación de fechas | `sale_order.py:174-199` |
| e | `pickup_date` / `return_date` solo se escriben si son *truthy*: el cliente no puede vaciarlas. `event_date` sí. Incoherente | `sale_order.py:187-190` |
| f | `<input type="date">` manda `"2026-09-14"` a un `Datetime` → Odoo lo completa a `00:00 UTC` = 02:00 local. En España cuadra de milagro; la hora de entrega no significa nada | `request_grid.xml:60-68` |
| g | `_enteza_portal_productos_habituales` hace un `search_read` sin límite de **todas** las líneas históricas del cliente en cada carga del catálogo | `sale_order.py:205-216` |
| h | `lineas_por_producto` calculado y nunca usado | `sale_order.py:233` |
| i | `_precargarDisponibilidad` sin *debounce* (el PRP §6.2 pide 400 ms): un cambio de filtro dispara 3 lotes secuenciales de 50 | `request_grid.js:246-267` |
| j | El cliente **no queda como seguidor** del pedido al enviar → las respuestas del comercial en el chatter no le llegan | `sale_order.py:500-531` |

---

## 6. Plan de trabajo

Cinco fases. **Cada fase deja el módulo instalable y coherente**: si hay que parar, se para
entre fases, nunca dentro. Ejecutar en orden.

### F1 — Cimientos: contrato de API idempotente y errores que se ven

**Objetivo:** que ningún fallo sea silencioso y que ninguna cantidad se pierda nunca.

**`controllers/common.py`**
- Añadir un decorador `enteza_json_endpoint` que envuelva el cuerpo entero de cada ruta y
  convierta `UserError`, `AccessError`, `MissingError` y `ValidationError` en
  `{'error': <texto>, 'error_code': <'no_editable'|'no_acceso'|'validacion'>}`.
  Cualquier otra excepción: registrar con `_logger.exception(...)` y devolver
  `{'error': "Ha ocurrido un error inesperado…", 'error_code': 'interno'}` — **nunca** el
  traceback al cliente.
- `enteza_get_solicitud`: quitar el parámetro `requiere_composing`. La comprobación de estado
  pasa a los métodos del modelo, que ya la hacen (`_enteza_portal_check_composing`).

**`controllers/api.py`** — rutas nuevas, todas `type='jsonrpc', auth='user'`, todas
decoradas:

| Ruta | Params | Devuelve |
|---|---|---|
| `…/catalogo` | `order_id` | igual que hoy (§8.3 del PRP) |
| `…/guardar` | `order_id`, `header`, `lines`, `customer_note` | estado autoritativo completo |
| `…/disponibilidad` | `order_id`, `items: [{product_id, qty}]` (máx. 50) | `{product_id: color}` |
| `…/enviar` | `order_id`, `header`, `lines`, `customer_note` | `{ok, ref, redirect}` o `{error, error_code, detalle}` |
| `…/cancelar` | `order_id` | `{ok}` |

- **Se eliminan** `…/cabecera` y `…/lineas`, y con ellas `expected_write_date` de todo el
  módulo.
- 🔴 `…/enviar` **recibe el cesto y hace guardado + envío en una sola transacción**. Así
  desaparece por completo la carrera entre guardar y enviar (§5.4).
- `…/disponibilidad` recibe la cantidad tecleada por producto, en vez de leerla de la línea:
  con guardado diferido puede no estar en base de datos todavía.

**`models/sale_order.py`**
- `_enteza_portal_guardar(header, lines, customer_note)` — **el método central**. En una
  transacción y en este orden:
  1. `_enteza_portal_check_composing()`.
  2. Validar y escribir cabecera (§6.1).
  3. Reconciliar líneas contra `lines` (§6.2): crear, actualizar, y **borrar las que ya no
     estén en el cesto**. `lines` es el estado completo, no un delta.
  4. Escribir `enteza_portal_customer_note`.
  5. Devolver el payload autoritativo: `{order, lines, totals, warnings}`.
- `action_enteza_portal_submit(header, lines, customer_note)` — llama primero a
  `_enteza_portal_guardar(...)` y sigue con lo que ya hace. Mantener la idempotencia que ya
  tiene: si no está en `composing`, devolver el estado actual sin repetir nada.
- Borrar `_enteza_portal_actualizar_cabecera` y `_enteza_portal_actualizar_lineas`.
- Borrar `write_date` del payload de cabecera y la línea muerta `sale_order.py:233`.

**`static/src/services/request_service.js`** — reescritura:
- Fuera la cola `_cambiosPendientes` y el *debounce* por línea.
- `guardar(estado)` / `enviar(estado)` / `disponibilidad(items)` / `cancelar()`, cada una
  devolviendo `{ok: true, data}` o `{ok: false, error, error_code}` — **nunca lanza**.
- Serializar las escrituras: una sola en vuelo a la vez; si llega otra mientras, se encola
  *la última* (coalescencia), no todas.
- `guardadoPendiente()` para que el componente sepa si hay cambios sin confirmar.

**Criterio de hecho de F1:** ninguna llamada del JS puede terminar en una promesa rechazada
sin atender; ningún endpoint puede lanzar hacia el transporte; ninguna cantidad se descarta
antes de tener confirmación del servidor.

### F2 — La rejilla deja de repintarse al teclear

**`static/src/grid/qty_cell.js` + `.xml`** — reescritura:
- Input **no controlado**: `t-ref="input"`, sin `t-att-value`. El valor se pinta con
  `onMounted` y en `onWillUpdateProps` solo cuando la fila **no** está en edición.
- El aviso de caja pasa a `useState({aviso})` y se recalcula **con *debounce* de 300 ms** tras
  dejar de teclear, y siempre en `blur`. Deja de aparecer y desaparecer letra a letra.
- El aviso se pinta en un contenedor de **altura reservada** (`min-height` en el SCSS) para
  que la fila no cambie de alto. *(Progressive disclosure: el aviso es una línea corta con el
  redondeo propuesto; el detalle de cajas, en el `title`.)*
- `onWillUnmount` limpia el temporizador.

**`static/src/grid/request_grid.js` + `.xml`**
- **Ventana de render** (§7.2): `state.window` = nº de filas pintadas, inicial 60, +60 por
  clic en «Mostrar más». `_recomputeVisible` la reinicia a 60.
- Memoizar los contadores de faceta: calcular `categoryCounts` / `facetCounts` **una vez por
  cambio de filtro** dentro de `_recomputeVisible`, y que `FacetDropdown` lea el mapa ya
  hecho. Prohibido llamar al contador desde la plantilla.
- `_recomputeVisible()` también tras recibir semáforos, **solo si** `filters.hideUnavailable`
  está activo (arregla §5.6).
- `_precargarDisponibilidad` con *debounce* de 400 ms y `try/catch`.
- Guardar el cesto en `localStorage` con clave `enteza_portal_solicitud_<order_id>` en cada
  cambio, y ofrecer recuperarlo si al cargar el catálogo el servidor tiene menos líneas que el
  borrador local. Es la red de seguridad del guardado diferido.
- Autoguardado: 2,5 s de inactividad tras el último cambio → `service.guardar(...)`.
  Indicador discreto en la barra: «Guardando…» / «Guardado hace un momento» / «Sin guardar».

**`static/src/filters/facet_dropdown.js`** — `opcionesOrdenadas` solo se evalúa con el
desplegable abierto; con él cerrado, devolver `[]` sin recorrer nada.

**Criterio de hecho de F2:** teclear una cantidad en una fila no cambia la altura de ninguna
fila, no mueve el cursor y no toca más DOM que esa celda.

### F3 — Corrección funcional de cabecera, fechas y almacén

**`models/sale_order.py`**
- `_enteza_portal_validar_header(vals)`, con mensajes en castellano y **de uno en uno** (el
  primero que falle; no un muro de errores):
  - `pickup_date <= return_date`.
  - `event_date` entre `pickup_date` y `return_date`, ambas inclusive.
  - `pickup_date` con al menos `company.enteza_portal_dias_minimos` de antelación → **aviso,
    no bloqueo** (§6.4 del PRP: el semáforo no bloquea; la antelación tampoco). Viaja en
    `warnings`, no en `error`. Esto por fin da uso al campo (§5.9c).
- Fechas: el portal manda `YYYY-MM-DD`. Escribirlas **fijando una hora de negocio en la zona
  del usuario** y convirtiendo a UTC, no dejando que Odoo complete con `00:00` (§5.9f).
  Constantes en el modelo: entrega a las **08:00** locales, retirada a las **20:00** locales.
  Usar `fields.Datetime.to_string(...)` sobre un `datetime` ya convertido con
  `pytz`/`babel` a partir de `self.env.user.tz or 'Europe/Madrid'`.
- Permitir **vaciar** `pickup_date` y `return_date` igual que `event_date`: la condición pasa
  de `if vals.get(k)` a `if k in vals` (§5.9e).
- Cambio de almacén con líneas grabadas: si `almacen.company_id != self.company_id` y hay
  líneas, **no** cambiar la compañía en silencio. Devolver
  `{'error': …, 'error_code': 'cambio_compania'}` explicando que hay que vaciar la solicitud
  primero, y ofrecer en la interfaz un botón «Vaciar y cambiar de almacén» (§5.8).
- `_enteza_portal_productos_habituales`: `read_group` sobre `sale.order.line` agrupado por
  `product_id`, con `order_id.date_order` de los últimos **24 meses** y `limit`. Cachear el
  resultado en el payload del catálogo, que ya se sirve una sola vez (§5.9g).

**`action_enteza_portal_repetir`** (§5.7): si el cliente ya tiene una solicitud en
`composing`, **no crear otra**. Volcar las líneas del pedido de origen sobre la existente
(sumando o reemplazando — reemplazar, y avisarlo en la interfaz antes de hacerlo) y devolver
esa misma.

### F4 — El diálogo cliente ↔ comercial

Es la parte con más funcionalidad nueva. Detalle completo en §8. Resumen de entregables:

- `models/sale_order.py`: `message_subscribe` del cliente al enviar; nuevas acciones
  `action_enteza_portal_devolver` y notificación al marcar contrapropuesta;
  `_enteza_portal_mensajes()` para el portal.
- `controllers/portal.py`: rutas POST `/my/solicitud/<id>/mensaje`,
  `/my/solicitud/<id>/aceptar`, `/my/solicitud/<id>/cambios`.
- `views/portal_templates.xml`: bloque de conversación y acciones en la página de resumen.
- `views/sale_order_views.xml`: botón «Devolver al cliente».
- `data/mail_template_data.xml`: dos plantillas nuevas (contrapropuesta y devolución) y una
  para el mensaje del cliente.

### F5 — Pruebas, documentación y despliegue

- Actualizar `tests/` al contrato nuevo (§11).
- Reescribir el `README.md` del módulo: contrato de API, estados y **decir siempre** que está
  validado por sintaxis y **no ejecutado**.
- Subir `__manifest__.py` a `19.0.2.0.0`.
- Pasar `validar_modulo.py` y `validar_vistas.py` (§12).

---

## 7. La pantalla del cliente, con progressive disclosure

### 7.1 Camino de entrada

Al abrir la solicitud, el cliente **no** ve 1.025 artículos. Ve, en este orden:

1. **Las fechas.** Sin fecha de evento no hay semáforo ni nada que decidir. Es lo único
   obligatorio y va primero, solo.
2. **«Mis habituales»** — los artículos que ya alquiló (el `habitual: true` del payload, que
   hoy se calcula y se infrautiliza). Para un cliente que repite, esto **es** su pedido. Este
   filtro viene **activado por defecto** cuando el cliente tiene al menos un habitual.
3. **Buscar o elegir categoría** para lo puntual.
4. **«Ver todo el catálogo»** — un enlace explícito, no el estado inicial.

El pie sigue diciendo siempre cuántas líneas hay en total y cuántas esconde el filtro
(comportamiento actual, correcto, se conserva).

### 7.2 Ventana de render

- Se pintan **60 filas**. Botón «Mostrar 60 más» con el contador restante.
- Cambiar cualquier filtro reinicia la ventana a 60.
- Las cantidades tecleadas **nunca** dependen de que la fila esté pintada: viven en el estado
  del cesto, igual que hoy viven en el pedido. Filtrar o cerrar la ventana no borra nada.
  Esto ya lo garantiza el PRP §2.3 y **no debe romperse**.

### 7.3 Detalle bajo demanda

- El aviso de caja: una línea corta con el redondeo propuesto. Los dos botones de redondeo se
  mantienen, pero en altura reservada (§F2).
- El semáforo: punto de color con `title`. Sin texto en la fila.
- Los totales: importe sin IVA en la barra. El desglose de IVA solo en la página de resumen.
- Los errores de validación: **el primero que falle**, no la lista entera.

---

## 8. El diálogo cliente ↔ comercial

Hoy la conversación es de un solo sentido: el cliente envía, el comercial recibe una actividad
y ahí termina el canal. El cliente **ni siquiera es seguidor del pedido** (§5.9j), así que
nada de lo que escriba el comercial en el chatter le llega.

### 8.1 Máquina de estados ampliada

Se conservan los seis valores actuales de `enteza_portal_state` y se añaden dos transiciones:

```
composing ──enviar──► submitted ──tomar──► reviewing ──contrapropuesta──► counter
    ▲                     │                    │                             │
    │                     │                    │                    ┌────────┴────────┐
    └────devolver─────────┴────────────────────┘              aceptar          pedir cambios
         (comercial)                                             │                   │
                                                                 ▼                   ▼
                                                              closed            reviewing
                                                        (al confirmar)
```

**Transiciones nuevas:**

| Transición | Quién | Efecto |
|---|---|---|
| `submitted`/`reviewing`/`counter` → `composing` | comercial, botón «Devolver al cliente» | El cliente puede volver a editar. Mensaje + correo + actividad para él |
| `counter` → `reviewing` | cliente, «Pedir cambios» | Reabre la revisión. Mensaje + actividad para el comercial |
| `counter` → *(sin cambio de estado)* | cliente, «Acepto la propuesta» | Mensaje + actividad urgente para el comercial. El cierre real lo hace `action_confirm` al firmar el presupuesto nativo |

🔴 **«Devolver al cliente» debe volver a poner `composing`, y `composing` es el único estado
editable.** Comprobar que `action_enteza_portal_devolver` no choca con el pedido ya enviado
por correo: si el presupuesto nativo está en `sent`, avisar al comercial de que el cliente va
a modificar algo que ya recibió.

### 8.2 Notificaciones: quién se entera de qué

| Suceso | Chatter | Actividad | Correo |
|---|---|---|---|
| Cliente envía la solicitud | ✔ resumen + líneas en rojo | ✔ comercial | ✔ comercial *(ya existe)* |
| Comercial marca contrapropuesta | ✔ resumen del diff | — | ✔ **cliente** *(nueva plantilla)* |
| Comercial devuelve al cliente | ✔ motivo | — | ✔ **cliente** *(nueva plantilla)* |
| Cliente escribe un mensaje | ✔ | ✔ comercial | ✔ seguidores (nativo) |
| Cliente acepta la propuesta | ✔ | ✔ comercial | ✔ seguidores |

**Al enviar la solicitud**, añadir `self.message_subscribe(partner_ids=self.partner_id.ids)`.
Sin esto, ninguna respuesta del comercial llega al cliente y el resto del diálogo es decorado.

### 8.3 Conversación en el portal

En `/my/solicitud/<id>/resumen`, bajo el resumen:

- **Los 3 últimos mensajes**, más reciente arriba, con autor y fecha. Enlace «Ver los N
  anteriores» que despliega el resto *(progressive disclosure; el resto va en el mismo HTML,
  oculto con `collapse` de Bootstrap — sin llamada extra)*.
- Formulario **plegado** «Escribir al comercial», que se abre con un clic.
- Los botones de acción del estado `counter` van **encima** de la conversación: son la
  decisión pendiente.

🔴 **Renderizado propio, no `portal.message_thread`.** Existe en la instancia (`ir.ui.view`
id 606, `mode: primary`) pero su contrato de `t-set` no está verificado contra `enteza26`, y
un `t-call` mal parametrizado es un 500 en la página. Se sigue el mismo criterio que ya usó
este módulo con `portal.portal_docs_entry` (comentario en `views/portal_templates.xml`):
markup propio sobre anclajes estables.

**Fuente de los mensajes** — `_enteza_portal_mensajes()` en el modelo:

```
self.message_ids.filtered(lambda m: m.message_type == 'comment'
                                    and m.subtype_id.internal is False)
```

🔴 Filtrar **`subtype_id.internal is False`** o el cliente verá las notas internas del
comercial. Es el fallo de seguridad más fácil de cometer aquí. Escribir un test para eso.

### 8.4 Rutas nuevas del portal

Las tres `type='http', auth='user', methods=['POST'], csrf=True`, con `<input type="hidden"
name="csrf_token" t-att-value="request.csrf_token()"/>` en el formulario — patrón ya usado en
`portal_solicitud_repetir` (`controllers/portal.py:142-163`).

| Ruta | Efecto | Redirige a |
|---|---|---|
| `/my/solicitud/<int:order_id>/mensaje` | `message_post` como el cliente + actividad para el comercial | `…/resumen` |
| `/my/solicitud/<int:order_id>/aceptar` | Mensaje + actividad. **No** confirma el pedido: la firma es la nativa | `…/resumen` con enlace destacado a `/my/quotes/<id>` |
| `/my/solicitud/<int:order_id>/cambios` | Mensaje obligatorio + `counter` → `reviewing` + actividad | `…/resumen` |

Las tres validan propiedad con `enteza_get_solicitud` y el estado que corresponda.

### 8.5 Lado del comercial

En `views/sale_order_views.xml`, junto a los dos botones que ya hay:

```xml
<button name="action_enteza_portal_devolver" type="object"
        string="Devolver al cliente"
        invisible="enteza_portal_state not in ('submitted','reviewing','counter')"/>
```

Mismo anclaje que los actuales (`//field[@name='state'][@widget='statusbar']`, `position="before"`),
ya validado. **Nunca anclar por `@string`** (gotcha del proyecto).

---

## 9. Contrato de datos del cesto

El estado que viaja del navegador al servidor en `guardar` y `enviar`:

```json
{
  "order_id": 1974,
  "header": {
    "event_date": "2026-09-15",
    "pickup_date": "2026-09-14",
    "return_date": "2026-09-16",
    "warehouse_id": 1
  },
  "lines": [ {"product_id": 412, "qty": 100}, {"product_id": 87, "qty": 25} ],
  "customer_note": "Montaje a partir de las 9h."
}
```

Reglas del servidor al reconciliar `lines`:

1. Es el **estado completo**, no un delta. Toda línea del pedido cuyo `product_id` no aparezca
   **se borra**.
2. `qty <= 0` → la línea no se crea, o se borra si existía.
3. Producto que no exista, o que no cumpla el filtro del catálogo
   (`rent_ok` + `consu` + `enteza_portal_ok` + `active`) → **se ignora en silencio** y se
   registra en `warnings`. Nunca se acepta un producto que el portal no serviría.
4. Al crear: `in_rental_app=True` en el contexto **y `is_rental: True` explícito** (§3).
   `product_uom_id` = `producto.uom_id` (la caja **no** va como UdM de la línea — PRP §8.2).
5. Respuesta: `{order, lines, totals, warnings, box_violations}`.

---

## 10. Gotchas a respetar

### 10.1 De Odoo 19 (ya documentados en el skill, se repiten los que muerden aquí)

- `type='jsonrpc'`, nunca `type='json'`.
- Ninguna ruta con `website=True`.
- `product_uom_id` en `sale.order.line`; `product_uom` en `stock.move`.
- `res.groups` no tiene `category_id` (aquí no se crean grupos, pero por si acaso).
- En vistas, nada de `attrs`/`states`; `invisible="…"` directo.
- Nunca anclar un `xpath` por `@string`.

### 10.2 De este módulo

- El grupo Portal **no tiene `ir.model.access` sobre `product.product`**: toda lectura de
  catálogo va con `sudo()` **después** de validar la propiedad del pedido. Ese orden no se
  invierte nunca.
- Un error de JS deja la pantalla **en blanco sin nada en el log del servidor**. La primera
  prueba tras desplegar necesita F12 abierto.
- `Ctrl+F5` tras desplegar: los assets se cachean.

### 10.3 De `rental_custom` (no se corrige aquí, se rodea)

`rental_custom.SaleOrderLine._compute_total_availability`
(`rental_custom/models/sale.py:191-198`) **no asigna** `total_stock` / `total_rented` /
`total_available` cuando `line.is_rental` es falso. Un campo calculado no almacenado sin
asignar lanza `ValueError` al leerlo. Como las líneas del portal se crearán siempre con
`is_rental=True` (§3), no debería dispararse — **pero conviene avisar al usuario**: es una
bomba de relojería para cualquier línea de servicio en un pedido de alquiler, y no es de este
módulo. Anotarlo como hallazgo, no arreglarlo en esta entrega.

---

## 11. Pruebas

Se escriben aunque **no se puedan ejecutar** (este hosting no da `odoo-bin --test-enable`).
Al entregar hay que decir siempre que están **validadas por sintaxis y no ejecutadas**.

Actualizar los cinco ficheros de `tests/` al contrato nuevo y añadir:

- `test_guardar_idempotente`: llamar dos veces a `_enteza_portal_guardar` con el mismo cesto
  deja el mismo número de líneas y los mismos importes.
- `test_guardar_borra_lo_que_falta`: un producto que desaparece del cesto pierde su línea.
- `test_guardar_ignora_producto_no_servido`: un producto sin `enteza_portal_ok` no entra y
  aparece en `warnings`.
- `test_enviar_es_atomico`: `action_enteza_portal_submit` con cesto guarda y envía; si la
  validación de fechas falla, **no queda ninguna línea escrita a medias**.
- `test_enviar_dos_veces`: el segundo envío devuelve el estado sin crear una referencia nueva
  (la secuencia no avanza).
- `test_mensajes_portal_no_filtran_notas_internas`: una nota con `subtype` interno **no**
  aparece en `_enteza_portal_mensajes()`. 🔴 Obligatorio.
- `test_devolver_al_cliente`: `counter` → `composing` y el pedido vuelve a ser editable.
- `test_repetir_no_duplica_composing`: con una solicitud abierta, «repetir» reutiliza esa.
- `test_fecha_entrega_hora_local`: `pickup_date = '2026-09-14'` con tz `Europe/Madrid` guarda
  `06:00 UTC` (08:00 locales), no `00:00`.

---

## 12. Validación y despliegue

```bash
python .claude/skills/odoo19-dev/scripts/validar_modulo.py enteza_portal_pedidos
python .claude/skills/odoo19-dev/scripts/validar_vistas.py enteza_portal_pedidos
```

Lo que esos scripts **no** cazan y hay que revisar a mano: `xpath` por `@string`, campos
nuevos en `res.company` sin `prefetch=False`, y cualquier `t-call` a una plantilla nativa.

Despliegue: `git push` a `19.0` → `git pull` de Xtendoo → Aplicaciones → Actualizar lista →
**Actualizar** el módulo → `Ctrl+F5`.

🔴 **Confirmar la versión por RPC, no fiarse del aviso verde.** Y recordar que los dos campos
están al revés de lo intuitivo: `latest_version` es la **instalada**, `installed_version` es
la del **manifiesto en disco**.

```bash
python .claude/skills/odoo19-dev/scripts/odoo19.py search ir.module.module \
    '[["name","=","enteza_portal_pedidos"]]' name,state,latest_version,installed_version
```

---

## 13. Criterios de aceptación

| # | Criterio | Cómo se comprueba |
|---|---|---|
| 1 | Teclear una cantidad no mueve el cursor ni cambia la altura de ninguna fila | A mano, con F12 abierto |
| 2 | Insertar un dígito en medio de «100» funciona | A mano |
| 3 | Nunca se pintan más de 60 filas sin pulsar «Mostrar más» | Contar `<tr>` en el inspector |
| 4 | Cortar la red y pulsar «Guardar» → mensaje de error visible y **las cantidades siguen ahí**; al volver la red, «Guardar» las graba | A mano, pestaña Red → *Offline* |
| 5 | Doble clic en «Enviar solicitud» → un solo envío, una sola referencia | RPC: `number_next_actual` avanza exactamente 1 |
| 6 | Enviar con fechas incoherentes → un mensaje claro, no un 500 | A mano |
| 7 | Al enviar, el cliente queda como seguidor del pedido | RPC sobre `message_follower_ids` |
| 8 | El comercial responde en el chatter → al cliente le llega y lo ve en `/my/solicitud/<id>/resumen` | A mano, dos sesiones |
| 9 | Una **nota interna** del comercial **no** aparece en el portal | A mano. 🔴 Crítico |
| 10 | «Devolver al cliente» deja la solicitud editable otra vez | A mano |
| 11 | «Pedir cambios» desde el portal devuelve la solicitud a `reviewing` y genera actividad | A mano + RPC |
| 12 | Ninguna operación deja el pedido en un estado a medias | Revisión de código: todo dentro de un método del modelo |

---

## 14. Orden sugerido para el agente

1. Leer el PRP original completo (`PRP-PORTAL-PEDIDOS-CLIENTE.md`) y el skill `odoo19-dev`.
2. F1 completa (modelo + controladores + servicio JS). **Es la fase que arregla los tres
   síntomas reportados.** No pasar a F2 sin haberla terminado.
3. F2 (rejilla y rendimiento).
4. F3 (fechas, almacén, repetir).
5. F4 (diálogo). Es la única fase con funcionalidad nueva: si hay que negociar alcance, es
   aquí.
6. F5 (pruebas, README, versión, validadores).
7. **Parar y entregar al usuario para la primera prueba real.** No escribir nada en
   `enteza26` por RPC en ningún momento.

Al entregar, decir explícitamente: **validado por sintaxis, no ejecutado** — y qué partes
dependen de comportamiento de Odoo Enterprise que no se ha podido leer (`_rental_set_dates`,
`_compute_is_rental`).
