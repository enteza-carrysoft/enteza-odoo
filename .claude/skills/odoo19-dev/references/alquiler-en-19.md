# El alquiler en Odoo 19 — lo que hay que saber antes de tocarlo

Todo lo de este documento está **verificado por RPC contra `enteza26` y contra el código
fuente de Odoo 19/18 Enterprise** (2026-08-01). Donde el código y la intuición chocan, manda
el código.

## Los tres módulos que intervienen

| Módulo | Estado | Qué aporta |
|---|---|---|
| `sale_renting` | instalado | Alquiler nativo: `is_rental_order`, fechas, `rental_status`, precios |
| `sale_stock_renting` | **instalado** | **El motor de disponibilidad**, `rental_loc_id`, el padding y los albaranes de alquiler |
| `rental_custom` | instalado | Módulo del cliente. Aporta **`event_date`** en `sale.order` y en `sale.order.line` |

🔴 **`sale_stock_renting` se pasa por alto con facilidad** y es el que contiene casi todo lo
importante. Si un análisis concluye "Odoo no trae cálculo de disponibilidad de alquiler", está
mirando solo `sale_renting`.

## Campos y su almacenamiento

Lo que está o no almacenado condiciona qué se puede hacer con cada campo.

### `sale.order`

| Campo | Tipo | Store | Nota |
|---|---|---|---|
| `is_rental_order` | bool | ✅ | |
| `rental_start_date` | datetime | ✅ | Cuándo SALE el material del almacén |
| `rental_return_date` | datetime | ✅ | |
| `rental_status` | selection | ✅ | Valores abajo |
| `warehouse_id` | m2o | ✅ | De qué almacén sale |
| `event_date` | date | ✅ | De `rental_custom`. Informado en los 1.153 pedidos migrados |

**`rental_status`**: `draft` (Quotation) · `sent` · `pickup` (Reserved) · `return` (Pickedup)
· `returned` · `cancel`.

### `sale.order.line`

| Campo | Tipo | Store | Nota |
|---|---|---|---|
| `is_rental` | bool | ✅ | Calculado pero `readonly=False`: se puede escribir |
| `product_uom_qty`, `qty_delivered`, `qty_returned` | float | ✅ | |
| `product_uom_id` | m2o | ✅ | ⚠️ En la 15 era `product_uom` |
| `reservation_begin` | datetime | ✅ | Ver abajo: **lleva el padding restado** |
| `start_date` / `return_date` | datetime | ❌ | `related` de las fechas del pedido |
| `event_date` | date | ✅ | |

⚠️ **Matiz importante sobre `start_date` / `return_date`.** No están almacenados, así que **no
sirven para `read_group` ni para SQL**. Pero **sí son buscables en un `search`**: son `related`
de campos almacenados y el ORM traduce el dominio. El propio Odoo los usa así en
`_get_active_rental_lines`. La idea de que "no se pueden usar para filtrar" es falsa a medias.

### `is_rental` al crear pedidos

Se calcula como `is_product_rentable and context.get('in_rental_app')`. Para crear un pedido
de alquiler por código o en una prueba:

```python
pedido = env['sale.order'].with_context(in_rental_app=True).create({...})
```

Sin ese contexto las líneas **no serán de alquiler** aunque el producto tenga `rent_ok`.

## El padding: dos campos que se confunden

| Campo | Dónde | Unidad | Qué es |
|---|---|---|---|
| `res.company.padding_time` | compañía | **horas** | Solo el **valor por defecto**. Al instalar se copia a un `ir.default` de `product.template.preparation_time` |
| `product.template.preparation_time` | producto, `company_dependent` | **horas** | **El que manda de verdad** |

Hoy ambos valen **0** en `enteza26`.

`sale_stock_renting` **sobrescribe** el cálculo de `reservation_begin`:

```python
reservation_begin = start_date - timedelta(hours=product.preparation_time)
```

Es decir: **el padding es previo al alquiler** (tiempo de preparación) y **ya viene aplicado
en `reservation_begin`**. No hay que volver a restarlo. Ojo: en `sale_renting` a secas
`reservation_begin` es igual a `rental_start_date`; la resta la añade `sale_stock_renting`.

## El motor de disponibilidad — NO lo reimplementes

`product.product._get_unavailable_qty(from_date, to_date=None, ignored_soline_id=False, warehouse_id=False)`

Devuelve **el máximo de unidades no disponibles** en el intervalo. Por dentro hace un barrido
por eventos sobre las fechas de interés y se queda con el pico, que es exactamente lo que hace
falta para saber si se puede comprometer material durante todo un periodo.

Incluye cosas que es fácil no ver:

- **`ignored_soline_id`**: excluye una línea del cálculo. Es lo que permite recalcular un
  pedido que se está modificando sin que compita consigo mismo.
- **`warehouse_id`**: todo el cálculo nativo se scopea **por almacén**, no por compañía.
- **Ajustes por recogida y devolución tempranas** (`_get_rented_quantities`): si el material
  se recogió antes de tiempo o volvió antes, lo corrige desde la fecha actual. Reimplementar
  el motor sin esto da cifras distintas a las que ve el comercial en pantalla.

### 🔴 El detalle del barrido que se escapa al replicarlo

El bucle de `_get_unavailable_qty` mide el pico así:

```python
for key_date in key_dates:
    if key_date > to_date: break
    unavailable_quantity += rented_quantities[key_date]
    if key_date >= from_date:
        max_unavailable_qty = max(unavailable_quantity, max_unavailable_qty)
```

Visto suelto **parece que ignora el nivel arrastrado**: un alquiler que empieza antes de
`from_date` y acaba después de `to_date` no aporta ninguna fecha dentro del intervalo. Lo que
lo salva está en el método de al lado:

```python
key_dates = sorted(set(rented_quantities.keys()) | set(mandatory_dates))   # mandatory = [from, to]
```

`_get_rented_quantities` **inyecta `from_date` y `to_date` como fechas obligatorias**, así que
siempre hay un evento justo en `from_date` donde medir lo que venía acumulado.

**Quien copie el bucle sin copiar esa inyección obtiene ceros** en el caso más normal del
negocio: material comprometido para un fin de semana largo, consultado por un día suelto de
dentro. Pasó en `enteza_prestamo_intercompania` v19.0.1.0.0 y se corrigió en la `.1`.

### La fórmula completa de disponibilidad

Está en `RentalOrderLine._compute_qty_at_date` (`sale_stock_renting/models/sale_order_line.py`):

```python
if desde <= now:
    rentable = producto.with_context(from_date=desde, to_date=hasta,
                                     warehouse_id=wh).qty_available
else:
    rentable = producto.with_context(from_date=False, to_date=desde,
                                     warehouse_id=wh).virtual_available
    # Suma de vuelta lo que `virtual_available` ya había descontado por movimientos de
    # alquiler planificados, para no restarlo dos veces con _get_unavailable_qty.
    rentable += producto._get_virtual_unavailable_qty_in_rent(pivot_date=desde, ...)

alquilado = producto._get_unavailable_qty(desde, hasta, ignored_soline_id=..., warehouse_id=wh)
disponible = max(rentable - alquilado, 0)
```

⚠️ **Odoo no busca el mínimo de todo el periodo** para stock futuro: usa el previsto del
**primer día**, por rendimiento y con comentario explícito en su código. Si un desarrollo
necesita el mínimo real del intervalo, es una divergencia deliberada que hay que documentar,
porque dará números distintos a la ficha del producto.

### Rendimiento

`_get_unavailable_qty` hace `ensure_one()` y **una búsqueda por producto**. Para decenas de
líneas va sobrado; para barrer 1.000 productos no. Si hace falta analizar el catálogo entero,
hay que asumirlo o construir una vía agrupada aparte.

## Dónde está el material alquilado

`res.company.rental_loc_id` apunta a una ubicación **`usage='internal'`** creada bajo
`stock.stock_location_customers` (aparece como `Customers/Alquiler`).

Consecuencia: **el material que está fuera en un evento sigue contando como inventario de su
compañía**. Lo que hace a una unidad no disponible no es dónde está, sino estar comprometida
en una fecha. Por eso `qty_available` y `free_qty` **no responden** a "¿puedo alquilar esto el
día 15?".

## `rent_ok` no es lo mismo que "es material físico"

Verificado por RPC contra `enteza26` el 2026-08-04: de **1.060** productos con `rent_ok=True`,
**6 son `type == 'service'`** — FIANZA, ANTICIPO DE CLIENTES, DESCARGA COMPLICADA SEVILLA,
ALQUILER DE AMBIENTE, PRECIO POR PLAZA y hasta una furgoneta de reparto (FURGON NISSAN
NV400). Son líneas legítimas de un pedido de alquiler, pero no son material que se cargue en
un camión.

Cualquier cálculo que agregue "material de alquiler" a partir de líneas de pedido —un panel,
un informe, una exportación— tiene que filtrar por **`type == 'consu'` (Bienes) Y
`rent_ok == True`**, no solo por `rent_ok`. `type` en la 19 es
`[('consu', 'Goods'), ('service', 'Service'), ('combo', 'Combo')]`; "Goods" se traduce como
"Bienes" en la interfaz en castellano del cliente — la API RPC devuelve las etiquetas en
inglés porque el usuario de la API tiene `lang=en_US` aunque la base solo tenga `es_ES`
activo, así que no fiarse de lo que devuelve `fields_get` para saber cómo lo lee el cliente.

Implementado así en `enteza_panel_eventos/models/sale_order.py`,
`_enteza_panel_datos_articulos()` (`19.0.5.0.0`).

## Disponibilidad en el buscador de producto (Many2One de la línea)

Petición de cliente resuelta el 2026-08-04 (`enteza_prestamo_intercompania`): que el
desplegable de «Añadir un producto» diga cuántas unidades hay libres para el periodo del
pedido, sin tener que montar la línea primero.

**El texto que se ve en cada opción del desplegable es `record.display_name` tal cual**,
confirmado leyendo `web_name_search` en `addons/web/models/models.py` de la 19 (Community,
público):

```python
def web_name_search(self, name, specification, domain=None, operator='ilike', limit=100):
    id_name_pairs = self.name_search(name, domain, operator, limit)
    records = self.browse([id for id, _ in id_name_pairs])
    if len(specification) == 1 and 'display_name' in specification:
        return [{
            'id': record.id,
            'display_name': record.display_name,
            '__formatted_display_name': record.with_context(formatted_display_name=True).display_name,
        } for record in records]
```

Y el cliente web (`relational_utils.js`, `buildRecordSuggestion`) usa
`record.__formatted_display_name || record.display_name` como etiqueta. Las dos pasan por
`_compute_display_name()`, así que **sobrescribir ese método en `product.product` /
`product.template`** (llamando a `super()` primero y añadiendo el texto después) basta para
que el número aparezca — sin tocar el widget JS ni el `name_search`.

**Pero solo tiene sentido en el contexto de una línea de alquiler**: fuera de eso no hay
periodo ni almacén que consultar, y no hay que tocar el nombre en ningún otro sitio de Odoo
por accidente. Eso llega por el `context=` del campo `product_id`/`product_template_id` en la
vista de la línea, que hay que **añadir a mano**: comprobado por RPC contra `enteza26` que en
la 19 ninguna vista de `sale_renting`/`sale_stock_renting` manda ya el periodo del alquiler en
ese contexto (sí lo hacía en la 18 EE, y se perdió al pasar a la 19). Hay que heredar
`sale.view_order_form` (la vista base) con un `<xpath>` que reproduzca el `context` ENTERO del
campo — `position="attributes"` sobre `context` **reemplaza** el atributo, no lo amplía — y
seleccionar el nodo por algo estable, nunca por `@string` (ver «Un xpath no puede seleccionar
por `@string`» en `convenciones-modulo.md`).

Implementado en `enteza_prestamo_intercompania/models/product_product.py`,
`product_template.py` y `views/sale_order_product_search_views.xml` (`19.0.9.0.0`). El texto
se recortó a `Artículo - X uds.` en la `19.0.10.0.3`: la primera versión, con la unidad de
medida detrás, se salía del ancho de la columna del desplegable casi siempre.

## Albaranes de alquiler

El grupo `sale_stock_renting.group_rental_stock_picking` decide si los alquileres generan
albaranes reales o si solo se manejan cantidades a mano.

**En `enteza26` está implicado por `base.group_user`**, así que lo tienen todos los usuarios
internos: los alquileres **sí** generan albaranes, por la ruta `route_rental`
(`rental_loc → lot_stock` del almacén).

## Estado de la instancia que condiciona cualquier prueba

⚠️ Esto cambia rápido: la carga de inventario está en curso. **Comprobarlo por RPC** en vez
de fiarse de esta lista. Última verificación, **2026-08-01**:

- `stock.quant` con cantidad: **4**. Ya no es cero, pero es casi nada: la mayoría de los
  cálculos seguirán diciendo "no hay stock" y no es un fallo del código.
- **Dos almacenes**: `Sevilla` (`SEV`, compañía 1) y `Jerez` (`JER`, compañía 2). Corrige el
  estado anterior, en el que Stileum no tenía almacén. **Y habrá más**, confirmado por el
  cliente: nada debe asumir uno por compañía.
- 3 pedidos de alquiler confirmados con fecha futura, aparte de los migrados.
- 1.153 pedidos de alquiler migrados de la 15, todos con `rental_status='returned'` y fechas
  de 2026 ya pasadas. **Filtrarlos siempre** en cualquier análisis de demanda, o generan
  déficits fantasma masivos.

## Errores clásicos

1. Calcular disponibilidad con `qty_available` → ignora la dimensión temporal.
2. Reimplementar el barrido → se pierden los ajustes por recogida/devolución temprana.
3. Restar el padding otra vez sobre `reservation_begin` → se cuenta dos veces.
4. Usar `res.company.padding_time` como si fuera el padding real → es solo el defecto.
5. Escribir `start_date`/`return_date` de línea → no están almacenados.
6. Crear pedidos de prueba sin `in_rental_app=True` → no salen de alquiler.
7. Razonar por compañía cuando el nativo razona **por almacén**.
8. Dar por hecho que `rent_ok=True` significa "es material físico" → hay artículos de
   servicio (fianzas, portes) también marcados como alquilables.
