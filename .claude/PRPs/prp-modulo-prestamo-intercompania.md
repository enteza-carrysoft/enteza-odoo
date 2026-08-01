# PRP — Módulo Odoo 19: préstamo de material entre compañías del grupo

**Destinatario:** agente programador que desarrollará el módulo.
**Fecha:** 2026-08-01 · **Instancia destino:** `enteza26` (Odoo 19 EE)
**Estado:** diseño aprobado en sus cinco decisiones estructurales (D1–D5); quedan puntos abiertos
marcados como `[PENDIENTE]` que **no bloquean** el desarrollo de la fase 1.

> **Si solo vas a leer una sección antes de empezar, que sea la D5 (§3) junto con §7.0 y §5.6.**
> Es el camino principal del módulo y el que tiene el riesgo técnico serio (concurrencia).

---

## 1. Problema de negocio

El grupo lo forman dos sociedades independientes (no hay matriz-filial):

- **Visueña de Material Plegable, S.L.** ("Vimaple"), compañía `id=1`
- **Stileum**, compañía `id=2`

El negocio es **alquiler de material para eventos** (sillas, mesas, vajilla, cristalería,
cubertería…). Cada sociedad tiene sus propios almacenes en **ubicaciones geográficas distintas**,
y cada artículo tiene existencias propias en cada uno.

El material se alquila por días: sale para un evento y vuelve. La demanda es **muy estacional y
concentrada en fines de semana**, con picos que una sociedad no siempre puede cubrir sola.

**Caso de uso canónico:**

> Vimaple tiene pedidos para el **15 de agosto** por **1.000 unidades** del artículo `001`, pero
> solo dispone de **900**. Stileum tiene unidades libres esa fecha. **Tres días antes** (el 12) se
> trasladan 100 unidades del almacén de Stileum al de Vimaple, para que Vimaple sirva el pedido
> completo.
>
> Cuando el material vuelve del evento, hay que devolverlo a Stileum — **pero antes se comprueba
> si Vimaple lo necesita para sus propios pedidos de los días siguientes**. Si de las 100
> prestadas va a necesitar 30, se devuelven **70** y se retienen 30.

**Lo que hay que construir:** un módulo que detecte los déficits con antelación, proponga
préstamos entre las dos sociedades, ejecute los traslados de ida y vuelta, y calcule cuánto
devolver en cada retorno.

---

## 2. Estado verificado de la instancia

Todo lo de esta sección está **comprobado por RPC contra `enteza26` el 2026-08-01**. No hace falta
volver a verificarlo, pero sí conviene releerlo antes de asumir cualquier otra cosa.

### 2.1 Lo que ya está a favor

| Hecho | Valor | Por qué importa |
|---|---|---|
| Compañías | `1` Visueña, `2` Stileum · **sin `parent_id`** | Son independientes: no hay jerarquía que herede reglas |
| Productos | **1.908 plantillas con `company_id = False`** | **Están compartidos entre compañías.** Es la base imprescindible: un mismo `product.product` tiene existencias en las dos. No romper esto nunca |
| Productos alquilables | 1.054 con `rent_ok = True` | El catálogo de alquiler ya está marcado |
| Módulos instalados | `stock`, `sale_renting`, `sale_stock`, `purchase` | El alquiler nativo y el inventario están operativos |
| Ubicación de alquiler | `Customers/Alquiler` existe **en las dos compañías**, `usage='internal'` | El material alquilado **sigue en el inventario de su compañía** mientras está fuera. Clave para el cálculo del parque |
| Módulo inter-compañía | `sale_purchase_stock_inter_company_rules` **disponible, sin instalar** | La vía "facturar entre empresas" es estándar de Odoo: **no hay que programarla** (ver §9) |

### 2.2 Lo que falta y NO es parte del módulo

Son **prerrequisitos de configuración**. El módulo debe *comprobarlos y fallar con un mensaje
claro* si no están, pero no debe crearlos por su cuenta salvo donde se indique.

| Falta | Estado actual | Quién lo resuelve |
|---|---|---|
| **Almacén de Stileum** | Solo existe `Vimaple` (`WH`, compañía 1). **Stileum no tiene almacén** | Configuración manual previa |
| **Multi-almacén activado** | Grupo `Manage Multiple Warehouses` (id 28) sin activar | Configuración manual previa |
| **Ubicaciones de tránsito** | **0 ubicaciones `usage='transit'`** en toda la base | **Las crea el módulo** (§6.1) |
| **Existencias** | `stock.quant` = **0**. No hay ni una unidad cargada | Carga de inventario inicial, en curso aparte |
| Almacenes por ubicación geográfica | Sin definir cuántos ni cuáles | Negocio · ver `[PENDIENTE-1]` |

> ⚠️ **El módulo no se puede probar de verdad hasta que haya inventario cargado.** Desarróllalo
> contra datos de prueba propios (ver §14, fase 0).

### 2.3 Campos verificados sobre los que se apoya el diseño

Nombres reales en esta instancia, ya comprobados:

**`sale.order`** (documento de alquiler)
- `is_rental_order` (bool, stored)
- `rental_start_date`, `rental_return_date` (datetime, **stored**)
- `warehouse_id` (m2o `stock.warehouse`, **stored**) — de qué almacén sale
- `company_id`, `state`

**`sale.order.line`**
- `is_rental`, `order_is_rental` (bool)
- `product_uom_qty`, `qty_delivered`, `qty_returned`
- `reservation_begin` (datetime)
- `start_date`, `return_date` (datetime) — ⚠️ **`store = False`**

> 🔴 **Consecuencia crítica de diseño:** las fechas de alquiler **de línea no están almacenadas**,
> se calculan desde el pedido. **No se pueden usar en un `search`, ni en un `read_group`, ni en
> SQL.** Toda consulta de demanda por fecha **debe hacerse sobre `sale.order.rental_start_date` /
> `rental_return_date`**. En este negocio un pedido = un evento con fechas únicas, así que es
> correcto; pero no escribas nunca en `start_date`/`return_date` de línea ni los uses para
> filtrar.

**`product.product`**
- `qty_available`, `virtual_available`, `free_qty`
- `qty_in_rent` — unidades actualmente fuera, en alquiler
- `rent_ok`

**`stock.warehouse`**
- `code`, `company_id`, `resupply_wh_ids`, `resupply_route_ids`, `reception_steps`,
  `delivery_steps`

**`res.company`**
- `rental_loc_id` — ubicación a la que va el material alquilado
- `padding_time` — tiempo de seguridad entre alquileres

---

## 3. Decisiones de diseño ya tomadas

Confirmadas con el cliente el 2026-08-01. **No las reabras**; si el desarrollo revela que alguna
es inviable, párate y repórtalo en vez de improvisar otra cosa.

### D1 · La propiedad del stock pasa al que recibe

El préstamo es un **traslado real entre almacenes de distinta compañía**. Las 100 sillas salen
del inventario de Stileum y entran en el de Vimaple, que las sirve como propias.

*Descartado:* consigna con `owner_id` (grupo `Manage Different Stock Owners`). Más fiel
jurídicamente, pero el alquiler nativo de Odoo no reserva bien stock de terceros y obligaría a
reescribir la reserva. **No lo implementes.**

### D2 · La reserva es automática; el movimiento físico lo aprueba una persona

Hay que distinguir dos cosas que son distintas:

- **Reservar** (apuntar que ese material queda comprometido para un pedido): **automático e
  inmediato**, en cuanto se confirma el pedido. No mueve nada, no tiene coste, es reversible.
- **Trasladar** (sacar el material del almacén y llevarlo al otro): **requiere aprobación
  humana**. Nada sale de un almacén sin que un responsable lo confirme.

*Motivo del automatismo en la reserva:* ver D5 — sin reserva inmediata, dos comerciales venden el
mismo material.

*Motivo de la aprobación en el traslado:* el equipo arranca en Odoo 19 sin confianza aún en el
módulo de almacén, y el inventario está a cero. Un traslado automático generaría movimientos
fantasma que nadie ha validado.

### D3 · Devolución con ventana configurable, por defecto 7 días

Al volver el material de un evento, antes de devolverlo a la prestamista se mira **qué pedidos
confirmados tiene la receptora en los próximos N días** (parámetro, por defecto **7**) y se retiene
solo lo necesario para cubrirlos. El resto se devuelve.

### D4 · La facturación va desacoplada

**Todavía no está decidido** si el préstamo se factura entre las dos sociedades, se documenta con
albarán valorado, o no genera documento alguno. Está pendiente de la asesoría fiscal.

**Implicación para ti:** el módulo **mueve stock y no genera ningún documento contable**, pero
debe dejar un **punto de enganche limpio** (§9) para añadir después el documento que se decida,
**sin rehacer el flujo**. No inventes facturación. No crees asientos.

---

### D5 · La comprobación y la reserva ocurren AL CONFIRMAR EL PEDIDO 🔴

**Decisión del 2026-08-01, y es la más importante del documento.**

Los presupuestos sin confirmar **no reservan material** — eso no se cambia. Pero eso crea un
problema real: si la disponibilidad solo se comprueba en un proceso nocturno, entre que un
comercial prepara un presupuesto y lo confirma, **otro comercial puede haber vendido el mismo
material**, y al confirmar ya no hay.

Por tanto, **en el momento de confirmar el pedido de alquiler**, de forma síncrona:

1. Se comprueba la disponibilidad real en la compañía del pedido, para las fechas del pedido.
2. Si no hay suficiente, se comprueba **inmediatamente** si la otra compañía tiene unidades
   libres en esas fechas.
3. Si las tiene, **se reservan en firme en la otra compañía** en ese mismo instante, y se crea el
   préstamo en estado `reserved`, con el **traslado programado** para la fecha que corresponda
   (§7.2, punto 3).
4. Si tampoco las tiene, se avisa al comercial del déficit **antes** de dejarle confirmar (§7.0).

**A partir de ese momento, la reserva es firme:** ningún otro pedido, de ninguna de las dos
compañías, puede contar con ese material para esas fechas.

> Esto **no elimina** el análisis por lotes del §7.1: sigue haciendo falta para detectar déficits
> que aparecen por cambios posteriores (pedidos modificados, devoluciones que no llegan,
> cancelaciones). Pero el camino principal es el de la confirmación, no el cron.

## 4. Alcance del módulo

### 4.1 Qué SÍ hace

1. Calcular, por producto / compañía / fecha, el **parque disponible** y la **demanda comprometida**
   de alquiler.
2. **Al confirmar un pedido**, comprobar la disponibilidad, buscar en la otra compañía lo que
   falte y **reservarlo en firme** en ese instante (D5, §7.0). *Es la función principal.*
3. Detectar por lotes los **déficits** que aparezcan después, como red de seguridad.
4. Generar **propuestas de préstamo**, agrupadas y con fecha de traslado calculada.
5. Ejecutar el **traslado de ida** al aprobarse (dos albaranes vía tránsito).
6. Calcular, al volver el material, **cuánto devolver y cuánto retener**.
7. Ejecutar el **traslado de vuelta**, total o parcial, tantas veces como haga falta.
8. Dar **trazabilidad**: qué se prestó, a quién, para qué pedido, cuánto queda por devolver.
9. **Aparte del préstamo**, añadir una **vista calendario de alquileres pivotada en `event_date`**
   con el lugar de entrega en la ventana flotante (§10.1). Es una petición independiente que se
   entrega en el mismo módulo.

### 4.2 Qué NO hace (no lo programes)

- No factura ni genera asientos contables (§9).
- No mueve material sin aprobación humana (D2). *Reservar sí lo hace solo; trasladar no.*
- No gestiona transporte, rutas de reparto ni costes de portes `[PENDIENTE-4]`.
- No sustituye al inventario ni al alquiler nativos: se **apoya** en ellos.
- No toca los pedidos de alquiler migrados de Odoo 15 (histórico ya cerrado y cuadrado).

---

## 5. El corazón: cálculo de disponibilidad y déficit

Esta es la parte que hay que hacer bien. Todo lo demás es flujo de documentos.

### 5.1 Definiciones

Para un producto `p`, una compañía `c` y un día `d`:

```
parque(p, c)        = unidades que POSEE la compañía c del producto p
                    = suma de stock en TODAS sus ubicaciones internas,
                      incluida la ubicación de alquiler (rental_loc_id)

comprometido(p,c,d) = demanda_propia(p,c,d) + prestado_a_terceros(p,c,d)

  demanda_propia    = suma de product_uom_qty de las líneas de alquiler
                      de pedidos CONFIRMADOS de la compañía c, del producto p,
                      cuyo intervalo [rental_start_date, rental_return_date]
                      solapa con el día d, ampliado por el padding_time

  prestado_a_terceros = suma de qty de las líneas de préstamo en las que c es
                      la PRESTAMISTA, en estado activo (reserved, approved,
                      in_transit, lent, partially_returned), cuyo intervalo
                      de préstamo solapa con el día d

disponible(p,c,d)   = parque(p, c) - comprometido(p, c, d)

deficit(p,c,d)      = max(0, comprometido(p,c,d) - parque(p, c))
```

> 🔴 **`prestado_a_terceros` es imprescindible y es fácil olvidarlo.** Si el material que Stileum
> ha reservado para prestar a Vimaple no cuenta como comprometido en Stileum, Stileum lo venderá
> otra vez y habremos reproducido exactamente el problema que este diseño viene a resolver, solo
> que un nivel más arriba. **La reserva de préstamo tiene el mismo peso que un pedido propio.**

**Por qué `parque` incluye lo que está alquilado:** en esta instancia la ubicación
`Customers/Alquiler` tiene `usage='internal'` (verificado), así que el material que está fuera
en un evento **sigue contando como inventario de su compañía**. Lo que lo hace no-disponible en
una fecha concreta no es dónde está, sino que esté comprometido en esa fecha. Por eso el cálculo
es **temporal**, no de existencias actuales: `qty_available` y `free_qty` **no sirven** para esto.

### 5.2 Regla del solapamiento

Dos alquileres compiten por la misma unidad si sus intervalos se solapan:

```
solapan(A, B)  ⟺  A.inicio < B.fin + padding  ∧  B.inicio < A.fin + padding
```

El `padding_time` de `res.company` es el tiempo de seguridad entre alquileres (limpieza,
revisión, transporte). **Respétalo**: si la empresa lo tiene a 1 día, una silla que vuelve el
lunes no está disponible para un evento del lunes.

### 5.3 Disponibilidad a lo largo de un intervalo

Para prestar de `c_origen` a `c_destino` durante `[inicio, fin]` hay que garantizar que la
prestamista puede prescindir del material **todos los días del intervalo**, no solo el primero:

```
prestable(p, c_origen, inicio, fin) = min( disponible(p, c_origen, d) )  para d en [inicio, fin]
```

Implementación recomendada: **barrido por eventos**, no día a día. Construye una línea temporal
con los puntos de cambio (inicios y fines de los alquileres que solapan el intervalo), y evalúa
el comprometido solo en esos puntos. Con miles de pedidos, iterar día a día por producto es
inviable en rendimiento.

### 5.4 Rendimiento — restricción dura

Hay ~1.054 productos alquilables y el horizonte típico es de semanas. Un cálculo ingenuo
(producto × día × pedido) no aguanta.

**Requisitos:**
- Una sola consulta agrupada para traer la demanda del horizonte, **no una consulta por producto**.
- Filtrar por `sale.order.rental_start_date` / `rental_return_date` (stored e indexables).
- Cachear el parque por producto/compañía durante el cálculo de una tanda.
- Si hace falta, **SQL directo** sobre `sale_order_line` ⨝ `sale_order`. Está permitido y es
  probablemente necesario. Documenta la consulta.
- **Objetivo: el análisis de un horizonte de 30 días debe completarse en menos de 30 segundos.**

### 5.5 Por qué la reserva es lógica y no usa la reserva nativa de Odoo

Podría parecer natural crear el albarán de salida en la prestamista ya al reservar, y dejar que
la reserva nativa de `stock.move` bloquee el material. **No lo hagas.**

La reserva nativa de Odoo bloquea una cantidad **desde ahora y sin fecha de fin**. El alquiler es
**temporal**: unas sillas comprometidas para el 15 de agosto están perfectamente disponibles para
un evento del 2 de agosto que las devuelve el día 3. Bloquearlas desde julio dejaría inmovilizado
medio almacén y haría que el sistema dijera "no hay stock" con el almacén lleno.

Por eso la reserva de préstamo es un **registro lógico acotado en el tiempo** (`enteza.stock.loan.line`
con su intervalo), que participa en `comprometido()` (§5.1) solo en las fechas que le tocan. El
albarán —y con él la reserva nativa— se crea **al aprobar el traslado**, pocos días antes del
evento, que es cuando el bloqueo físico sí tiene sentido.

### 5.6 Concurrencia: dos comerciales confirmando a la vez 🔴

Es el riesgo técnico principal de D5. Dos comerciales confirman pedidos del mismo artículo para
la misma fecha con un segundo de diferencia: ambos calculan disponibilidad, ambos ven 100 libres,
ambos reservan 100. **El sistema acaba de vender 200 unidades que no existen**, y encima con la
apariencia de estar todo correcto.

**Requisito:** el bloque "calcular disponibilidad → decidir → reservar" debe ser **atómico**.

- Toma un **bloqueo de base de datos** sobre las filas afectadas antes de calcular
  (`SELECT ... FOR UPDATE` sobre el producto/compañía, o una tabla de bloqueos dedicada con una
  fila por producto+compañía).
- El bloqueo se libera al terminar la transacción de la confirmación.
- **No sirve** comprobar y volver a comprobar sin bloqueo: reduce la ventana, no la cierra.
- Debe haber una **prueba automatizada de concurrencia** (§15, prueba 10). No des esto por bueno
  con una prueba manual: el fallo aparece justo cuando hay carga, que es en temporada alta.

### 5.7 Qué pedidos cuentan como demanda

- `is_rental_order = True`
- `state = 'sale'` (confirmados). **Los presupuestos (`draft`/`sent`) NO cuentan** — decisión
  confirmada por negocio el 2026-08-01. El riesgo que esto genera se resuelve con D5, no
  contando presupuestos.
- Se excluyen las cantidades ya devueltas (`qty_returned`).
- Se excluyen pedidos cancelados.
- ⚠️ **Excluye los 1.153 pedidos migrados de Odoo 15**, que están todos en `rental_status =
  'returned'` y con fechas de 2026 ya pasadas. Si no los filtras bien, generarán déficits
  fantasma masivos. Filtra por fecha futura y por `rental_status != 'returned'`.

---

## 6. Modelo de datos

### 6.1 Infraestructura de ubicaciones (datos del módulo)

Crear en un fichero de datos:

```xml
<!-- Ubicación de tránsito COMPARTIDA: company_id vacío a propósito -->
<record id="location_inter_company_transit" model="stock.location">
    <field name="name">Tránsito inter-compañía</field>
    <field name="usage">transit</field>
    <field name="company_id" eval="False"/>
    <field name="location_id" ref="stock.stock_location_locations_virtual"/>
</record>
```

> 🔴 **`company_id` vacío es obligatorio.** Una ubicación con compañía asignada no puede recibir
> movimientos de la otra sociedad. Este es el mecanismo estándar de Odoo para mover stock entre
> compañías y el único que funciona sin parches.

**Tipos de operación:** el módulo debe crear, para cada almacén que participe, un tipo de
operación dedicado (`Préstamo salida` / `Préstamo entrada`), **no reutilizar los `OUT`/`IN` de
cliente** — mezclarlos haría ilegibles los albaranes de reparto. Créalos mediante una acción de
configuración (`res.config.settings` o un asistente), **no como datos estáticos**: los almacenes
aún no existen y sus ids no son conocidos.

### 6.2 Modelo principal: `enteza.stock.loan` (préstamo)

Documento cabecera. Un préstamo agrupa varias líneas (varios productos) entre dos compañías para
un intervalo.

| Campo | Tipo | Notas |
|---|---|---|
| `name` | Char | Secuencia `PRE/2026/00001` |
| `company_id` | m2o res.company | **Compañía que PRESTA** (dueña del documento) |
| `company_dest_id` | m2o res.company | Compañía que RECIBE |
| `warehouse_src_id` | m2o stock.warehouse | Almacén de origen (de `company_id`) |
| `warehouse_dest_id` | m2o stock.warehouse | Almacén de destino (de `company_dest_id`) |
| `date_transfer` | Date | Fecha prevista del traslado de ida |
| `date_expected_return` | Date | Fecha prevista de devolución |
| `state` | Selection | ver §6.4 |
| `line_ids` | o2m loan.line | |
| `picking_out_id` | m2o stock.picking | Albarán de salida (compañía prestamista) |
| `picking_in_id` | m2o stock.picking | Albarán de entrada (compañía receptora) |
| `origin_order_ids` | m2m sale.order | Pedidos de alquiler que motivaron el préstamo |
| `origin` | Selection | `confirmation` (nació al confirmar un pedido, D5) / `batch` (análisis por lotes) |
| `date_reserved` | Datetime | Cuándo se reservó en firme. Para auditar quién pilló el material antes |
| `notes` | Html | |

### 6.3 Modelo de línea: `enteza.stock.loan.line`

| Campo | Tipo | Notas |
|---|---|---|
| `loan_id` | m2o | |
| `product_id` | m2o product.product | |
| `qty_proposed` | Float | Lo que calculó el sistema |
| `qty_reserved` | Float | 🔴 Reservado en firme en la prestamista. **Es el campo que alimenta `prestado_a_terceros`** (§5.1) |
| `qty_approved` | Float | Lo que aprobó la persona (editable) |
| `qty_sent` | Float | Realmente trasladado (del albarán) |
| `qty_returned` | Float | Devuelto acumulado |
| `qty_pending` | Float, computed | `qty_sent - qty_returned` |
| `date_from`, `date_to` | Datetime | 🔴 **Intervalo que ocupa la reserva.** Sin esto no se puede calcular `prestado_a_terceros` por fecha: una reserva sin intervalo bloquearía el material para siempre (§5.5) |
| `sale_line_id` | m2o sale.order.line | Línea de pedido que lo motivó, para poder liberar al cancelar |
| `deficit_date` | Date | Día concreto que motivó la línea |

> Indexa `(product_id, date_from, date_to)` y el estado del préstamo: el cálculo de
> `prestado_a_terceros` se ejecuta en cada confirmación de pedido y tiene que ser rápido.

### 6.4 Estados del préstamo

```
draft ──┐
        ├──> reserved ──aprobar──> approved ──validar salida──> in_transit ──validar entrada──> lent
reserved┘   (D5: directo                                                                          │
             al confirmar                                              ┌───devolución parcial─────┤
             el pedido)                                                │                          │
                                                                       └──> partially_returned ───┤
                                                                                                  │
                                                                        devolución total ─────────┴──> returned

cualquiera (salvo returned) ──> cancelled
```

- `draft` — propuesta nacida del análisis por lotes (§7.1). Editable, borrable, **no reserva
  nada**. Es una sugerencia.
- `reserved` — 🔴 **reserva en firme.** El material está comprometido en la prestamista y
  **cuenta como `prestado_a_terceros`** en su disponibilidad (§5.1). Todavía **no se ha movido
  nada físicamente**. Es el estado en el que nacen los préstamos del camino principal (D5) y en
  el que pasarán la mayor parte de su vida: desde que se confirma el pedido hasta tres días antes
  del evento.
- `approved` — un responsable ha autorizado el traslado físico. Genera los albaranes.
- `in_transit` — salida validada; el material está en la ubicación de tránsito.
- `lent` — entrada validada; el material está en el almacén de la receptora y es suyo.
- `partially_returned` — se ha devuelto parte; queda saldo pendiente.
- `returned` — saldo cero. Cerrado.
- `cancelled` — anulado. **Libera la reserva** en la prestamista.

**Reversibilidad:** en `draft` se borra sin rastro. En `reserved` se cancela liberando la reserva,
tampoco hay rastro físico. En `approved` hay albaranes **sin validar**: se pueden **ajustar en
cantidad** (§7.0.2) y, si hay que anular el préstamo entero, cancelarlos. Una vez validada la
salida (`in_transit` en adelante) el movimiento ya ocurrió: cualquier corrección es un movimiento
nuevo en sentido contrario. **Nunca borres el histórico de stock.**

**Fecha límite del traslado:** un préstamo en `reserved` cuyo `date_transfer` ya ha llegado y
sigue sin aprobarse es una alerta operativa: el evento se acerca y el material no se ha movido.
Debe destacarse en la vista de control (§7.6) y, si se estima oportuno, notificar al responsable.

### 6.5 Modelo de análisis: `enteza.stock.deficit` (opcional pero recomendado)

Modelo transitorio o `auto_vacuum` que materializa el resultado del análisis para la vista de
propuestas: `product_id`, `company_id`, `date`, `qty_needed`, `qty_available`, `qty_deficit`,
`qty_available_other_company`, `loan_id` (si ya se cubrió).

Permite que el usuario vea el panorama antes de aprobar nada y que la vista sea agrupable y
filtrable sin recalcular.

---

## 7. Flujo funcional completo

### 7.0 Camino principal: confirmación del pedido (D5) 🔴

**Es el flujo que más se va a ejecutar y el que más importa.** Se engancha en
`sale.order.action_confirm()`, antes de que Odoo confirme.

```
Comercial pulsa «Confirmar» en un pedido de alquiler
   │
   ├─ (bloqueo de concurrencia — §5.6)
   │
   ├─ Para cada línea de alquiler del pedido:
   │     falta = cantidad - disponible(producto, compañía_pedido, fechas_pedido)
   │
   ├─ ¿falta <= 0 en todas las líneas?
   │     SÍ → confirmar con normalidad. Fin.
   │
   ├─ Hay faltas: para cada una, mirar la OTRA compañía
   │     prestable = prestable(producto, otra_compañía, fechas_pedido)
   │
   ├─ ¿prestable cubre la falta?
   │     SÍ  → reservar en firme en la otra compañía
   │           crear enteza.stock.loan en estado `reserved`
   │           con date_transfer = inicio_alquiler - dias_antelacion
   │           confirmar el pedido
   │           avisar al comercial: «cubierto con préstamo de <compañía>,
   │           traslado programado para el <fecha>»
   │
   │     PARCIAL o NO →  §7.0.1
   │
   └─ (liberar bloqueo al cerrar la transacción)
```

#### 7.0.1 Qué pasa si no hay material ni en la otra compañía

**No bloquear la confirmación en silencio ni dejar pasar el pedido sin avisar.** El comportamiento
por defecto es:

- Mostrar un **aviso claro y bloqueante** al comercial, indicando **artículo, fecha, cuánto falta
  y cuánto se ha podido cubrir**.
- Permitir confirmar de todos modos **solo a quien tenga el grupo de responsable**, dejando el
  pedido marcado con un indicador de **déficit no cubierto** visible en la lista de pedidos.
- Lo reservable **se reserva igualmente** (cubrir 80 de 100 es mejor que no cubrir nada), y el
  déficit residual queda registrado.

*Motivo:* el comercial tiene que poder cerrar la venta y buscar una solución (subcontratar,
cambiar de artículo, renegociar la fecha), pero nadie puede confirmar a ciegas un pedido que no
se puede servir. Ver `[PENDIENTE-8]`.

#### 7.0.2 Modificar un pedido ya confirmado: AJUSTAR, no cancelar y rehacer 🔴

**Dato de la instancia, confirmado por el cliente el 2026-08-01:** en Odoo 19, un pedido ya
confirmado admite cambios de cantidad **sin cancelar los albaranes**, siempre que esos albaranes
no estén validados. Odoo propaga el cambio a los movimientos de stock por sí solo.

**Consecuencia de diseño: el módulo debe comportarse igual.** Modificar un pedido **ajusta** el
préstamo existente; no lo cancela para crear otro. Cancelar y rehacer generaría un rastro de
préstamos anulados ilegible, rompería la trazabilidad con el pedido de origen y perdería el
`date_reserved` — que es lo que determina quién pilló el material primero (`[PENDIENTE-9]`).

Comportamiento por estado del préstamo:

| Estado | Qué hacer al cambiar el pedido |
|---|---|
| `reserved` | Trivial: actualizar `qty_reserved` y el intervalo. No hay nada físico. |
| `approved` | **Aquí aplica el dato de arriba.** Los albaranes existen pero no están validados: **actualiza las cantidades de los movimientos**, apoyándote en la propagación nativa. No canceles los albaranes. |
| `in_transit` | La salida ya está validada: el material físicamente ya salió. Una reducción **no se puede deshacer hacia atrás**; el sobrante entra igual y pasa al circuito de devolución (§7.5). |
| `lent` en adelante | Solo por devolución. Nunca tocando el albarán original. |

**Reglas:**
- **Aumentar cantidad**: recalcular el déficit y ampliar la reserva; si no hay prestable
  suficiente, avisar como en §7.0.1.
- **Reducir cantidad**: liberar la parte proporcional de la reserva. Nunca por debajo de lo ya
  entregado.
- **Cambiar fechas**: es lo más delicado — el intervalo de la reserva se mueve, y en las fechas
  nuevas puede no haber disponibilidad aunque la hubiera en las viejas. **Recalcular contra las
  fechas nuevas**, no suponer que si valía antes vale ahora.
- **Cancelar el pedido**: libera las reservas. Si el préstamo ya se trasladó físicamente, no se
  libera solo: se marca para revisión (§12, caso 11).

> Extrae la comprobación a un **método reutilizable** que sirva igual para `action_confirm` y para
> el `write` de las líneas. No dupliques el cálculo en dos sitios: divergirán.

### 7.1 Análisis por lotes (red de seguridad, sin efectos)

Con D5, la mayoría de los déficits se detectan y cubren al confirmar. Este proceso es la **red de
seguridad** para lo que se escapa: pedidos modificados después de confirmar, material que no
vuelve a tiempo, cancelaciones que liberan stock y permiten devolver antes, cambios de fecha.

Un **cron diario** (configurable, por defecto de madrugada) recorre el horizonte de análisis
(parámetro, por defecto **30 días**) y para cada producto/compañía/fecha calcula el déficit
(§5). Resultado: registros de `enteza.stock.deficit`.

**El cron no crea préstamos ni mueve nada.** Solo analiza. Debe poder lanzarse a mano desde un
botón.

Además debe **señalar las reservas sobrantes**: préstamos reservados cuyo pedido de origen se ha
reducido o cancelado y que están inmovilizando material sin necesidad. Es dinero parado.

### 7.2 Propuesta

Desde la vista de déficits, una acción **"Proponer préstamos"** (manual, o el propio cron si se
activa la opción) agrupa los déficits y, para cada uno:

1. Comprueba si la **otra compañía** tiene `prestable(p, c_otra, inicio, fin) > 0` (§5.3).
2. Calcula `qty = min(deficit, prestable)`.
3. Calcula la **fecha de traslado** = fecha del déficit − `dias_antelacion` (parámetro, **por
   defecto 3 días**; ver `[PENDIENTE-3]`).
4. Agrupa en un único `enteza.stock.loan` en `draft` todas las líneas que compartan
   (compañía origen, compañía destino, almacén origen, almacén destino, fecha de traslado).

**Si la otra compañía no tiene suficiente**, se propone lo que haya y se marca el déficit como
**cubierto parcialmente**. Nunca se propone más de lo prestable. El déficit residual queda
visible: es información para que comercial decida (subcontratar, renegociar con el cliente…).

### 7.3 Aprobación

Un responsable abre la propuesta, ajusta `qty_approved` si quiere y pulsa **Aprobar**. Entonces:

1. **Se revalida la disponibilidad.** Si el préstamo venía de `reserved` (camino D5), el material
   ya estaba comprometido y la revalidación debe salir bien: si no sale, hay un fallo en el
   cálculo de reservas y **hay que registrarlo como incidencia**, no taparlo. Si venía de `draft`
   (análisis por lotes), la comprobación es real: entre la propuesta y la aprobación han podido
   entrar pedidos nuevos. En cualquiera de los dos casos, si no hay stock prestable suficiente,
   **avisar y no dejar aprobar** sin ajustar la cantidad.
2. Se crean los dos albaranes:
   - **Salida** en la compañía prestamista: `WH_origen/Stock` → `Tránsito inter-compañía`
   - **Entrada** en la compañía receptora: `Tránsito inter-compañía` → `WH_destino/Stock`
3. Estado → `approved`.

> ⚠️ Los dos albaranes pertenecen a **compañías distintas**. Créalos con
> `with_company(...)` / `sudo()` según corresponda, y ten presente que el usuario que aprueba
> puede no tener permiso sobre las dos. Ver §11.

### 7.4 Traslado de ida

El almacén de la prestamista valida la salida → `in_transit`. El almacén de la receptora valida
la entrada → `lent`. A partir de ahí las unidades **son inventario de la receptora** y el
alquiler nativo las reserva y las sirve como cualquier otra.

### 7.5 Retorno del evento y devolución inteligente

Cuando el material vuelve del evento (el alquiler nativo lo devuelve a `WH_destino/Stock`), el
préstamo entra en la cola de devolución.

**Cálculo de cuánto devolver** — es el punto que pidió el cliente explícitamente:

```
ventana        = hoy .. hoy + N días          (N = parámetro, por defecto 7)
necesita       = max( comprometido(p, c_receptora, d) )  para d en ventana
propio         = parque(p, c_receptora) - prestado_pendiente(p, c_receptora)
retener        = min( prestado_pendiente, max(0, necesita - propio) )
devolver       = prestado_pendiente - retener
```

**Ejemplo del cliente:** prestadas 100, necesita 30 en la ventana y no le llega con lo propio →
`retener = 30`, `devolver = 70`. ✔

**Reglas:**
- El resultado es una **propuesta**, no una ejecución (D2). El responsable puede cambiar la
  cantidad.
- Se pueden hacer **devoluciones parciales sucesivas**: cada una genera su par de albaranes
  (receptora → tránsito → prestamista) y actualiza `qty_returned`.
- Cuando `qty_pending` llega a 0 en todas las líneas → `returned`.
- 🔴 **Prioridad en conflicto:** si la **prestamista** también necesita el material en la ventana,
  su necesidad **manda** sobre la retención de la receptora — es su material. Implementa esta
  regla y hazla visible en la propuesta (mostrando ambas necesidades). Ver `[PENDIENTE-5]`.

### 7.6 Vista de control

Una vista que responda de un vistazo: **qué tengo prestado, a quién, desde cuándo, cuánto queda
por devolver y qué se espera devolver esta semana**. Es lo que va a mirar el responsable a diario.

---

## 8. Parámetros de configuración

Todos en `res.config.settings` (ámbito compañía) o `ir.config_parameter`, **ninguno en el código**:

| Parámetro | Por defecto | Qué controla |
|---|---|---|
| `dias_antelacion_traslado` | 3 | Días antes del evento en que se hace el traslado de ida |
| `horizonte_analisis` | 30 | Días hacia adelante que mira el detector de déficits |
| `ventana_retencion` | 7 | Ventana de la devolución inteligente (D3) |
| `cron_activo` | True | Si el análisis diario corre solo |
| `proponer_automatico` | False | Si el cron, además de analizar, crea propuestas en borrador |
| `almacen_prestamo_<compañía>` | — | Almacén por defecto de cada compañía para préstamos |

---

## 9. Punto de enganche para la facturación (D4)

**No implementes facturación.** Pero deja el flujo preparado:

1. En `enteza.stock.loan`, define los métodos vacíos y documentados:
   ```python
   def _post_loan_hook(self):
       """Se llama tras validar la entrada del traslado de ida (estado -> lent).
       Punto de extensión para generar el documento entre compañías que decida
       la asesoría fiscal. En la versión base no hace nada."""
       return

   def _post_return_hook(self, returned_lines):
       """Ídem tras cada devolución."""
       return
   ```
2. Añade a la cabecera los campos `move_id` (m2o `account.move`, sin usar) y `amount_total`
   (computed, 0 en la versión base) para no tener que migrar el modelo después.
3. **Documenta en el README** que la vía prevista si se decide facturar es instalar
   `sale_purchase_stock_inter_company_rules` (disponible en la instancia, sin instalar) y
   engancharlo en `_post_loan_hook`, **no reescribir el módulo**.

---

## 10. Interfaz de usuario

- **Menú propio**: "Préstamos entre empresas", dentro de Inventario.
- **Vista lista + formulario** de `enteza.stock.loan`, con la barra de estado y los botones de
  acción (Aprobar, Cancelar, Proponer devolución, Ver albaranes).
- **Vista de déficits** agrupable por producto, fecha y compañía, con indicador de si la otra
  compañía puede cubrirlo.
- **Botón inteligente** en el pedido de alquiler: si un pedido está cubierto gracias a un
  préstamo, que se vea desde el pedido.
- **Todo en castellano.** La instancia trabaja en español; las etiquetas, los mensajes de error y
  los nombres de menú van en castellano. Incluye `i18n/es_ES.po`.

### 10.1 Vista calendario de alquileres pivotada en la fecha del evento

Funcionalidad **independiente del préstamo** pero que se entrega en el mismo módulo, por petición
del cliente (2026-08-01).

#### Situación verificada

| Hecho | Comprobado en `enteza26` |
|---|---|
| Existe calendario de alquiler | **Sí.** Vista `rental.order.calendar` (id 1703), que hereda de `sale.order.calendar` (id 1504) |
| Sobre qué pivota | `date_start = rental_start_date`, `date_stop = rental_return_date`, `color = rental_status`, `edit = 0` |
| Está accesible | Sí: las acciones *Rental Orders* (626, 627, 628) ya incluyen `calendar` en su `view_mode` |
| Qué muestra la ventana flotante | `partner_id` (con avatar), `amount_total`, `payment_term_id` |
| `event_date` | Campo del módulo **`rental_custom`**, `date`, **stored**, en `sale.order` y en `sale.order.line` |
| ¿Está informado? | **Sí: los 1.153 pedidos de alquiler lo tienen relleno** |
| `partner_shipping_id` | Nativo, m2o `res.partner`, **required**, stored, "Delivery Address". Informado en los pedidos |

🔴 **Ojo con la premisa:** el calendario **ya existe**; lo que no hace es pivotar sobre la fecha
del evento. Y la diferencia importa: en los datos reales, un pedido con evento el **27/06** tiene
`rental_start_date` el **26/06**, porque el material se entrega el día antes. El calendario nativo
muestra el día de la entrega, no el día del evento — que es el que el negocio quiere ver.

**Por tanto: no construyas un calendario desde cero. Hereda y ajusta.**

#### Qué hay que hacer

1. **Vista calendario nueva**, heredando de `sale.order.calendar`, con:
   - `date_start = "event_date"`
   - **sin `date_stop`**: el evento es de un día. (Si negocio pide después mostrar la duración,
     se añade `rental_return_date` como `date_stop`, pero no de entrada.)
   - `color = "rental_status"`, `edit = "0"`, `mode = "month"`
   - Dominio del la acción: `[('is_rental_order', '=', True)]`
2. **Contenido de la ventana flotante**, en este orden:
   - Cliente (`partner_id`) — ya está
   - 🔴 **Lugar de entrega (`partner_shipping_id`) justo debajo del cliente** — es lo que pidió el
     cliente expresamente
   - Importe total y lo demás que ya trae la vista heredada
3. **Acción y menú propios** en la aplicación de Alquiler: *"Calendario de eventos"*. **No
   sustituyas** el calendario nativo de alquiler: convive con él. Uno responde "qué sale del
   almacén hoy" y el otro "qué eventos hay el sábado"; los dos son útiles y son preguntas
   distintas.
4. **`partner_shipping_id` solo se ve con el ajuste activado** (§10.2). Si el ajuste está
   desactivado, el campo desaparecerá también del popover. Ténlo en cuenta al probar: si no lo
   ves, mira primero el ajuste antes de tocar la vista.

#### Cuidado con `event_date` en dos modelos

`event_date` existe **tanto en `sale.order` como en `sale.order.line`**. Para el calendario usa
**siempre el del pedido**. Si en los datos reales aparecen líneas con fecha de evento distinta a
la de su pedido, **no lo resuelvas por tu cuenta**: repórtalo, porque significa que un pedido
puede cubrir varios eventos y eso cambia el diseño del calendario.

### 10.2 Dirección de entrega — ✅ RESUELTO el 2026-08-01

> **Ya está activado en `enteza26`.** El grupo `account.group_delivery_invoice_address` (id 39) se
> añadió a los `implied_ids` de `base.group_user`, y los 10 usuarios internos lo tienen heredado.
> `partner_shipping_id` se ve ya en el formulario de pedido y presupuesto, y estará disponible
> para el popover del calendario (§10.1). Script: `scripts/enable-delivery-address.ts`
> (`--revert --execute` lo deshace).
>
> Se deja documentado el diagnóstico porque explica **por qué** el campo no aparecía y evita que
> alguien concluya que falta el campo y lo cree duplicado.

**Diagnóstico verificado el 2026-08-01.** El campo *lugar de entrega* **no faltaba en la 19:
estaba oculto por configuración.**

- En la **15**, el grupo `Addresses in Sales Orders` (id 35) lo tenían **los 22 usuarios internos**
  → el campo se veía.
- En la **19**, el grupo `Delivery Address` (id 39) **existe pero no está activado**: no aparece
  entre los `implied_ids` de `Role / User`, y los usuarios no tienen más grupos que ése.

**Solución (no requiere código):** *Ventas → Configuración → Ajustes → sección Presupuestos y
pedidos → activar **«Direcciones de cliente»***. Al activarlo aparecen en el formulario de
pedido/presupuesto la **dirección de entrega** y la **dirección de facturación**.

⚠️ **El identificador técnico es `account.group_delivery_invoice_address`, no
`sale.group_...`** — en Odoo 19 este grupo vive en el módulo `account`. Si lo referencias con el
prefijo antiguo, la instalación del módulo fallará con un error de referencia externa.

Es un ajuste de compañía y afecta a todos los usuarios. **El módulo NO debe activarlo ni
desactivarlo por su cuenta**, pero **sí debe comprobarlo al instalarse y avisar con un mensaje
claro** si estuviera desactivado, porque sin él la vista calendario sale incompleta.

---

## 11. Multi-compañía y seguridad — la parte delicada

🔴 **Es donde más fácil es equivocarse.** Un préstamo implica por definición dos compañías, y las
reglas de registro de Odoo aíslan por compañía.

**Requisitos:**

1. **Reglas de registro:** el préstamo debe ser visible para usuarios de **ambas** compañías. La
   regla no puede ser el clásico `('company_id', 'in', company_ids)`: hay que contemplar también
   `company_dest_id`:
   ```python
   ['|', ('company_id', 'in', company_ids), ('company_dest_id', 'in', company_ids)]
   ```
2. **Creación de registros de la otra compañía:** el albarán de entrada pertenece a la receptora.
   Un usuario de la prestamista puede no tener acceso. Usa `with_company()` y `sudo()` **de forma
   acotada y comentada**, nunca un `sudo()` global al método entero.
3. **Grupos:**
   - `Préstamos: usuario` — ve los préstamos, propone.
   - `Préstamos: responsable` — aprueba, cancela, ajusta cantidades.
   Solo el responsable puede pasar de `draft` a `approved`.
4. **Ubicación de tránsito sin compañía** (§6.1): si le pones compañía, la mitad del flujo falla
   con un error de acceso poco descriptivo. Es la causa nº1 de problemas en este tipo de módulo.
5. **Productos compartidos:** no añadas `company_id` a productos ni a sus reglas. Si el módulo
   rompe el hecho de que los 1.908 productos sean compartidos, rompe la premisa entera.

---

## 12. Casos límite que hay que resolver

Todos deben tener comportamiento definido y **prueba automatizada**:

1. **Ninguna compañía tiene suficiente.** Se propone lo máximo posible; el déficit residual queda
   visible y señalado. No fallar en silencio.
2. **El pedido que motivó el préstamo cambia de fecha después de aprobarlo.** Si los albaranes no
   están validados, se ajustan (§7.0.2) y se **recalcula la disponibilidad para las fechas
   nuevas** — que puede no haberla. Si ya se validó la salida, el préstamo **no se deshace solo**:
   se marca como "revisar" y se avisa al responsable.
3. **El material no vuelve del evento** (roto, perdido, retrasado). El préstamo se queda en
   `lent`; debe poderse cerrar manualmente con una justificación, y la diferencia debe ser
   visible `[PENDIENTE-6]`.
4. **Devoluciones parciales sucesivas.** Tres devoluciones de 30, 20 y 20 sobre 100 prestadas
   dejan 30 pendientes. Los importes acumulados deben cuadrar siempre.
5. **Dos déficits del mismo producto en fechas próximas.** No generar dos préstamos solapados que
   muevan el mismo material dos veces; agrupar.
6. **Préstamo encadenado**: la receptora presta a su vez a un tercero. Con dos compañías no
   aplica hoy, pero **no lo impidas por diseño** — el modelo no debe asumir que solo hay dos.
7. **Unidad de medida.** Si algún artículo se maneja en unidades distintas (docenas de platos),
   respeta `product_uom`. No asumas unidades sueltas.
8. **Fechas con hora.** `rental_start_date` es datetime y el negocio razona en días. Define y
   documenta la conversión (y el huso horario), o tendrás errores de un día en los límites.
9. **Confirmación simultánea de dos pedidos** que compiten por el mismo material (§5.6). Prueba
   obligatoria.
10. **Pedido confirmado y luego ampliado.** Se confirma por 900 (sin préstamo) y después se sube
    a 1.000. Debe crearse la reserva por las 100 nuevas, no quedarse sin cubrir en silencio.
10bis. **Préstamo ya aprobado y el pedido se reduce.** Con los albaranes creados y sin validar,
    las cantidades se **ajustan en el propio albarán** (§7.0.2). Comprobar que no queda ningún
    albarán cancelado ni ningún préstamo duplicado, y que la reserva liberada vuelve a estar
    disponible en la prestamista.
11. **Cancelación con préstamo ya trasladado.** El material está físicamente en la otra compañía
    y el pedido que lo justificaba desaparece. No devolver automáticamente: marcar para revisión
    y proponer la devolución por el circuito normal.
12. **Reserva huérfana.** Préstamo en `reserved` cuyo pedido de origen se canceló pero la
    liberación falló. El análisis por lotes debe detectarlo (§7.1).

---

## 13. Restricciones técnicas

- **Odoo 19 Enterprise.** Sintaxis moderna: sin `attrs`/`states` en las vistas (eliminados desde
  17), usa atributos condicionales directos (`invisible="..."`, `readonly="..."`).
- **Dependencias del manifiesto:** `stock`, `sale_renting`, `sale_stock`. **No** dependas de
  `account` (la facturación va desacoplada, D4) ni de módulos OCA.
- **Nombre técnico sugerido:** `enteza_prestamo_intercompania`.
- **No modificar** modelos nativos con `write` masivos ni sobrescribir métodos de reserva de
  `stock.move` salvo necesidad justificada y documentada.
- **Apóyate en la propagación nativa de cantidades** de Odoo 19 (§7.0.2) en vez de reimplementar
  la sincronización pedido↔albarán. Si en algún caso no propaga como esperas, **documenta el caso
  concreto** antes de escribir código que lo sustituya: casi siempre es una condición del estado
  del movimiento, no una carencia de Odoo.
- **No tocar** los datos migrados de Odoo 15 (facturas, asientos, pedidos ya cuadrados al
  céntimo). El módulo es aditivo.
- **Código y comentarios en castellano**, coherente con el resto del proyecto.

---

## 14. Plan de desarrollo por fases

**Fase 0 — Entorno y datos de prueba.**
Crear almacén de Stileum, activar multi-almacén, cargar existencias ficticias y varios pedidos de
alquiler que provoquen déficit. Sin esto no se puede validar nada. *No tocar producción.*

**Fase 1 — Motor de cálculo.**
`parque`, `comprometido`, `disponible`, `prestable` (§5), con pruebas unitarias sobre casos
construidos a mano, incluido el padding y el solapamiento. **Es la fase crítica: si el cálculo
falla, todo lo demás sobra.** Sin interfaz todavía.

**Fase 2 — Documento, reserva y flujo de ida.**
Modelos, estados, vistas. **El enganche en `action_confirm` con la reserva en firme y el bloqueo
de concurrencia (§7.0, §5.6) va en esta fase, no en la 4**: es el camino principal, no una
automatización opcional. Después, aprobación y generación de los dos albaranes vía tránsito. Al
terminar, el caso canónico del §1 debe funcionar de punta a punta hasta `lent`, y las pruebas 9 a
14 del §15 deben pasar.

**Fase 3 — Devolución inteligente.**
Cálculo de retención (§7.5), devoluciones parciales, cierre. Al terminar, el ejemplo de las 100
prestadas / 30 retenidas / 70 devueltas debe salir solo.

**Fase 4 — Red de seguridad y control.**
Cron de análisis por lotes, detección de reservas huérfanas y sobrantes, vista de control,
parámetros de configuración, permisos y reglas multi-compañía.

**Fase 5 — Pulido.**
Traducciones, mensajes de error claros, README, casos límite del §12.

**Fase A — Vista calendario de eventos (§10.1). Independiente del resto.**
No depende de ninguna otra fase ni del inventario: `event_date` ya está informado en los 1.153
pedidos. **Se puede hacer la primera y entregar por separado**, y probablemente convenga: es
pequeña, es visible y le da al equipo algo útil desde el primer día en Odoo 19, mientras el
préstamo —que necesita inventario cargado— aún no se puede ni probar.

> Entrega **fase a fase, validando cada una** antes de seguir. No entregues las cinco de golpe.

---

## 15. Pruebas de aceptación

El módulo se da por bueno cuando pasan estas pruebas, automatizadas con `TransactionCase`:

1. **Caso canónico.** Vimaple con 900 unidades y pedidos por 1.000 para el 15/08; Stileum con 200
   libres → se propone un préstamo de 100 con traslado el 12/08. Tras aprobar y validar, Vimaple
   tiene 1.000 y Stileum 100.
2. **Devolución parcial.** Con 100 prestadas y necesidad de 30 en los 7 días siguientes → propone
   devolver 70 y retener 30. Tras validar, `qty_pending = 30` y estado `partially_returned`.
3. **Sin stock en la otra compañía.** Déficit de 100 y solo 40 prestables → propone 40 y deja 60
   de déficit residual visible.
4. **Solapamiento y padding.** Una unidad alquilada del 10 al 12 con padding de 1 día no está
   disponible para un evento del 13.
5. **Aislamiento multi-compañía.** Un usuario de Stileum ve el préstamo en el que es prestamista;
   un usuario sin acceso a ninguna de las dos no lo ve.
6. **Los pedidos migrados no generan déficit.** Con los 1.153 pedidos históricos en
   `rental_status='returned'`, el análisis no propone nada.
7. **Rendimiento del análisis.** 30 días con 1.000 productos y 500 pedidos en **menos de 30
   segundos**.
8. **Idempotencia del cron.** Ejecutarlo dos veces seguidas no duplica déficits ni propuestas.
9. **Reserva al confirmar (D5).** Vimaple con 900 unidades confirma un pedido de 1.000 para el
   15/08 → el pedido queda confirmado, se crea un préstamo en `reserved` por 100 con
   `date_transfer = 12/08`, y **la disponibilidad de Stileum para esas fechas baja en 100**.
10. **Concurrencia (§5.6).** Dos confirmaciones simultáneas del mismo artículo y fecha, con stock
    para solo una: **una debe cubrirse y la otra recibir el aviso de déficit**. Nunca las dos.
    Prueba con transacciones concurrentes reales, no secuenciales.
11. **Doble venta del material prestado.** Tras reservar 100 de Stileum para Vimaple, un pedido
    de Stileum para esas mismas fechas **no puede** contar con esas 100 unidades.
12. **Liberación al cancelar.** Cancelar el pedido de origen de un préstamo en `reserved` devuelve
    la disponibilidad a la prestamista.
13. **Ampliación de pedido confirmado.** Subir de 900 a 1.000 en un pedido ya confirmado crea la
    reserva de las 100 nuevas.
13bis. **Ajuste sobre préstamo aprobado.** Con el préstamo en `approved` y los albaranes sin
    validar, reducir el pedido debe **ajustar las cantidades de los albaranes existentes**, sin
    cancelarlos ni crear un préstamo nuevo, conservando el mismo `name` y el mismo
    `date_reserved`.
14. **Rendimiento de la confirmación.** Confirmar un pedido de 30 líneas debe tardar **menos de 3
    segundos**: es una operación interactiva y el comercial está esperando delante.
15. **Calendario de eventos (§10.1).** Un pedido con `event_date = 27/06` y
    `rental_start_date = 26/06` aparece en el calendario nuevo el **27**, y en el calendario nativo
    de alquiler sigue apareciendo el **26**. Los dos calendarios conviven sin pisarse.
16. **Lugar de entrega en el popover.** Con el ajuste de direcciones activado, la ventana flotante
    muestra el `partner_shipping_id` justo debajo del cliente.

---

## 16. Decisiones pendientes

Ninguna bloquea las fases 1 y 2. **Consúltalas antes de la fase que las necesita** en vez de
elegir por tu cuenta.

- **`[PENDIENTE-1]` Almacenes reales.** Cuántos almacenes tendrá cada compañía y en qué
  ubicaciones. Hoy solo existe uno. El diseño soporta N, pero hay que saber si el préstamo es
  siempre entre almacenes concretos o hay que elegir origen. *Necesario para fase 2.*
- ~~`[PENDIENTE-2]` ¿Los presupuestos cuentan como demanda?~~ **RESUELTO el 2026-08-01:** no
  reservan. El riesgo de que dos comerciales vendan lo mismo se resuelve comprobando y reservando
  **al confirmar** (D5, §7.0), no contando presupuestos.
- **`[PENDIENTE-3]` ¿Los 3 días de antelación son fijos?** Puede depender de la distancia entre
  almacenes (no es lo mismo Sevilla-Jerez que otra provincia). Si depende, el parámetro debe ser
  por par de almacenes, no global. *Necesario para fase 2.*
- **`[PENDIENTE-4]` Transporte y costes.** Si hay que registrar portes o planificar camiones, es
  otro alcance. Hoy queda fuera.
- **`[PENDIENTE-5]` Prioridad en conflicto.** Se ha asumido que la necesidad de la prestamista
  manda sobre la retención de la receptora. **Confirmar con negocio.** *Necesario para fase 3.*
- **`[PENDIENTE-6]` Material perdido o roto durante un préstamo.** Cómo se salda: ¿se factura, se
  repone en especie, se asume? *Necesario para fase 5.*
- **`[PENDIENTE-7]` Facturación (D4).** Pendiente de la asesoría fiscal. No condiciona el
  desarrollo si se respetan los puntos de enganche del §9.
- **`[PENDIENTE-8]` ¿Se puede confirmar un pedido que no se puede servir?** El diseño asume que
  sí, pero solo con permiso de responsable y dejando el pedido marcado (§7.0.1). Confirmar con
  negocio: la alternativa es impedirlo del todo. *Necesario para fase 2.*
- **`[PENDIENTE-9]` ¿Quién manda si las dos compañías necesitan el material a la vez?** Hoy vence
  quien reserva primero (`date_reserved`). Si el grupo quiere otra prioridad —por margen del
  pedido, por antigüedad del cliente, por sociedad— hay que definirla. *Necesario para fase 2.*

---

## 17. Avisos finales

1. **El inventario está a cero en producción.** Hasta que se cargue, el módulo dará "no hay stock"
   en todo. No es un fallo del módulo.
2. **El equipo está arrancando en Odoo 19 esta misma semana** y llevará el almacén **en paralelo**
   con una aplicación externa hasta que confíe en Odoo. Este módulo entra en un sistema que aún
   no tiene rodaje: prioriza que **nada se mueva sin aprobación humana** y que todo sea
   reversible y trazable, por encima de la automatización.
3. **Producción es producción.** `enteza26` tiene la contabilidad migrada y cuadrada al céntimo.
   Desarrolla y prueba en una copia; no ejecutes nada del módulo contra la base real sin que lo
   valide el responsable del proyecto.
