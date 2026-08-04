# Convenciones para módulos de este repositorio

## Estructura y nombres

Cada módulo es una carpeta en la **raíz** del repositorio. Los módulos propios de Enteza van
con prefijo `enteza_`.

```
enteza_mi_modulo/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   └── mi_modelo.py
├── security/
│   ├── ir.model.access.csv
│   └── mi_modulo_security.xml
├── views/
│   └── mi_modelo_views.xml
├── tests/
│   ├── __init__.py
│   └── test_algo.py
└── README.md
```

Manifiesto mínimo:

```python
{
    'name': 'Enteza - Lo que hace',
    'version': '19.0.1.0.0',
    'category': '...',
    'author': 'Enteza',
    'license': 'OPL-1',
    'depends': [...],
    'data': ['security/...', 'views/...'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
```

**Código, comentarios y textos de interfaz en castellano.** La instancia trabaja en español y
el equipo también. Los nombres técnicos de modelos y campos pueden ir en inglés si siguen una
convención existente, pero las etiquetas y los mensajes de error van en castellano.

## Sintaxis de la 19 que cambió

### Vistas

**`attrs` y `states` no existen** desde la 17. Se usan atributos condicionales directos:

```xml
<!-- MAL, no instala -->
<field name="x" attrs="{'invisible': [('state','=','draft')]}"/>

<!-- BIEN -->
<field name="x" invisible="state == 'draft'"/>
<field name="y" readonly="state != 'draft'"/>
<field name="z" required="tipo == 'a'"/>
```

Las vistas `tree` se llaman `list`.

#### `<group>` en una vista de búsqueda: ni `expand` ni `string`

🔴 **Rompe la instalación**, y el error no dice cuál es el atributo culpable: solo
*«Vista no disponible <nombre> definición en <fichero>»* (que es
`ValidationError('Invalid view %(name)s definition in %(file)s')` de `ir_ui_view.py:507`
traducido). El detalle va al log del servidor, al que aquí no se llega.

```xml
<!-- MAL, no instala: el bloque de agrupaciones de la 15 y la 18 -->
<group expand="0" string="Agrupar por">
    <filter name="g_estado" string="Estado" context="{'group_by': 'state'}"/>
</group>

<!-- BIEN: el cliente web ya rotula el bloque por su cuenta -->
<group>
    <filter name="g_estado" string="Estado" context="{'group_by': 'state'}"/>
</group>
```

La causa es que **las vistas se validan contra un esquema RELAX NG, pero solo algunos
tipos**: `view_validation.schema_valid` lleva
`@validate('calendar', 'graph', 'pivot', 'search', 'list', 'activity')`. **Los formularios
no están en esa lista**, así que el mismo `<group string="...">` es correcto en un form y
mortal en un search — que es justo lo que despista al diagnosticar. La definición que manda
está en `base/rng/common.rng` y solo acepta `position`, `groups`, `colspan`, `rowspan`,
`fill`, `height`, `width`, `name`, `color`, `invisible` y `col`.

Comprobado el 2026-08-02 validando en local contra el esquema real (`expand` y `string`
rechazados los dos, `name` aceptado) y contra `enteza26`: de todas las vistas de búsqueda de
la instancia, **ninguna** usa `expand` en un `<group>`.

Lo que sí sigue siendo válido dentro de un dominio de filtro, y parece sospechoso pero no lo
es: `context_today()`, `allowed_company_ids`, `current_date`, `uid`, `time`, `datetime`.
Están en la lista blanca `IGNORED_IN_EXPRESSION` de `view_validation.py`.

#### Un xpath no puede seleccionar por `@string`

🔴 **Rompe la actualización del módulo entero**, no solo la vista, y `validar_vistas.py` **no
lo detecta**: es una regla de herencia de vistas, no de esquema RELAX NG, así que pasa la
validación local y solo revienta contra el servidor real. Comprobado el 2026-08-04
actualizando `enteza_prestamo_intercompania` en `enteza26`:

```xml
<!-- MAL: el servidor lo rechaza con «View inheritance may not use attribute 'string' as a
     selector», y el `git pull` + Actualizar entero se para ahí -->
<xpath expr="//setting[@string='Rental Transfers']" position="after">

<!-- BIEN: selecciona por algo que no sea `string` — un `name`, o sube al padre desde un
     campo que sí lo tenga -->
<xpath expr="//field[@name='group_rental_stock_picking']/parent::setting" position="after">
```

Tiene sentido una vez se sabe: `string` es texto traducible, y apoyar una herencia en un
valor que cambia con el idioma del usuario sería frágil. Pero el error no avisa en local —
para eso haría falta un servidor Odoo 19 real, que aquí no hay—, así que **la única forma de
pillarlo es no usar `@string` como selector nunca**, ni siquiera en un `<setting>` de
`res.config.settings`, donde parece el único candidato natural.

#### Validar las vistas antes de desplegar

Esa comprobación por esquema **se puede reproducir en local**, que es lo único de la
instalación que no exige un ciclo de `git pull` + Actualizar:

```bash
python .claude/skills/odoo19-dev/scripts/validar_vistas.py enteza_mi_modulo
```

Descarga los `.rng` de Odoo Community 19.0, los cachea y dice el atributo y la línea exactos.
Necesita `lxml` (`python -m pip install lxml`). **Pasarlo no garantiza que el módulo instale**
—no comprueba campos, dominios ni referencias externas—, pero fallarlo garantiza que no.

### Modelos y campos

| Antes | Ahora |
|---|---|
| `product_uom` (en `sale.order.line`) | **`product_uom_id`** |
| `tax_id` | `tax_ids` |
| `type='product'` | `type='consu'` + `is_storable=True` |
| `detailed_type` | eliminado |
| `uom_po_id` | eliminado |
| `uom.uom.factor` | **`relative_factor`** (existe `rounding`) |
| `rental` (en producto) | `rent_ok` |
| `ir.ui.menu.groups_id` | **`group_ids`** (verificado por RPC el 2026-08-01) |
| `res.groups.category_id` | **eliminado** → `privilege_id` (ver abajo) |
| `_sql_constraints = [...]` | **`models.Constraint('CHECK (...)', 'mensaje')`** |
| `_auto_init` + `tools.create_index` | **`models.Index('(campo1, campo2)')`** |
| `stock.move.name` | **eliminado** → `description_picking` (y `date` es obligatorio) |
| `stock.location.scrap_location` / `return_location` | **eliminados** |
| `stock.move.product_uom` | **sigue llamándose así**, no `product_uom_id` (ojo: en `sale.order.line` sí cambió) |

### Restricciones e índices: `_sql_constraints` ya no existe

🔴 **Fallo silencioso.** En la 19, `add_to_registry()` detecta `_sql_constraints`, escribe en
el log «Model attribute '_sql_constraints' is no longer supported» y **no crea la
restricción**. El módulo instala con normalidad y la comprobación simplemente no está. Se
descubrió así en `enteza_prestamo_intercompania` (v19.0.1.0.0).

```python
# MAL: no falla, pero la restricción no llega a la base de datos
_sql_constraints = [('companias_distintas', 'CHECK (a != b)', 'Mensaje')]

# BIEN (idioma de la 19; el nombre del atributo empieza por `_`)
_companias_distintas = models.Constraint('CHECK (a != b)', 'Mensaje')
_producto_intervalo_idx = models.Index('(product_id, date_from, date_to)')
```

Ejemplos nativos: `sale.order._date_order_conditional_required`,
`stock.move.line._free_reservation_index`, `ir.rule._no_access_rights`.

### Grupos: `res.groups` ya no tiene `category_id`

🔴 **Esto sí rompe la instalación**, con `ValueError: Invalid field 'category_id' in
'res.groups'` al cargar el XML de seguridad. La 19 intercala el modelo
**`res.groups.privilege`**: el grupo apunta a un privilegio y el privilegio a la
`ir.module.category`.

```xml
<record id="privilege_x" model="res.groups.privilege">
    <field name="name">Lo que agrupa</field>
    <field name="category_id" ref="base.module_category_supply_chain"/>
    <field name="sequence">20</field>
</record>

<record id="group_x_usuario" model="res.groups">
    <field name="name">Usuario</field>
    <field name="privilege_id" ref="privilege_x"/>   <!-- NO category_id -->
    <field name="sequence">10</field>
</record>
```

Los grupos de un mismo privilegio salen como **selector** en la ficha del usuario, así que la
pareja Usuario/Responsable encadenada con `implied_ids` es el patrón que espera la interfaz.
Categorías útiles: `base.module_category_supply_chain` (es la del privilegio *Inventory*
nativo, privilegio 7 → categoría 3, verificado por RPC).

### `ir.rule`: no escribir `global`

Es un campo **calculado y almacenado** (`_compute_global` = `not groups`). Una regla sin
grupos ya es global; fijarlo en el XML es redundante.

En `res.groups` conviven cuatro campos y es fácil coger el que no es: `implied_ids` (los que
implica, almacenado), `implied_by_ids` (los que le implican, almacenado) y las versiones
transitivas `all_implied_ids` / `all_implied_by_ids`, que **no** están almacenadas y por tanto
no se pueden usar en un `search`.

Comparación de cantidades: `float_compare` con
`self.env['decimal.precision'].precision_get('Product Unit of Measure')`, que es el idioma que
usa el propio `sale_renting`. Nunca `> 0` a pelo sobre floats.

### Hooks

`post_init_hook(env)` recibe el entorno directamente (antes eran `cr, registry`).

## Código que Odoo no carga y no lo dice 🔴

**Fallo silencioso, y de los que cuestan un despliegue entero.** Un fichero de `models/` que
no esté en `models/__init__.py` sencillamente no se carga: el módulo instala con normalidad,
no hay error en ningún log y todo lo demás funciona. Se descubre cuando alguien prueba la
funcionalidad y «no pasa nada».

Ocurrió el 2026-08-02 en `enteza_prestamo_intercompania`: se borró un `models/sale_order.py`
y su import, y al crear otro fichero con el mismo nombre para otra cosa **no se volvió a
añadir el import**. El `action_confirm` que abría el diálogo nunca llegó a registrarse.

```bash
python .claude/skills/odoo19-dev/scripts/validar_modulo.py enteza_mi_modulo
python .claude/skills/odoo19-dev/scripts/validar_modulo.py     # todos los del repositorio
```

Comprueba los `.py` no importados, los paquetes (`wizard/`, `report/`) que faltan en el
`__init__.py` de la raíz, y los ficheros de datos declarados que no existen o que existen sin
declarar. **Pasarlo por el módulo antes de cada `git pull`.**

Al pasarlo por el repositorio entero (2026-08-02) aparecieron seis fallos más, todos en
módulos de terceros: `app_common`, `app_odoo_customize` (dos modelos sin cargar),
`om_account_bank_statement_import`, `sale_order_line_product_image` y
`stock_picking_batch_report`.

## Dependencias del manifiesto

**El error más caro y el más fácil de cometer.** Si una vista o un modelo referencia algo de
un módulo que no está en `depends`, el orden de carga no está garantizado y **la instalación
falla**.

Para saber qué módulo aporta un campo:

```bash
python .claude/skills/odoo19-dev/scripts/odoo19.py search ir.model.fields \
    '[["model","=","sale.order"],["name","=","event_date"]]' name,modules,store
```

Casos reales de este proyecto:

- `event_date` lo aporta **`rental_custom`**, no el alquiler nativo.
- Todo el motor de disponibilidad de alquiler lo aporta **`sale_stock_renting`**, no
  `sale_renting`.

### External IDs que engañan

- El grupo de direcciones de entrega es **`account.group_delivery_invoice_address`**. En la 19
  vive en `account`, no en `sale`. Con el prefijo antiguo la instalación revienta con un error
  de referencia externa.
- `sale` depende de `account` de forma transitiva (vía `account_payment`), así que se pueden
  referenciar external ids de `account` sin declararlo en `depends`. Conviene comentarlo en el
  manifiesto para que nadie lo "arregle" después.

## Seguridad

Todo modelo nuevo necesita `ir.model.access.csv`, o Odoo avisa y el modelo queda inaccesible
para los usuarios normales.

### Multi-compañía

Es donde más fácil es equivocarse. Las reglas de registro aíslan por compañía, y un documento
que implique **dos** compañías desaparece para una de ellas con la regla clásica:

```python
# MAL para un documento entre dos compañías
[('company_id', 'in', company_ids)]

# BIEN
['|', ('company_id', 'in', company_ids), ('company_dest_id', 'in', company_ids)]
```

Otras dos reglas del mismo terreno:

- Para mover stock entre compañías hace falta una **ubicación de tránsito con `company_id`
  vacío**. Con compañía asignada, la mitad del flujo falla con un error de acceso poco
  descriptivo. Es la causa número uno de problemas en este tipo de módulo.
- **Los productos son compartidos** (`company_id = False` en 1.908 plantillas). No añadir
  `company_id` a productos ni a sus reglas: rompería la premisa de todo el desarrollo de
  alquiler.

Al crear registros de otra compañía, `with_company()` y `sudo()` **acotados y comentados**,
nunca un `sudo()` global al método entero.

## Pruebas

Se escriben con `TransactionCase` y `@tagged('post_install', '-at_install')`.

⚠️ **No se pueden ejecutar**: no hay acceso a `odoo-bin --test-enable` en el hosting. Se
escriben igualmente —documentan el comportamiento esperado y valdrán el día que haya
staging— pero **al entregar hay que decir que no están ejecutadas**.

Para montar escenarios, copiar los idiomas de `sale_stock_renting/tests/test_rental.py` en vez
de pelearse con los campos calculados:

```python
pedido = env['sale.order'].with_context(in_rental_app=True).create({...})
quant = env['stock.quant'].create({'product_id': ..., 'inventory_quantity': 10,
                                   'location_id': almacen.lot_stock_id.id})
quant.action_apply_inventory()
```

## Antes de escribir un módulo nuevo

**Mirar si ya existe.** Ver `catalogo-modulos.md`: hay 33 módulos en el repositorio y varios
resuelven cosas que parecen pendientes. Instalar dos módulos que resuelven lo mismo por vías
distintas —sobre todo si ambos calculan stock— produce cifras que no cuadran y es muy difícil
de diagnosticar después.
