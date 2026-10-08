# Architecture

Módulo `rental_custom`, `19.0.1.16.1` → `19.0.1.17.0`. Todo aditivo; solo toca el asistente
«Registrar faltas» (modelos transitorios) y añade el primer bloque `assets` del manifiesto.

Fuentes leídas (rama `19.0` de `odoo/odoo`, el 2026-10-08):
`web/static/src/views/fields/x2many/x2many_field.{js,xml}`,
`web/static/src/views/list/list_renderer.{js,xml}`, `list_arch_parser.js`,
`core/hotkeys/hotkey_service.js`, `core/dialog/dialog.js`. Hechos usados:
- `X2ManyField` declara `static components = { ..., ListRenderer, ... }` y su plantilla pinta
  `<ListRenderer t-props="this.rendererProps"/>`: una subclase que sustituya `ListRenderer` en
  `components` cambia el renderer sin tocar la plantilla.
- `ListRenderer.getRowClass(record)` da la clase de cada `<tr class="o_data_row">`.
- `onCellKeydownEditMode(hotkey, cell, group, record)` solo trata `tab`, `shift+tab`, `enter`
  y `escape`; las flechas en edición no hacen nada. `enter` llama a `editNextRecord`, que hace
  `list.leaveEditMode({validate: true}).then(ok => ok && list.enterEditMode(siguiente))`.
- Al entrar en edición, `onPatched` enfoca la primera columna editable de la fila
  (`focusCell` salta las de solo lectura): en este asistente, «Faltas».
- `<list limit="N">` se respeta en un x2many (`list_arch_parser` → `activeField.limit`).
- El servicio de atajos escucha `keydown` en `window` (fase de burbuja); el diálogo cierra con
  el atajo `escape`. Un `stopPropagation()` en el `keydown` del buscador impide que llegue.

## Models

### `rental.missing.wizard.line` (`wizard/rental_missing_wizard.py`)
- Nuevo `default_code = fields.Char(related="product_id.default_code", string="Referencia")`,
  no almacenado (AC2). Modelo transitorio: sin cambio de esquema persistente.

### Orden de las líneas (AC1)
- Nueva función de módulo `missing_line_sort_key(sale_line)` en
  `wizard/rental_missing_wizard.py`:
  `(not code, code or "", "" if code else (product.name or "").lower(), sale_line.id)` con
  `code = product.default_code`. Las que tienen referencia primero, por texto; las demás por
  nombre; desempate por id de la línea del pedido.
- `sale.order.action_open_missing_wizard` (`models/sale.py`) ordena las líneas con esa clave
  antes de los `Command.create`. El `_order` de la línea transitoria sigue siendo `id`, así
  que el One2many devuelve el orden de creación = el orden pedido.

`action_confirm`, `_create_missing_order` y `_check_quantities` no cambian (AC9, AC11).

## Views

`wizard/rental_missing_wizard_view.xml`:
- `<field name="line_ids" widget="rental_missing_lines">`.
- `<list editable="bottom" create="false" delete="false" limit="1000">` (AC3).
- Columnas: `sale_line_id` (oculta), `default_code` (readonly, AC2), `product_id` (readonly,
  `context="{'display_default_code': False}"` para que el nombre salga sin `[código]`),
  `qty_rented`, `qty_lost_prev`, `qty_missing`.
- El texto de ayuda añade una línea sobre el buscador y el teclado.

## Client widget (`static/src/rental_missing_lines/`)

`rental_missing_lines.js`:
- `normalize(text)`: `NFD` + quitar diacríticos + minúsculas.
- `isRecordVisible(record, filter)`: `filter.onlyMissing && !(qty_missing > 0)` → oculta;
  con `term = normalize(filter.search.trim())` no vacío → visible si
  `normalize(default_code).startsWith(term)` o `normalize(nombre).includes(term)`, donde
  `nombre` sale de `record.data.product_id` (objeto `{id, display_name}`; se acepta también
  `[id, nombre]` por robustez).
- `RentalMissingListRenderer extends ListRenderer`:
  - `static props = [...ListRenderer.props, "missingFilter"]`.
  - `setup()`: `super.setup()` y `this.missingFilter = useState(this.props.missingFilter.state)`
    para volver a pintar al cambiar el filtro.
  - `get visibleRecords()` = `props.list.records.filter(isRecordVisible)` (orden de pantalla,
    incluido el reordenado por cabecera).
  - `getRowClass(record)`: la nativa + `" d-none"` si no es visible (AC4, AC8). Las filas
    ocultas siguen en `list.records`: sus valores viajan al guardar (AC9).
  - `onCellKeydownEditMode(hotkey, cell, group, record)`:
    - `arrowdown` / `arrowup` → `moveTo(record, ±1)`: siguiente/anterior en `visibleRecords`;
      si es la primera y `arrowup` → `leaveEditMode({validate: true})` y enfocar el buscador;
      si es la última y `arrowdown` → nada (pero devuelve `true` para consumir la tecla).
    - `enter` con `search` no vacío → `leaveEditMode({validate: true})`, vaciar `search`,
      enfocar el buscador (AC6).
    - `enter` con `search` vacío y `onlyMissing` activo → `moveTo(record, +1)` (la fila
      siguiente nativa podría estar oculta); al final, vuelve a la primera visible como el
      nativo.
    - resto → `super`.
  - `moveTo` usa el mismo patrón que `editNextRecord`:
    `leaveEditMode({validate: true}).then(ok => ok && list.enterEditMode(destino))` ⇒ el valor
    se aplica en el cliente antes de cambiar de fila.
- `RentalMissingLinesField extends X2ManyField`:
  - `static template = "rental_custom.RentalMissingLinesField"`,
    `static components = { ...X2ManyField.components, ListRenderer: RentalMissingListRenderer }`.
  - `setup()`: `super.setup()`, `this.filter = useState({ search: "", onlyMissing: false })`,
    `this.searchRef = useRef("search")`.
  - `get rendererProps()`: los de `super` + `missingFilter: { state: this.filter,
    focusSearch: () => this.focusSearch() }`.
  - `get counts()`: `{ total: list.records.length, missing: nº con qty_missing > 0 }` (AC8,
    independiente de filtros). `list.count` se usaría si `limit` se superase, pero con 1000 no
    ocurre.
  - `onSearchKeydown(ev)`: `getActiveHotkey(ev)`:
    - `enter` → `preventDefault` + `stopPropagation`; primera visible → `list.enterEditMode`
      (AC5); sin visibles, nada.
    - `escape` con texto → vaciar, `preventDefault` + `stopPropagation` (no cierra el diálogo,
      AC10). Vacío → no se toca: comportamiento nativo.
- Registro: `registry.category("fields").add("rental_missing_lines",
  { ...x2ManyField, component: RentalMissingLinesField })`. Sin `patch()` (AC11).

`rental_missing_lines.xml`: `rental_custom.RentalMissingLinesField`, `t-inherit="web.X2ManyField"
t-inherit-mode="primary"`, `xpath //ListRenderer position="before"` con una barra:
`<input type="search" t-ref="search" t-model="filter.search" t-on-keydown="onSearchKeydown"
placeholder="Buscar por referencia o nombre…">`, un `form-switch` «Solo con faltas»
(`t-model="filter.onlyMissing"`) y el contador `«N líneas · M con faltas»`. Textos con `_t`
desde el JS.

La herencia `primary` crea plantilla nueva; la base no cambia.

## Security

Sin cambios: `ir.model.access.csv` igual (las dos filas del asistente para
`sales_team.group_sale_salesman`), sin reglas, sin `sudo()`, sin rutas. El widget no hace RPC
propios: filtra lo que el formulario ya cargó (AC4, AC11).

## Manifest

- `version` → `19.0.1.17.0`.
- Nuevo `'assets': {'web.assets_backend': ['rental_custom/static/src/rental_missing_lines/*']}`.
  Solo esa carpeta: `static/src/js/` y `static/src/widgets/` siguen fuera (AC11).
- `depends` sin cambios (`web` llega por `sale_management`).

## Reports
Ninguno.

## Tours
Ninguno (no ejecutables en este hosting). AC4–AC8 y AC10 se comprueban en pantalla.

## Demo data
Ninguna.

## Documentation
- `readme/DESCRIPTION.md`: párrafo «Registrar faltas con muchas líneas» (buscador, teclado,
  «Solo con faltas»).
- Docstring del módulo JS.

## Tests (`tests/test_faltas_buscador.py`, registrado en `tests/__init__.py`)
Escritos, no ejecutados. Ver test-plan.md.

## Decisiones
- Intro con buscador vacío y «Solo con faltas» activo salta a la siguiente fila **visible**,
  no a la siguiente nativa (que podría estar oculta). Con ambos filtros vacíos se usa el
  nativo tal cual. Es la lectura de AC6 «baja a la fila siguiente» coherente con AC7.
- El orden se fija en el servidor (prueba Python posible) y no con `default_order`, que en un
  x2many no admite un campo related no almacenado.
