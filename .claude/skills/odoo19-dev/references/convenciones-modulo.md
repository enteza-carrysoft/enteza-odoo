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

En `res.groups` conviven cuatro campos y es fácil coger el que no es: `implied_ids` (los que
implica, almacenado), `implied_by_ids` (los que le implican, almacenado) y las versiones
transitivas `all_implied_ids` / `all_implied_by_ids`, que **no** están almacenadas y por tanto
no se pueden usar en un `search`.

Comparación de cantidades: `float_compare` con
`self.env['decimal.precision'].precision_get('Product Unit of Measure')`, que es el idioma que
usa el propio `sale_renting`. Nunca `> 0` a pelo sobre floats.

### Hooks

`post_init_hook(env)` recibe el entorno directamente (antes eran `cr, registry`).

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
