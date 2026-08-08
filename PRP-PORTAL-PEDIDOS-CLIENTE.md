# PRP — `enteza_portal_pedidos`: solicitudes de alquiler desde el portal del cliente

**Repositorio:** `enteza-odoo`, rama `19.0` · **Instancia:** `enteza26` (Odoo 19 EE, producción)
**Estado:** especificación para implementar · **Fecha:** 2026-08-08

> **Antes de escribir una línea, cargar el skill `odoo19-dev`**
> (`.claude/skills/odoo19-dev/SKILL.md`) y leer sus referencias `alquiler-en-19.md`,
> `convenciones-modulo.md` y `owl-acciones-cliente.md`. Este documento asume ese contexto y
> **no repite** los gotchas que allí están; la sección 14 solo lista los que muerden aquí.

---

## 1. Qué se pide

Que el cliente de alquiler, con sus credenciales, entre en una pantalla del frontend y monte
su solicitud de material para un evento. Los pedidos reales tienen **80–100 líneas**, así que
la pantalla tiene que parecerse a una hoja de cálculo, con celdas y filtros, no a una tienda
online con fichas de producto.

**El catálogo es el centro del módulo.** Sobre él va un sistema de filtros con **desplegables**
—categoría, marca, modelo, color… más búsqueda por texto contenido— que es lo que decide si el
cliente encuentra sus 100 artículos en cinco minutos o abandona y llama por teléfono. Las
dimensiones tienen que ser **ampliables por el cliente sin tocar código** (§4.4, §9.3).

El cliente indica en la cabecera **fecha del evento**, **día de entrega** y **día de retirada**.
Con eso el sistema evalúa disponibilidad y le muestra un **semáforo de color** por artículo —
nunca la cantidad exacta libre. Ciertos artículos van en **cajas cerradas**: la cantidad tiene
que ser múltiplo de las unidades por caja, y si el cliente teclea otra cosa se le proponen los
dos redondeos.

Al enviar, el comercial asignado recibe **aviso en el backend**. Revisa contra disponibilidad
real y **acepta** o **contrapropone** (lo que no haya para esa fecha). El cliente ve la
contrapropuesta, la acepta o la discute. Desde su usuario del portal sigue **toda la traza**:
solicitud → presupuesto → pedido → albarán → factura → cobro.

---

## 2. Las seis decisiones de arquitectura, y por qué

Estas decisiones ya están tomadas. **No re-litigarlas durante la implementación**; el porqué
está aquí para que no se deshagan por accidente.

### 2.1 NO se instala `website` ni `website_sale`. Solo `portal`.

Verificado por RPC el 2026-08-08: `portal` está **instalado**; `website`, `website_sale`,
`website_sale_renting`, `website_sale_stock` y `website_payment` están **todos sin instalar**.

El eCommerce nativo trae constructor de páginas, SEO, carrito, checkout y pago — todo lo que
sobra aquí. `portal` ya da el layout del frontend (`portal.frontend_layout`,
`portal.portal_layout`, `portal.portal_table`, `portal.pager`, `portal.portal_searchbar`), el
login, la barra de "Mi cuenta" y las páginas de presupuestos, pedidos y facturas. Es
exactamente "como el ecommerce pero más simple".

🔴 **Consecuencia directa en el código:** ninguna `@http.route` puede llevar `website=True`.
Ese parámetro lo aporta `website` y sin él la ruta no se registra. *(El módulo antiguo
`rental_portal_change_request` lo usa en todas sus rutas — es una de las razones por las que
no está instalado. Ver §3.)*

### 2.2 La solicitud **ES** un `sale.order` de alquiler en borrador. No hay modelo paralelo.

Es la decisión que más código ahorra y la que da la trazabilidad gratis.

Un modelo propio `enteza.rental.request` obligaría a reimplementar tarifas, impuestos,
disponibilidad, conversión a pedido, y a construir a mano todas las pantallas de seguimiento.
Un `sale.order` en `draft` con `is_rental_order=True` ya es, literalmente, un presupuesto de
alquiler: el comercial lo abre en la pantalla que usa todos los días, lo ajusta, lo envía con
el botón nativo *Enviar por correo* y el cliente lo ve en `/my/quotes` con el
**«Aceptar y firmar» nativo**. A partir de ahí, pedido, albarán, factura y cobro son 100 %
Odoo, sin una línea nuestra.

Lo único que añadimos al `sale.order` es **un campo de estado del canal portal** y una
**foto de lo que el cliente pidió originalmente**, para poder enseñarle el diff cuando llegue
la contrapropuesta.

### 2.3 El catálogo **es** la hoja de cálculo. No hay "buscador + carrito".

Con 80–100 líneas, cualquier flujo de «busco → añado → vuelvo → busco» es inviable: son 100
idas y vueltas. La rejilla muestra **el catálogo filtrado con una columna de cantidad**.
Escribir una cantidad en una fila *es* añadir la línea. Un conmutador *«Solo con cantidad»*
convierte la misma rejilla en el resumen del pedido para repasarlo antes de enviar.

🔴 **Filtrar no vacía el pedido.** Las cantidades viven en el `sale.order`, no en la rejilla:
los filtros solo **ocultan filas**. Un artículo con cantidad sigue en la solicitud aunque el
filtro activo no lo muestre. El contador de la cabecera («102 líneas») cuenta **todas**, no las
visibles, y hay un aviso cuando el filtro esconde líneas con cantidad.

Esto también elimina la paginación: son **1.025 artículos alquilables de tipo Bien**
(verificado por RPC), que se sirven de una vez en un JSON pequeño y se filtran **en el
navegador**, de forma instantánea — incluidos todos los desplegables de §9.3, que por eso
pueden recalcular sus contadores en cada pulsación sin ir al servidor. Lo caro (la
disponibilidad) va aparte y bajo demanda (§6).

### 2.4 Las dimensiones de filtrado son **etiquetas nativas agrupadas por «faceta»**.

Esto es el corazón de la pantalla, así que la decisión importa. Estado real verificado por RPC
el 2026-08-08:

| Candidato | Situación real | Veredicto |
|---|---|---|
| `product.category` | 24 categorías, **planas**, con datos reales (SILLAS, MESAS, VAJILLAS, CRISTALERIAS…) | ✅ **Se usa** como desplegable propio |
| Campo `marca` / `brand` / `model` en `product.template` | **No existe ninguno** | ❌ No hay dato que filtrar |
| `product.attribute` | Existen 8 (`brand`, `manufacturer`, `color`, `material`, `size`…) pero con **0 valores**: nadie los usa | ❌ **Trampa**, ver abajo |
| `product.tag` (`product_tag_ids`) | Modelo nativo, m2m ya presente en `product.template`, con `visible_to_customers`, `image`, `color` y `sequence`. **0 registros** | ✅ **Se usa como base** |

🔴 **Por qué NO `product.attribute`, aunque parezca lo obvio:** los 8 atributos tienen
`create_variant = 'always'`. Asignar «Marca = X» a una plantilla **crearía variantes de
producto**, multiplicando el catálogo y rompiendo el alquiler, el inventario que se está
cargando y el `id_map` de la migración. Se podrían pasar a `no_variant`, pero entonces
aparecen en el configurador de producto de la línea de pedido y estorban al comercial. No
compensa: son atributos de **configuración de producto**, no de **búsqueda**.

**La solución:** `product.tag` es nativo, está pensado justo para esto y ya trae
`visible_to_customers` — pero es **plano**, y con una única bolsa de etiquetas no se pueden
montar desplegables separados de «Marca» y «Modelo». Se le añade **el eslabón que le falta**:

- un modelo nuevo minúsculo, **`enteza.product.facet`** («dimensión de búsqueda»: Marca,
  Modelo, Color, Estilo, Material… las que el cliente quiera),
- y un campo **`enteza_facet_id`** en `product.tag` que dice a qué dimensión pertenece cada
  etiqueta.

Cada faceta se convierte automáticamente en **un desplegable** del portal. El cliente crea
«Marca» y sus valores desde un menú de Odoo, sin desarrollo. Coste total: **un modelo y un
campo**. Y se reutiliza el m2m `product_tag_ids` que ya existe en la ficha del producto, con su
widget nativo de etiquetas.

### 2.5 La disponibilidad la calcula **el motor nativo**. No se reimplementa.

`product.product._get_unavailable_qty(...)` de `sale_stock_renting`, con la fórmula completa
de `_compute_qty_at_date`. Está detallado en `references/alquiler-en-19.md` del skill, con el
gotcha del barrido (las fechas obligatorias inyectadas) que ya costó una versión en
`enteza_prestamo_intercompania`.

🔴 **Regla de convivencia del repositorio:** un solo motor de disponibilidad instalado a la vez.
`enteza_prestamo_intercompania` (instalado) ya trae el suyo. **Este módulo no aporta ninguno**:
solo consume el nativo. No instalar `rental_multi_warehouse` ni `sale_stock_renting_extension`
a la vez que esto.

### 2.6 Las cajas se modelan con el **packaging nativo de Odoo 19**, que es una UdM.

En Odoo 19 **`product.packaging` ya no existe** — verificado por RPC: no hay ningún modelo
cuyo nombre contenga `packaging`. El packaging se fusionó con las unidades de medida. El
vehículo nativo es:

- `product.template.uom_ids` — m2m a `uom.uom`, etiqueta **"Packagings"**, `store=True`.
  *(En `product.product` el mismo campo existe pero es `store=False`.)*
- Una "caja de 25" es un registro de `uom.uom` con `relative_uom_id` = *Units* y
  `relative_factor` = 25. **`relative_factor`, no `factor`** (§14).

Como las UdM en la 19 ya no tienen categorías, una misma «CAJA 25 UDS» sirve para todos los
artículos que van de 25 en 25: se crean **una docena de UdM**, no una por producto.

⚠️ **Hoy no hay ni un solo dato cargado**: `product.template` con `uom_ids` informado = **0**,
y `product.uom` (el modelo nuevo de código de barras por packaging) = **0 registros**. Cargar
esto es un **prerequisito de datos** (§12), no parte del código. Mientras un artículo no tenga
packaging, **no se le aplica ninguna restricción de múltiplo** y se pide por unidades sueltas.

---

## 3. Lo que ya existe en el repositorio y hay que tener en cuenta

| Módulo | Estado | Qué hacer |
|---|---|---|
| `rental_custom` `19.0.1.5.0` | **instalado** | **Dependencia obligatoria.** Aporta `event_date` en `sale.order`/`sale.order.line`, `rental_billable_days`, `place_number`, y un `onchange` de `event_date` que fija `rental_start_date = evento − 1 día` y `rental_return_date = evento + 1 día`. También valida en `action_confirm` que un alquiler **no se confirme sin `event_date`** |
| `sale_renting` + `sale_stock_renting` | instalados | Alquiler nativo y motor de disponibilidad. `rental_loc_id` configurado en las dos compañías, `padding_time = 0` |
| `enteza_prestamo_intercompania` `19.0.10.0.3` | instalado | Trae **su propio** motor de disponibilidad y parchea el widget `qty_at_date`. No colisiona con esto (nosotros no parcheamos widgets de backend), pero **no duplicar cálculos** |
| `rental_portal_change_request` | **sin instalar** | 🔴 **NO instalarlo y NO partir de él.** Resuelve otro problema (cambios sobre pedidos ya confirmados), usa `website=True` en todas sus rutas (§2.1), depende de `pg_trgm` y define campos `x_*` sobre `sale.order`. Su `docs/Analisis-Enteza-Web-Clientes.md` es un prompt antiguo con citas inventadas: **no es fuente**. Se puede **canibalizar la idea** del diff y del bloqueo optimista, nada más |

---

## 4. Modelo de datos

Un solo modelo nuevo (`enteza.product.facet`, §4.4). Todo lo demás son herencias.

### 4.1 `sale.order` (`models/sale_order.py`)

```python
class SaleOrder(models.Model):
    _inherit = 'sale.order'

    enteza_portal_ref = fields.Char(
        string="Referencia de solicitud", copy=False, index=True, readonly=True,
        help="Referencia visible para el cliente. Se asigna al enviar la solicitud desde "
             "el portal. No sustituye al número de presupuesto.")

    enteza_portal_state = fields.Selection(
        selection=[
            ('none',       "No es del portal"),
            ('composing',  "El cliente la está montando"),
            ('submitted',  "Enviada por el cliente"),
            ('reviewing',  "En revisión del comercial"),
            ('counter',    "Contrapropuesta enviada"),
            ('closed',     "Cerrada"),
        ],
        string="Estado en el portal", default='none', copy=False, index=True, tracking=True)

    enteza_portal_snapshot = fields.Json(
        string="Solicitud original del cliente", copy=False, readonly=True,
        help="Foto de las líneas tal como las envió el cliente. Se usa para mostrarle el "
             "diff cuando el comercial contrapropone.")

    enteza_portal_customer_note = fields.Text(
        string="Comentario del cliente", copy=False, tracking=True)

    enteza_portal_submitted_on = fields.Datetime(
        string="Enviada el", copy=False, readonly=True)

    _enteza_portal_ref_uniq = models.UniqueIndex('(enteza_portal_ref) WHERE enteza_portal_ref IS NOT NULL')
```

**Notas de implementación:**

- `fields.Json` existe en la 19 y es lo correcto para el snapshot. Alternativa si diese
  problemas de serialización: `fields.Text` con `json.dumps`.
- 🔴 `models.UniqueIndex` / `models.Index`, **nunca `_sql_constraints`** (§14).
- `enteza_portal_ref` se toma de una `ir.sequence` propia (`SOL/2026/00001`) y **no toca
  `name`**: el número de presupuesto sigue siendo el nativo, y `rental_custom` ya tiene un
  asistente para renombrarlo si el comercial quiere.

**Método atómico de envío** (el único punto crítico de concurrencia):

```python
def action_enteza_portal_submit(self, customer_note=None):
    """Cierra la composición y avisa al comercial. Idempotente."""
```

Debe, en una sola transacción:
1. `ensure_one()` y comprobar `enteza_portal_state == 'composing'`; si ya está en
   `submitted` o posterior, **devolver sin error** (idempotencia: el cliente da doble clic).
2. Validar cabecera: `event_date`, `rental_start_date`, `rental_return_date`, `warehouse_id`.
3. Validar que hay al menos una línea con cantidad > 0.
4. Validar **múltiplos de caja** de todas las líneas (§7). Si alguna falla → `UserError`
   con la lista de artículos. **No redondear por su cuenta.**
5. Recalcular disponibilidad de todas las líneas y guardar el resultado (§6).
6. Escribir el snapshot, `enteza_portal_ref` (de la secuencia),
   `enteza_portal_submitted_on`, `enteza_portal_state = 'submitted'`.
7. `message_post` en el chatter con el resumen (nº de líneas, importe, fechas, semáforos en
   rojo) y `activity_schedule('mail.mail_activity_data_todo', user_id=self.user_id.id)`.
8. Opcional según configuración: enviar la plantilla de correo al comercial.

### 4.2 `sale.order.line` (`models/sale_order_line.py`)

```python
enteza_portal_availability = fields.Selection(
    [('green', "Disponible"), ('amber', "Ajustado"), ('red', "Sin disponibilidad"),
     ('grey', "Sin datos")],
    string="Semáforo (portal)", copy=False, readonly=True)

enteza_portal_availability_date = fields.Datetime(
    string="Semáforo calculado el", copy=False, readonly=True)
```

Se guardan **solo** para que el comercial vea en el backend lo que vio el cliente al enviar.
**No son la fuente de verdad**: el comercial trabaja con el widget nativo `qty_at_date`.

### 4.3 `product.template` (`models/product_template.py`)

```python
enteza_box_uom_id = fields.Many2one(
    'uom.uom', string="Caja", compute='_compute_enteza_box', store=True,
    compute_sudo=True, help="Packaging más pequeño declarado en «Packagings» (uom_ids).")

enteza_units_per_box = fields.Float(
    string="Uds. por caja", compute='_compute_enteza_box', store=True, compute_sudo=True,
    digits='Product Unit of Measure',
    help="0 = el artículo se pide por unidades sueltas.")

enteza_portal_ok = fields.Boolean(
    string="Visible en el portal de clientes", default=True, index=True,
    help="Desmarcar para que el artículo no aparezca en la rejilla del cliente.")
```

`_compute_enteza_box` depende de `uom_ids`, `uom_ids.relative_factor`,
`uom_ids.relative_uom_id` y `uom_id`. Lógica: de entre los `uom_ids`, quedarse con el de
**menor `relative_factor` estrictamente mayor que 1** resoluble a la UdM del producto. Si no
hay ninguno → `enteza_units_per_box = 0`.

⚠️ **Los productos son compartidos** (`company_id = False` en 1.908 plantillas). **No añadir
`company_id`** a estos campos ni reglas por compañía sobre productos: rompería la premisa de
todo el desarrollo de alquiler del cliente.

### 4.4 Facetas de búsqueda — el único modelo nuevo

**`models/product_facet.py`:**

```python
class ProductFacet(models.Model):
    _name = 'enteza.product.facet'
    _description = "Dimensión de búsqueda del catálogo del portal"
    _order = 'sequence, name'

    name = fields.Char(string="Nombre", required=True, translate=True)
    sequence = fields.Integer(string="Secuencia", default=10)
    active = fields.Boolean(string="Activa", default=True)
    tag_ids = fields.One2many('product.tag', 'enteza_facet_id', string="Valores")
    tag_count = fields.Integer(compute='_compute_tag_count')
    portal_visible = fields.Boolean(
        string="Mostrar en el portal", default=True,
        help="Desmarcar para usar la dimensión solo internamente.")
    multi = fields.Boolean(
        string="Permite varios valores", default=True,
        help="Si está marcado, el cliente puede elegir varias opciones a la vez "
             "(se combinan con O).")

    _name_uniq = models.Constraint('UNIQUE(name)', "Ya existe una dimensión con ese nombre.")
```

**`models/product_tag.py`:**

```python
class ProductTag(models.Model):
    _inherit = 'product.tag'

    enteza_facet_id = fields.Many2one(
        'enteza.product.facet', string="Dimensión", index=True, ondelete='set null',
        help="Desplegable del portal en el que aparece esta etiqueta. "
             "Sin dimensión, la etiqueta no se usa como filtro.")
```

**Cómo se aplica al producto:** con el m2m nativo **`product.template.product_tag_ids`**, que
ya existe. **No se crea ninguna relación nueva** en el producto, y el comercial etiqueta desde
la ficha con el widget de etiquetas de siempre.

**Qué llega al portal:** solo las etiquetas con `enteza_facet_id` informado, cuya faceta tenga
`portal_visible = True` y que tengan **`visible_to_customers = True`** — campo **nativo** de
`product.tag`, pensado exactamente para esto. Así el cliente puede usar etiquetas internas
(«revisar», «lote 2019») sin que se le cuelen al cliente final.

**Menú:** Inventario → Configuración → **Dimensiones de búsqueda**, con la lista de facetas y
sus valores en línea. Las etiquetas se siguen gestionando también desde el menú nativo de
Etiquetas de producto, que hereda una columna «Dimensión».

⚠️ **`ir.model.access.csv` es obligatorio** para `enteza.product.facet`: lectura para
`base.group_user`, escritura para `stock.group_stock_manager` (o `sales_team.group_sale_manager`).
El grupo Portal **no** necesita acceso: las facetas se sirven desde el controlador con
`sudo()`, como el resto del catálogo (§8.2).

### 4.5 `res.partner` (`models/res_partner.py`)

```python
enteza_portal_pedidos_ok = fields.Boolean(
    string="Puede solicitar pedidos por el portal", default=False, tracking=True)

enteza_portal_warehouse_id = fields.Many2one(
    'stock.warehouse', string="Almacén habitual",
    help="Almacén desde el que se sirve por defecto a este cliente.")
```

El primero es **la puerta**: sin él, un usuario del portal ve sus documentos pero no la
pantalla de solicitud. Se activa cliente a cliente.

### 4.6 `res.company` + `res.config.settings`

```python
# res.company
enteza_portal_semaforo = fields.Boolean(
    string="Mostrar semáforo de disponibilidad en el portal", default=False)
enteza_portal_dias_minimos = fields.Integer(
    string="Antelación mínima (días)", default=2)
enteza_portal_aviso_email = fields.Boolean(
    string="Avisar al comercial también por correo", default=True)
```

🔴 `enteza_portal_semaforo` **arranca en `False` a propósito**. Con el inventario a medio
cargar el semáforo diría "rojo" en casi todo (§12) y el cliente lo leería como "no tenéis
nada". Se enciende cuando el almacén esté cargado.

En `res.config.settings`, los tres como `related='company_id.…', readonly=False`, bajo
Ajustes → Ventas → Alquiler.
🔴 El `<xpath>` de la vista de ajustes **no puede seleccionar por `@string`** (§14).

---

## 5. Flujo de estados y quién puede qué

```
                    ┌──────────────────────────────────────────────┐
  CLIENTE (portal)  │  COMERCIAL (backend)                         │
                    └──────────────────────────────────────────────┘

  [Nueva solicitud]
        │  crea sale.order draft, is_rental_order=True
        ▼
   composing ──────── el cliente edita la rejilla ────────┐
        │                                                 │ (puede cancelar → cancel)
        │  action_enteza_portal_submit()                  │
        ▼                                                 ▼
   submitted ─── aviso: chatter + actividad + correo ──► el comercial la ve
        │                                                        │
        │                                              lee, ajusta cantidades
        │                                                        ▼
        │                                                   reviewing
        │                                       ┌────────────────┴────────────────┐
        │                                  ACEPTA                            CONTRAPROPONE
        │                                       │                                 │
        │                          «Confirmar» nativo                «Enviar por correo» nativo
        │                                       │                                 │
        ▼                                       ▼                                 ▼
  ve el pedido en /my/orders        sale.order.state = 'sale'        state='sent', portal='counter'
  albarán, factura, cobro                                                         │
        ▲                                                    el cliente ve el DIFF en el portal
        │                                                    y usa «Aceptar y firmar» NATIVO
        └────────────────────────────────────────────────────────────────┘
```

**Reglas duras:**

| Estado portal | El cliente puede | El comercial puede |
|---|---|---|
| `composing` | editar todo, enviar, cancelar | verla filtrada aparte; **no tocarla** (convenio, no código) |
| `submitted` | solo leer + comentar | todo |
| `reviewing` | solo leer + comentar | todo |
| `counter` | leer el diff, **Aceptar y firmar** (nativo), rechazar/comentar (nativo) | todo |
| `closed` | leer | — |

- **Una sola solicitud en `composing` por cliente** a la vez. Si ya existe, la ruta
  `/my/solicitud/nueva` **redirige a la existente** en lugar de crear otra.
- El cliente **nunca** escribe sobre `sale.order` directamente: todo pasa por los
  controladores de §8, que validan propiedad y usan `sudo()` acotado.
- `sale.order.state` recorre solo valores nativos verificados en la instancia:
  `draft` · `sent` · `sale` · `cancel`.

---

## 6. Disponibilidad: el semáforo

### 6.1 El cálculo

**Reutilizar el nativo tal cual.** La fórmula, copiada de
`RentalOrderLine._compute_qty_at_date` de `sale_stock_renting`:

```python
def _enteza_libre(self, producto, desde, hasta, almacen, ignorar_soline=False):
    """Unidades realmente alquilables del producto en [desde, hasta] en ese almacén."""
    ahora = fields.Datetime.now()
    if desde <= ahora:
        rentable = producto.with_context(
            from_date=desde, to_date=hasta, warehouse_id=almacen.id).qty_available
    else:
        rentable = producto.with_context(
            from_date=False, to_date=desde, warehouse_id=almacen.id).virtual_available
        # Devuelve lo que virtual_available ya había descontado por alquileres planificados,
        # para no restarlo dos veces con _get_unavailable_qty.
        rentable += producto._get_virtual_unavailable_qty_in_rent(
            pivot_date=desde, warehouse_id=almacen.id)

    alquilado = producto._get_unavailable_qty(
        desde, hasta, ignored_soline_id=ignorar_soline, warehouse_id=almacen.id)
    return max(rentable - alquilado, 0)
```

🔴 **Tres avisos:**

1. `_get_virtual_unavailable_qty_in_rent` es un **método privado de Enterprise**. Su firma
   está leída del repositorio del cliente `enteza-carrysoft/odoo_enterprise_18` (rama `18.0`),
   **no de la 19**. Verificarla en `enteza26` antes de darla por buena; si no coincide,
   ajustar y **decirlo al entregar**.
2. `_get_unavailable_qty` hace `ensure_one()` y **una búsqueda por producto**. Para 1.025
   artículos son 1.025 consultas: **inaceptable en una petición web**. De ahí §6.2.
3. **No reimplementar el barrido.** El gotcha de las fechas obligatorias inyectadas está
   documentado en el skill y ya costó una versión de `enteza_prestamo_intercompania`.

### 6.2 Cuándo se calcula (esto es lo que hace que funcione)

**Nunca para el catálogo entero.** El semáforo se pide en un endpoint aparte y por lotes:

- **Al abrir** o al **cambiar las fechas**: para los productos que ya tienen cantidad.
- **Al hacer scroll o filtrar**: para las **filas visibles** que aún no tengan semáforo,
  en lotes de **50 como máximo**, con *debounce* de 400 ms.
- **Al teclear una cantidad** en una fila sin semáforo: para esa fila sola.

El cliente OWL cachea por clave `producto|desde|hasta|almacén` y **vacía la caché entera
cuando cambian las fechas o el almacén**. Se pide con `ignorar_soline` = la línea propia, para
que la solicitud en curso no compita consigo misma.

Si `res.company.enteza_portal_semaforo` está desactivado, el endpoint devuelve `grey` para
todo sin consultar nada, y la columna se oculta.

### 6.3 Los colores

Con `libre` = resultado de §6.1 y `pedido` = cantidad tecleada:

| Color | Condición | Texto en pantalla |
|---|---|---|
| ⬜ `grey` | semáforo desactivado, o el artículo no gestiona existencias | *(sin texto)* |
| 🟩 `green` | `pedido > 0` y `libre >= pedido` · o `pedido == 0` y `libre > 0` | «Disponible» |
| 🟨 `amber` | `pedido > 0` y `0 < libre < pedido` | «Puede que no haya todo» |
| 🟥 `red` | `libre <= 0` | «Sin disponibilidad» |

🔴 **Nunca se envía al navegador la cantidad libre.** El endpoint devuelve **solo el color**.
Si el número viaja en el JSON, el cliente lo ve en las herramientas de desarrollo — y el
cliente ha pedido explícitamente no mostrarlo.

Comparaciones con `float_compare` y
`self.env['decimal.precision'].precision_get('Product Unit of Measure')`. Nunca `> 0` a pelo.

### 6.4 Un ámbar o un rojo **no bloquean el envío**

Es el punto del módulo: el cliente pide, el comercial ajusta. El semáforo es orientativo —
así se le dice en pantalla — y las filas en rojo se resaltan en el aviso al comercial.

---

## 7. Cajas y múltiplos

**Origen del dato:** `product.template.enteza_units_per_box` (§4.3), derivado del packaging
nativo. Si vale `0`, el artículo va por unidades y **nada de esta sección aplica**.

**Regla:** `cantidad % uds_por_caja == 0`. Nunca media caja.

**En el navegador**, al salir de la celda de cantidad:

```
uds_caja = 25,  tecleado = 90
abajo  = floor(90/25)*25 = 75      arriba = ceil(90/25)*25 = 100
```

Se muestra un *chip* inline bajo la celda, en rojo suave, con dos botones:
`↓ 75 (3 cajas)` y `↑ 100 (4 cajas)`. La celda queda marcada en rojo hasta que se resuelve.
Si el cliente teclea menos de una caja (p. ej. 10 de 25), la opción "abajo" es **0 = quitar
la línea** y se rotula así.

La columna **Cajas** muestra `cantidad / uds_caja` en las filas que tengan packaging.

**En el servidor**, `action_enteza_portal_submit` **vuelve a validar**. Si queda alguna línea
no múltiplo → `UserError` listando artículo, cantidad y los dos redondeos. **El servidor no
redondea solo**: cambiarle la cantidad al cliente sin que lo pida es peor que rechazar.

---

## 8. Controladores

Dos ficheros. **Ninguna ruta lleva `website=True`** (§2.1).

### 8.1 Páginas HTML — `controllers/portal.py`

Heredan de `odoo.addons.portal.controllers.portal.CustomerPortal`.

| Ruta | Qué hace |
|---|---|
| `GET /my/solicitudes` | Lista de solicitudes del cliente con su estado. `portal.portal_table` + `portal.pager` |
| `GET /my/solicitud/nueva` | Crea (o recupera) la solicitud en `composing` y **redirige** a la siguiente |
| `GET /my/solicitud/<int:order_id>` | La rejilla. Monta el componente OWL |
| `GET /my/solicitud/<int:order_id>/resumen` | Vista de solo lectura + **diff** contra el snapshot cuando el estado es `counter` |

Todas con `type='http', auth='user'`.

También se sobrescribe `_prepare_home_portal_values` para añadir el contador
`solicitud_count` a la portada de `/my`, y se hereda `portal.portal_my_home` para pintar la
tarjeta — **solo si `partner.enteza_portal_pedidos_ok`**.

**Comprobación de propiedad, en todas** (helper compartido):

```python
def _enteza_get_solicitud(self, order_id):
    order = request.env['sale.order'].browse(order_id).exists()
    commercial = request.env.user.partner_id.commercial_partner_id
    if not order or order.partner_id.commercial_partner_id != commercial:
        raise NotFound()
    return order
```

Se apoya en la regla nativa ya presente en la instancia (`ir.rule` 171, *Portal Personal
Quotations/Sales Orders*, `[('partner_id','child_of',[user.commercial_partner_id.id])]`),
pero **se comprueba igualmente en el controlador**. Cinturón y tirantes.

### 8.2 API JSON — `controllers/api.py`

🔴 **`type='jsonrpc'`**, que en Odoo 19 es el nuevo nombre de lo que hasta la 18 era
`type='json'`. Con `type='json'` la ruta no se registra.
([Web Controllers — Odoo 19](https://www.odoo.com/documentation/19.0/developer/reference/backend/http.html))

| Ruta | Params | Devuelve |
|---|---|---|
| `/enteza_portal/solicitud/catalogo` | `order_id` | catálogo completo (§8.3) |
| `/enteza_portal/solicitud/cabecera` | `order_id`, `event_date`, `pickup_date`, `return_date`, `warehouse_id` | cabecera normalizada + `dirty: true` si hay que refrescar semáforos |
| `/enteza_portal/solicitud/lineas` | `order_id`, `changes: [{product_id, qty}]` | líneas afectadas, totales, avisos de múltiplo |
| `/enteza_portal/solicitud/disponibilidad` | `order_id`, `product_ids` (máx. 50) | `{product_id: 'green'|'amber'|'red'|'grey'}` |
| `/enteza_portal/solicitud/enviar` | `order_id`, `customer_note` | `{ok, ref, redirect}` o `{error, lines:[…]}` |
| `/enteza_portal/solicitud/cancelar` | `order_id` | `{ok}` |

**Todas**: `type='jsonrpc', auth='user'`, y **lo primero que hacen** es
`self._enteza_check(order_id)` — propiedad + `enteza_portal_pedidos_ok` + estado
`composing` (salvo `catalogo`, que también sirve en solo lectura).

**`sudo()` acotado y comentado**, nunca al método entero. Se necesita porque:
- 🔴 **El grupo Portal (id 10) no tiene ningún `ir.model.access` sobre `product.product`,
  `product.template`, `product.category` ni `uom.uom`** — verificado por RPC. Sin
  `website_sale` instalado, un usuario del portal **no puede leer el catálogo**. Todas las
  lecturas de producto van con `sudo()` tras validar la propiedad del pedido.
- La escritura de líneas sobre un `sale.order` en borrador tampoco la permite el portal.

**Escritura de líneas** (`/lineas`), en una sola transacción:
- `qty > 0` sobre producto sin línea → crear línea.
- `qty > 0` sobre producto con línea → `write` de `product_uom_qty`.
- `qty == 0` → `unlink` de la línea.
- Crear el pedido y las líneas **siempre** con
  `.with_context(in_rental_app=True)`, o `is_rental` sale `False` y no es un alquiler.
- `product_uom_id` se deja **en la UdM del producto** (Units). El packaging **no** se pone en
  la línea: solo restringe la cantidad (§7). Poner la caja como UdM de la línea alteraría el
  cálculo de tarifas de alquiler y el importe que ve el comercial.

**Bloqueo optimista:** cada respuesta devuelve `write_date` del pedido y el cliente lo manda
en la siguiente petición. Si no coincide → `{"error": "stale"}` y el navegador recarga. Es
suficiente: solo edita el cliente, y las escrituras son incrementales y pequeñas.

### 8.3 Payload del catálogo

Una sola llamada al abrir la pantalla. Filtro:
`[('rent_ok','=',True), ('type','=','consu'), ('enteza_portal_ok','=',True), ('active','=',True)]`
— 🔴 **`type='consu'` además de `rent_ok`**: hay 6 artículos de servicio marcados como
alquilables (fianza, portes, precio por plaza…) que no son material de camión.

```json
{
  "order": {"id": 1234, "ref": null, "state": "composing", "write_date": "…",
            "event_date": "2026-09-12", "pickup_date": "2026-09-11",
            "return_date": "2026-09-13", "warehouse_id": 1,
            "warehouses": [{"id": 1, "name": "Sevilla"}],
            "semaforo_activo": false, "dias_minimos": 2,
            "currency": {"symbol": "€", "position": "after", "decimals": 2}},
  "categories": [{"id": 35, "name": "SILLAS"}, "…"],
  "facets": [
    {"id": 1, "name": "Marca", "multi": true,
     "tags": [{"id": 12, "name": "Vimaple"}, {"id": 13, "name": "Colonial"}]},
    {"id": 2, "name": "Modelo", "multi": true,
     "tags": [{"id": 40, "name": "Bambú"}, {"id": 41, "name": "Crossback"}]},
    {"id": 3, "name": "Color",  "multi": true,
     "tags": [{"id": 60, "name": "Blanco"}, {"id": 61, "name": "Natural"}]}
  ],
  "products": [
    {"id": 3568, "code": "SIL-BAM-01", "name": "Silla bambú", "category_id": 35,
     "tag_ids": [12, 40, 61], "uom": "Units", "box": 25, "price": 2.5, "habitual": true}
  ],
  "lines": [{"line_id": 991, "product_id": 3568, "qty": 100, "subtotal": 250.0}],
  "totals": {"untaxed": 250.0, "tax": 52.5, "total": 302.5}
}
```

`habitual: true` = el cliente ya alquiló ese artículo alguna vez (§9.4).

**Tamaño:** ~1.025 productos ≈ **150 KB**, y `tag_ids` añade unos pocos enteros por fila. Se
manda entero y se filtra en el navegador. 🔴 **Las etiquetas viajan como `tag_ids` (enteros),
no repitiendo el nombre en cada producto**: con 1.025 filas × 4 etiquetas, repetir cadenas
triplicaría el payload sin aportar nada. Los nombres van una sola vez, en `facets`.

**Qué facetas se sirven:** las de `portal_visible = True` cuyas etiquetas tengan
`visible_to_customers = True` **y** estén usadas por al menos un producto del catálogo servido.
Una faceta que se quede sin valores **no se manda**: un desplegable vacío es ruido.

**Importes formateados en Python** con `formatLang(self.env, importe, currency_obj=…)` — menos
JS que no se puede probar. **Fechas y horas** convertidas con
`fields.Datetime.context_timestamp(...)`: los `Datetime` de Odoo están en UTC y España va +2
en verano (esto ya mordió una vez en este proyecto, con 16 pedidos que se veían un día tarde).

---

## 9. La interfaz del cliente

### 9.1 Cómo se monta

**Componente público OWL** en el bundle del frontend — el patrón documentado para portal en la
19 ([Use Owl components on the portal and website](https://www.odoo.com/documentation/19.0/developer/howtos/frontend_owl_components.html)):

```js
// static/src/grid/request_grid.js
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";

export class RequestGrid extends Component {
    static template = "enteza_portal_pedidos.RequestGrid";
    static props = { orderId: { type: Number } };
    // …
}
registry.category("public_components").add("enteza_portal_pedidos.RequestGrid", RequestGrid);
```

```xml
<!-- views/portal_templates.xml -->
<owl-component name="enteza_portal_pedidos.RequestGrid"
               props="{'orderId': order.id}"/>
```

```python
'assets': {'web.assets_frontend': ['enteza_portal_pedidos/static/src/**/*']},
```

🔴 `web.assets_frontend`, **no** `web.assets_backend`: esto vive en el portal.
🔴 El `t-name` de la plantilla tiene que coincidir **exactamente** con `static template`.
🔴 Un error de JS deja **la pantalla en blanco, sin nada en el log del servidor**. Solo se
diagnostica en la consola del navegador (F12). Contar con una ronda de ajuste al entregar.
🔴 Tras desplegar assets, **`Ctrl+F5`** o se sigue viendo el bundle anterior.

### 9.2 Distribución de la pantalla

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│  SOL/2026/00042 · Borrador               [Cancelar]  [Guardar]  [Enviar solicitud] │ ← fija
├───────────────────────────────────────────────────────────────────────────────────┤
│  Evento [12/09/2026]   Entrega [11/09]   Retirada [13/09]   Almacén [Sevilla ▾]    │ ← fija
│                                            102 líneas · 4.820,00 € (sin IVA)      │
├───────────────────────────────────────────────────────────────────────────────────┤
│ 🔍 [ silla bambú blanca            ]  [Categoría ▾] [Marca ▾] [Modelo ▾] [Color ▾] │ ← BARRA
│                                       [ Más filtros ▾ ]                           │   DE
│ Filtros: (SILLAS ✕) (Marca: Vimaple ✕) (Color: Blanco, Natural ✕)   Limpiar todo   │   FILTROS
│          ☑ Mis habituales   ☐ Solo con cantidad   ☐ Ocultar sin disponibilidad     │   fija
├───────────────────────────────────────────────────────────────────────────────────┤
│ Ref.      Artículo                    Disp.   Uds/caja   Cantidad   Cajas   Import.│ ← cabecera
│ ───────────────────────────────────────────────────────────────────────────────── │   de tabla
│ SIL-BAM   Silla bambú blanca           🟩       25        [ 100]      4    250,00 │   fija
│ MES-RED   Mesa redonda 180             🟨        —        [  12]      —    180,00 │
│ VAJ-P27   Plato llano 27               🟩       50        [  90]⚠     —      —    │
│           ↳ La caja son 50 uds:   [ ↓ 50 (1 caja) ]  [ ↑ 100 (2 cajas) ]          │
│ CRI-COP   Copa de vino                 🟥       60        [    ]      —      —    │
│ …                                                                                 │
├───────────────────────────────────────────────────────────────────────────────────┤
│ 38 de 1.025 artículos  ·  ⚠ 3 líneas con cantidad están ocultas por el filtro      │ ← pie fijo
└───────────────────────────────────────────────────────────────────────────────────┘
```

- **Tres bandas fijas** (`position: sticky`): barra de acciones, cabecera del pedido + filtros,
  y cabecera de la tabla. Más un **pie fijo** con el recuento. Así el scroll nunca hace perder
  ni el contexto ni los botones — que es el problema real de 100 líneas.
- **Los filtros arriba, en horizontal, no en una columna lateral.** Con desplegables ocupan una
  banda estrecha y dejan **todo el ancho** para la tabla, que es donde el cliente trabaja. Una
  barra lateral se come 250 px de forma permanente para algo que se toca de vez en cuando.
- **Densidad alta**: fila de ~32 px, tipografía de tabla, sin imágenes en la rejilla (solo 529
  de los alquilables tienen imagen; miniatura en un *popover* al pasar por encima del nombre,
  cargada bajo demanda).
- El contador de la cabecera (líneas + importe) cuenta **todo el pedido**, no lo visible, y se
  confirma con lo que devuelve el servidor en cada `/lineas`.

### 9.3 El sistema de filtros

Es el requisito central de la pantalla. Todo se resuelve **en el navegador** sobre el catálogo
ya cargado (§2.3), así que responde en cada pulsación sin ir al servidor.

**Los controles, de izquierda a derecha:**

| Control | Origen del dato | Comportamiento |
|---|---|---|
| **Búsqueda por texto** | `name` + `default_code` del producto | Sin distinguir mayúsculas ni acentos. **Todas las palabras** tecleadas deben aparecer, en cualquier orden y en cualquiera de los dos campos: «silla bambu blanca» encuentra «Silla bambú blanca» y «Silla blanca de bambú». *Debounce* de 150 ms |
| **Categoría** | `product.category` (24, planas) | Desplegable **multiselección** con contador por opción |
| **Marca, Modelo, Color, …** | Una faceta = un desplegable (§4.4) | **Se generan solos** a partir de lo que devuelve el servidor. Si el cliente crea la faceta «Estilo», aparece su desplegable sin tocar código |
| **Más filtros ▾** | — | Recoge las facetas que no caben en la banda, para que nunca se parta en dos filas |
| **Mis habituales** | historial del cliente (§9.4) | Conmutador |
| **Solo con cantidad** | estado local | Conmutador. Convierte la rejilla en el resumen del pedido |
| **Ocultar sin disponibilidad** | semáforo (§6) | Conmutador. **Solo visible si el semáforo está activo** |

**Reglas de combinación** — las estándar, que es lo que el cliente espera sin que se lo
expliquen:

- **Dentro de un desplegable**, varios valores se combinan con **O**: Color = Blanco *o*
  Natural.
- **Entre desplegables distintos**, con **Y**: SILLAS *y* marca Vimaple *y* (blanco *o* natural).
- Una faceta con `multi = False` se comporta como selección única.

**Facetado dinámico** — esto es lo que separa un filtro cómodo de uno que frustra:

- Cada opción lleva **el número de artículos que quedarían** si se marcase, calculado sobre los
  filtros ya activos **de las demás dimensiones** (la técnica habitual: para contar las
  opciones de «Color» se aplica todo menos «Color»).
- Las opciones que darían **0 resultados** salen **atenuadas y al final** de la lista, no
  desaparecen: que una marca esté agotada para esa categoría es información, y hacerla
  desaparecer confunde.
- Un desplegable con **más de 12 opciones** lleva su propio **buscador interno**.

**Filtros activos como *chips***, bajo la barra, cada uno con su ✕, más **«Limpiar todo»**. Sin
esto, con cuatro desplegables el cliente pierde de vista por qué solo ve 38 artículos — que es
la queja número uno de cualquier catálogo filtrado.

🔴 **El pie avisa siempre si el filtro esconde líneas con cantidad** («3 líneas con cantidad
están ocultas»), con un enlace que limpia los filtros. Sin ese aviso, un cliente que filtre por
SILLAS antes de enviar cree que su pedido son 12 líneas cuando son 102.

**Persistencia:** la última combinación de filtros se guarda en `localStorage` por usuario y
solicitud, para que recargar la página o volver del resumen no obligue a rehacerla. **No se
guarda en el servidor**: es preferencia de pantalla, no dato del pedido.

**Accesibilidad y teclado:** los desplegables se abren y recorren con teclado, `Esc` los cierra,
y `/` desde cualquier punto de la rejilla lleva el foco a la búsqueda por texto.

### 9.4 «Mis habituales» y «Repetir un pedido anterior»

Con 80–100 líneas, esto es lo que decide si el cliente usa la herramienta o llama por teléfono.

- **Mis habituales**: productos que aparecen en pedidos anteriores del cliente
  (`sale.order.line` de sus pedidos en `sale`, agrupado por producto). Es un `read_group` con
  `sudo()` y se sirve en el payload del catálogo como `habitual: true`.
- **Repetir un pedido anterior**: en `/my/solicitudes`, un botón por pedido pasado que crea
  una solicitud nueva **copiando sus líneas** (cantidades incluidas) con fechas vacías. Es un
  `copy()` acotado del `sale.order` + limpieza de campos. Ahorra el 90 % del trabajo al
  cliente recurrente.

### 9.5 Teclado

Requisito de hoja de cálculo, no adorno:

- `↑` / `↓` — celda de cantidad de la fila anterior/siguiente **visible**.
- `Enter` — confirma y baja.
- `Esc` — deshace la celda.
- `Tab` — siguiente celda.
- La celda de cantidad es un `<input type="text" inputmode="numeric">` con máscara: acepta
  coma y punto decimales, rechaza el resto.

🔴 **Rendimiento OWL**: el estado de las cantidades vive en un `useState` por fila
(subcomponente `QtyCell`), **no** en un objeto global, o cada pulsación repinta las 1.025
filas. El envío al servidor va con *debounce* de 600 ms y agrupa los cambios pendientes en un
solo `/lineas`.

🔴 **Rendimiento del filtrado**: el resultado se calcula **una vez por cambio de filtro** y se
guarda en el estado; no se filtra dentro del `t-foreach` de la plantilla, que lo reevaluaría en
cada repintado. Para el texto, precalcular al cargar el catálogo un campo normalizado
(minúsculas y sin acentos, `String.prototype.normalize("NFD")` + `replace(/\p{Diacritic}/gu,"")`)
en vez de normalizar 1.025 cadenas en cada pulsación. Y **contar las facetas sobre índices**
(`Map` de `tag_id → Set` de productos) construidos una sola vez al cargar: recorrer los 1.025
productos por cada una de las ~40 opciones en cada pulsación se nota.

---

## 10. El lado del comercial

**Sin pantallas nuevas.** El comercial trabaja en el formulario de alquiler de siempre.

1. **Aviso.** `activity_schedule` sobre el `sale.order` para `order.user_id` (heredado de
   `partner_id.user_id`; si está vacío, para el responsable configurado en la compañía). Sale
   en su bandeja de actividades y en el resumen diario. Más `message_post` en el chatter con
   el resumen. Más correo si `enteza_portal_aviso_email`.

2. **Dónde las ve.** Menú **Alquiler → Solicitudes de clientes**, con una acción de ventana
   sobre `sale.order`, dominio
   `[('enteza_portal_state','in',['submitted','reviewing','counter'])]` y vista lista propia
   (referencia, cliente, fecha de evento, nº de líneas, importe, estado del portal, comercial).
   🔴 **`composing` queda fuera del dominio**: una solicitud a medio montar no es trabajo
   pendiente de nadie.

3. **En el formulario**, herencia de `sale_renting.rental_order_primary_form_view`:
   - una *ribbon* con el estado del portal,
   - `enteza_portal_customer_note` visible cuando hay comentario,
   - el semáforo guardado por línea (`enteza_portal_availability`) como decoración de fila,
   - botones **«Tomar la solicitud»** (`submitted` → `reviewing`, se asigna `user_id` si está
     vacío) y **«Marcar como contrapropuesta»** (`reviewing` → `counter`).

4. **Aceptar** = botón **Confirmar** nativo. `rental_custom` ya impide confirmar un alquiler
   sin `event_date`.
   **Contrapropuesta** = ajustar cantidades + **Enviar por correo** nativo (`state = 'sent'`)
   + marcar `counter`. El cliente recibe el presupuesto y lo acepta con **«Aceptar y firmar»**,
   que es nativo y ya confirma el pedido.

---

## 11. Trazabilidad para el cliente: todo nativo

Verificado que estas vistas existen en `enteza26`:

| Etapa | Dónde la ve el cliente | De dónde sale |
|---|---|---|
| Solicitud | `/my/solicitudes` | **nuestro** (§8.1) |
| Presupuesto / contrapropuesta | `/my/quotes` | `sale.portal_my_quotations` |
| Pedido confirmado | `/my/orders` | `sale.portal_my_orders` (+ `sale_stock.portal_my_orders`, que añade el estado de entrega) |
| Factura | `/my/invoices` | `account.portal_my_invoices` |
| Estado de cobro | misma página | `account_payment.portal_my_invoices_payment` |

**Lo único que hay que añadir** es el hilo que las une: en `/my/solicitud/<id>/resumen`, una
**línea de tiempo** con enlaces a `order.get_portal_url()` del presupuesto, del pedido y de
cada `account.move` de `order.invoice_ids`. Cinco enlaces, no cinco pantallas.

⚠️ **Los 20 proveedores de pago están deshabilitados** (verificado por RPC): no hay pago
online y no se debe intentar montarlo. El cliente ve el **estado** del cobro
(`payment_state` de la factura), que es lo que se pidió; el cobro llega por transferencia.

**El diff de la contrapropuesta**, en la misma página, cuando `enteza_portal_state == 'counter'`:
tabla de tres columnas *Artículo · Solicitaste · Te proponemos*, comparando
`enteza_portal_snapshot` con las líneas actuales, resaltando lo cambiado, lo quitado y lo
añadido. Se renderiza **en QWeb del lado servidor** — es estático y no merece OWL.

---

## 12. Prerequisitos: sin esto el módulo se instala pero no sirve

Son tareas de **datos y configuración**, no de código. Hay que entregarlas como lista de
comprobación al cliente.

1. 🔴 **No hay ni un usuario del portal.** `res.users` con `share = True` = **0**. Hay 308
   contactos con `customer_rank > 0`. Hay que dar acceso al portal con el asistente nativo
   (contacto → Acción → *Conceder acceso al portal*) y marcarles
   `enteza_portal_pedidos_ok`. `auth_signup` está instalado, así que el correo de invitación
   funciona.

2. 🔴 **No hay packagings cargados.** `product.template` con `uom_ids` = 0. Sin esto no hay
   control de cajas en ningún artículo. Pasos:
   a. crear las `uom.uom` de caja necesarias (`relative_uom_id` = *Units*, `relative_factor` =
      unidades por caja) — se estiman ~10-15 distintas;
   b. asignarlas en `uom_ids` a cada artículo que se sirva en caja.
   El módulo aporta una **vista lista editable** de `product.template` con `uom_ids` y
   `enteza_units_per_box` para hacerlo en masa.

3. 🔴 **No hay ni una etiqueta de producto.** `product.tag` = **0 registros**, y no existe
   ningún campo de marca ni de modelo en `product.template`. Sin esto, **el único desplegable
   con contenido será «Categoría»** y el resto de la barra de filtros saldrá vacía. Pasos:
   a. crear las facetas en Inventario → Configuración → **Dimensiones de búsqueda**
      (Marca, Modelo, Color, Estilo… las que el negocio use de verdad);
   b. crear sus etiquetas y marcarlas **`visible_to_customers = True`**;
   c. asignarlas a los 1.025 artículos alquilables con `product_tag_ids`.
   El módulo aporta una **vista lista editable** de `product.template` con `product_tag_ids`
   para etiquetar en masa; para el grueso, lo razonable es una **importación por CSV** partiendo
   de un export de referencia + nombre.
   ⚠️ **No usar los 8 `product.attribute` que ya existen** (`brand`, `manufacturer`, `color`…):
   están vacíos y con `create_variant = 'always'`, así que asignarlos **crearía variantes de
   producto**. Ver §2.4.

4. ⚠️ **El inventario está a medio cargar.** Se midieron 4 `stock.quant` con cantidad el
   2026-08-01, y el equipo controla el stock desde Odoo desde el 2026-08-07. Hasta que el
   almacén esté cargado, **`enteza_portal_semaforo` debe quedarse en `False`**: encenderlo
   antes pinta casi todo en rojo y el cliente lo lee como "no tenéis material". **No es un
   fallo del código.**

5. **Dos almacenes** (`Sevilla`/SEV, compañía 1 Vimaple · `Jerez`/JER, compañía 2 Stileum) y
   **habrá más**. Nada puede asumir uno por compañía. Asignar
   `res.partner.enteza_portal_warehouse_id` a los clientes que vayan a usar el portal.

6. **Comercial asignado.** El aviso va a `sale.order.user_id`, heredado de
   `partner_id.user_id`. Los clientes sin comercial asignado dejarían la solicitud sin dueño:
   revisar antes de abrir el portal, y configurar un responsable de reserva por compañía.

---

## 13. Estructura del módulo

```
enteza_portal_pedidos/
├── __init__.py
├── __manifest__.py
├── controllers/
│   ├── __init__.py
│   ├── portal.py                    # rutas type='http' (páginas)
│   └── api.py                       # rutas type='jsonrpc' (datos)
├── models/
│   ├── __init__.py
│   ├── sale_order.py                # estado portal, snapshot, submit atómico
│   ├── sale_order_line.py           # semáforo guardado
│   ├── product_template.py          # caja derivada del packaging nativo
│   ├── product_facet.py             # enteza.product.facet (modelo nuevo)
│   ├── product_tag.py               # product.tag + enteza_facet_id
│   ├── res_partner.py               # permiso y almacén habitual
│   ├── res_company.py
│   └── res_config_settings.py
├── security/
│   └── ir.model.access.csv          # solo para enteza.product.facet
├── data/
│   ├── ir_sequence_data.xml         # SOL/%(year)s/00000
│   └── mail_template_data.xml       # aviso al comercial + aviso al cliente
├── views/
│   ├── sale_order_views.xml         # lista/form backend + acción + menú
│   ├── product_template_views.xml   # lista editable de packagings y etiquetas
│   ├── product_facet_views.xml      # facetas + menú + columna en product.tag
│   ├── res_partner_views.xml
│   ├── res_config_settings_views.xml
│   └── portal_templates.xml         # QWeb del portal + <owl-component>
├── static/src/
│   ├── grid/
│   │   ├── request_grid.js / .xml           # raíz: cabecera + filtros + tabla
│   │   ├── qty_cell.js   / .xml             # celda de cantidad + chip de redondeo
│   │   └── availability_dot.js / .xml       # semáforo
│   ├── filters/
│   │   ├── filter_bar.js  / .xml            # la banda: texto + desplegables + chips
│   │   ├── facet_dropdown.js / .xml         # UN desplegable genérico y reutilizable
│   │   └── active_chips.js / .xml           # filtros activos + «Limpiar todo»
│   ├── services/
│   │   ├── request_service.js               # llamadas jsonrpc, caché, debounce
│   │   └── catalog_index.js                 # índices y normalización de texto (§9.5)
│   └── scss/
│       └── portal_pedidos.scss
├── tests/
│   ├── __init__.py
│   ├── test_submit_flow.py
│   ├── test_packaging.py
│   ├── test_availability.py
│   ├── test_facets.py
│   └── test_portal_http.py
└── README.md
```

🔴 **`facet_dropdown` es UN componente, no uno por dimensión.** «Marca», «Modelo» y «Color» son
el mismo control con datos distintos. Escribir un componente por faceta rompería la promesa de
§2.4: que el cliente pueda añadir «Estilo» sin llamar al programador.

**Manifiesto:**

```python
{
    'name': 'Enteza - Portal de pedidos de alquiler',
    'version': '19.0.1.0.0',
    'category': 'Sales/Rental',
    'summary': "Solicitudes de alquiler hechas por el cliente desde el portal",
    'author': 'Enteza',
    'license': 'OPL-1',
    'depends': [
        'portal',
        'mail',
        'sale_management',
        'sale_renting',
        'sale_stock_renting',   # el motor de disponibilidad vive aquí, no en sale_renting
        'stock',
        'rental_custom',        # aporta event_date y rental_billable_days
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/mail_template_data.xml',
        'views/sale_order_views.xml',
        'views/product_facet_views.xml',
        'views/product_template_views.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'views/portal_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': ['enteza_portal_pedidos/static/src/**/*'],
    },
    'installable': True, 'application': False, 'auto_install': False,
}
```

**`security/` mínimo**: un solo `ir.model.access.csv` para `enteza.product.facet` (lectura a
`base.group_user`, escritura a `stock.group_stock_manager`). **No hay grupos nuevos**: la
autorización del portal es `res.partner.enteza_portal_pedidos_ok` + la `ir.rule` portal nativa
+ la comprobación explícita del controlador.

---

## 14. Gotchas de Odoo 19 que muerden en este módulo

Todos verificados en este proyecto. Ignorar uno cuesta un ciclo entero de despliegue, y aquí
**no hay entorno de pruebas**.

| # | Trampa | Qué hacer |
|---|---|---|
| 1 | `website=True` en una ruta | **No usarlo.** `website` no está instalado (§2.1) |
| 2 | `type='json'` en un controlador | En la 19 es **`type='jsonrpc'`** |
| 3 | `_sql_constraints` | **Fallo silencioso**: instala y la restricción no existe. Usar `models.Constraint(...)` / `models.Index(...)` / `models.UniqueIndex(...)` |
| 4 | `res.groups.category_id` | **Eliminado** → `privilege_id` (`res.groups.privilege`). Aquí no hacen falta grupos, pero si se añaden, este es el patrón |
| 5 | `<xpath expr="//…[@string='…']">` | **Rompe la actualización del módulo entero.** Nunca `@string` como selector; usar `name` o subir al padre desde un campo |
| 6 | `<group expand="0" string="…">` en una vista **search** | No instala. En `search` el `<group>` solo admite `name` (en `form` sí vale `string`) |
| 7 | `attrs` / `states` en vistas | Eliminados. `invisible="…"`, `readonly="…"`, `required="…"` directos |
| 8 | `.py` en `models/` sin importar en `__init__.py` | **Fallo silencioso**: instala y el código no se carga. Pasar `validar_modulo.py` antes de cada `git pull` |
| 9 | `product_uom` en `sale.order.line` | Es **`product_uom_id`**. (En `stock.move` sí sigue siendo `product_uom`) |
| 10 | `uom.uom.factor` | Para packagings, el que manda es **`relative_factor`** con `relative_uom_id` |
| 11 | `product.packaging` | **No existe en la 19.** Es `product.template.uom_ids` |
| 12 | Crear pedido/líneas sin `in_rental_app=True` | Las líneas **no** salen de alquiler aunque el producto tenga `rent_ok` |
| 13 | `rent_ok` como sinónimo de "material físico" | Hay 6 servicios marcados alquilables. Filtrar **`type='consu'` Y `rent_ok`** |
| 13b | Usar `product.attribute` para marca/modelo | Los 8 existentes tienen `create_variant='always'`: asignarlos **crea variantes** y multiplica el catálogo. Usar etiquetas + facetas (§2.4) |
| 13c | Filtrar dentro del `t-foreach` de OWL | Se reevalúa en cada repintado. Calcular la lista filtrada una vez y guardarla en el estado (§9.5) |
| 14 | `toISOString()` en JS | Convierte a UTC y al este de Greenwich **cambia el día**. Construir la clave a mano |
| 15 | `getDay()` | Empieza en domingo. Para semana en lunes: `(f.getDay() + 6) % 7` |
| 16 | Datetimes crudos | Están en UTC; España +2 en verano. `fields.Datetime.context_timestamp(...)` |
| 17 | Comparar floats con `> 0` | `float_compare` con `precision_get('Product Unit of Measure')` |
| 18 | Error de JS en el portal | **Pantalla en blanco sin log de servidor**. Solo se ve en F12 |
| 19 | Bundle de assets cacheado | `Ctrl+F5` tras cada despliegue con JS/SCSS |
| 20 | Añadir `company_id` a productos o a sus reglas | Los productos son **compartidos** (1.908 con `company_id = False`). Rompe todo el alquiler |

**Antes de cada despliegue, obligatorio:**

```bash
python .claude/skills/odoo19-dev/scripts/validar_modulo.py enteza_portal_pedidos
python .claude/skills/odoo19-dev/scripts/validar_vistas.py  enteza_portal_pedidos
```

Pasarlos no garantiza que instale (no comprueban campos, dominios ni referencias externas),
pero fallarlos garantiza que no.

---

## 15. Pruebas

`TransactionCase` / `HttpCase` con `@tagged('post_install', '-at_install')`.

⚠️ **No se pueden ejecutar**: el hosting no da acceso a `odoo-bin --test-enable`. Se escriben
igualmente y **al entregar hay que decir que están validadas por sintaxis y no ejecutadas**.

Escenarios mínimos:

- **`test_submit_flow`** — crear solicitud en `composing`; segunda llamada a
  `/solicitud/nueva` devuelve la misma; `submit` sin fechas → `UserError`; `submit` correcto →
  snapshot escrito, referencia asignada, actividad creada para `user_id`, estado `submitted`;
  **`submit` dos veces seguidas no duplica nada** (idempotencia).
- **`test_packaging`** — producto con caja de 25: qty 90 → `UserError` con los redondeos 75 y
  100; qty 100 → pasa; producto sin packaging → cualquier cantidad pasa; qty 10 con caja de 25
  → la propuesta "abajo" es 0.
- **`test_availability`** — montar un `stock.quant` y un alquiler solapado; comprobar los tres
  colores; comprobar que **el JSON no contiene la cantidad libre**; comprobar que con
  `enteza_portal_semaforo = False` devuelve todo `grey` sin consultar.
- **`test_facets`** — una etiqueta sin faceta **no** llega al portal; una etiqueta con
  `visible_to_customers = False` tampoco; una faceta con `portal_visible = False` no se sirve;
  una faceta cuyas etiquetas no usa ningún producto del catálogo **no aparece**; el payload
  manda `tag_ids` como enteros y los nombres una sola vez.
- **`test_portal_http`** — login de un portal user; leer el catálogo; **un portal user de otro
  cliente recibe 404** sobre la solicitud ajena; un portal user **sin**
  `enteza_portal_pedidos_ok` no ve la tarjeta ni puede llamar a la API.

Montaje de escenarios: copiar los idiomas de `sale_stock_renting/tests/test_rental.py`
(`with_context(in_rental_app=True)`, `stock.quant` + `action_apply_inventory()`).

---

## 16. Criterios de aceptación

1. Un cliente con acceso al portal y `enteza_portal_pedidos_ok` entra en `/my`, ve la tarjeta
   **Solicitudes** y abre una nueva.
2. Indica fecha de evento, entrega y retirada, y elige almacén si tiene más de uno.
3. Ve el catálogo completo en una rejilla densa con celdas y lo acota **sin recargar la
   página** con: búsqueda por texto (sin acentos, palabras sueltas en cualquier orden),
   desplegable de categoría y **un desplegable por cada faceta configurada** (Marca, Modelo,
   Color…), más los conmutadores de habituales/con cantidad/sin disponibilidad.
3b. Los desplegables muestran **contadores que se actualizan** al combinar filtros, los filtros
   activos aparecen como *chips* con ✕ y hay «Limpiar todo».
3c. El cliente crea una faceta nueva («Estilo») en Odoo, la asigna a unos artículos, y **su
   desplegable aparece en el portal sin tocar código**.
3d. Con un filtro activo que esconde líneas con cantidad, el pie **avisa** y el contador de la
   cabecera sigue mostrando el total real del pedido.
4. Monta **100 líneas** tecleando cantidades, moviéndose con el teclado, **sin perder de vista
   la cabecera ni los botones**.
5. En un artículo que va en cajas de 25, teclea 90 y se le ofrecen **75 y 100**; no puede
   enviar hasta resolverlo.
6. Con el semáforo activado, ve verde/ámbar/rojo por artículo y **en ningún sitio la cantidad
   libre** (comprobado también en el JSON de red).
7. Envía. El comercial asignado recibe **actividad + mensaje en el chatter** y la ve en
   **Alquiler → Solicitudes de clientes**.
8. El comercial baja una cantidad, marca contrapropuesta y envía el presupuesto.
9. El cliente ve en el portal **qué pidió y qué se le propone**, y acepta con el
   **«Aceptar y firmar» nativo** → el pedido queda confirmado.
10. Desde su usuario, el cliente sigue la traza completa: solicitud → presupuesto → pedido →
    factura → estado del cobro, **con las páginas nativas de Odoo 19**.
11. `validar_modulo.py` y `validar_vistas.py` pasan limpios.

---

## 17. Orden de implementación sugerido

Por si el desarrollo se corta a mitad, este orden deja algo utilizable en cada corte:

1. **Modelos + backend del comercial** (§4, §10). Se puede probar creando solicitudes por RPC.
2. **Facetas y etiquetado** (§4.4): modelo, menús y vista de etiquetado en masa. **Va antes que
   la rejilla a propósito**: sin datos cargados, la barra de filtros no se puede probar, y
   cargarlos es tarea del cliente, que tarda (§12.3).
3. **Controladores HTTP + páginas del portal en QWeb**, sin OWL: lista de solicitudes, resumen,
   diff. Ya da trazabilidad.
4. **API `jsonrpc` + rejilla OWL** (§8, §9). El grueso.
5. **Barra de filtros** (§9.3): `facet_dropdown` genérico, índices, chips y contadores.
6. **Semáforo** (§6). Aislado a propósito: es lo único que depende del inventario cargado.
7. **Extras**: repetir pedido anterior, habituales, miniatura en *popover*.

**Fuera de alcance de esta primera versión** (anotado para no colarlo por iniciativa propia):
pegar desde el portapapeles varias filas a la vez, adjuntar un plano del evento, chat en tiempo
real con el comercial, pago online (§11), y solicitudes de cambio sobre pedidos **ya
confirmados** — eso es lo que intentaba `rental_portal_change_request` y es otro proyecto.

---

## 18. Despliegue

1. `validar_modulo.py` + `validar_vistas.py`.
2. Commit y push a la rama `19.0` de `enteza-odoo`.
3. Xtendoo hace `git pull` contra el addons path de `enteza26`.
4. Aplicaciones → **Actualizar lista de aplicaciones** → Instalar.
5. 🔴 **Que aparezca en la lista no significa que esté instalado.** Comprobar el `state` por
   RPC:
   ```bash
   python .claude/skills/odoo19-dev/scripts/odoo19.py search ir.module.module \
       '[["name","=","enteza_portal_pedidos"]]' name,state,latest_version
   ```
6. `Ctrl+F5` en el navegador (assets).
7. Recorrer los prerequisitos de §12 con el cliente.

**`enteza26` es producción.** Confirmar con el usuario antes de cualquier escritura de datos,
y `archive` antes que `unlink`.
