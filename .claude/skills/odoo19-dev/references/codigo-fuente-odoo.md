# Dónde está el código fuente de Odoo

Ante cualquier duda sobre cómo se comporta el nativo, **leer el código gana a suponer**. Ha
pasado varias veces en este proyecto que la intuición y la documentación decían una cosa y el
código otra.

## Odoo Enterprise 18 — la fuente para TODO lo de alquiler

Repositorio del cliente con el código de Enterprise. **Es aquí donde hay que investigar
`sale_renting` y `sale_stock_renting`**, y en general cualquier módulo Enterprise:

```
https://github.com/enteza-carrysoft/odoo_enterprise_18            (rama 18.0)
https://github.com/enteza-carrysoft/odoo_enterprise_18/tree/18.0/sale_renting
```

🔴 **En `odoo/odoo` (Community) no está el código de alquiler.** Buscarlo ahí lleva a la
conclusión falsa de que "Odoo no trae cálculo de disponibilidad", que es el error nº 1 de este
proyecto. Y los métodos del motor son **privados** (`_get_unavailable_qty`,
`_get_virtual_unavailable_qty_in_rent`), así que **tampoco se pueden llamar por RPC**: este
repositorio es la única forma de leerlos.

Es la **18**, no la 19, pero para los módulos de alquiler la diferencia es mínima y sirve para
entender la mecánica. Lo que se lea ahí **hay que confirmarlo contra `enteza26`** con
`odoo19.py fields ...` antes de darlo por bueno en la 19 — y donde no se pueda confirmar
(métodos privados), **decirlo al entregar** en vez de presentarlo como verificado.

⚠️ **Es privado, así que hay que clonarlo** (ver abajo). Comprobado el 2026-08-01:
`raw.githubusercontent.com` devuelve **404** y `gh` **no está instalado** en esta máquina. Lo
que sí funciona es `git`, que tiene las credenciales configuradas —
`git ls-remote https://github.com/enteza-carrysoft/odoo_enterprise_18 18.0` responde—, de modo
que el clonado disperso de la sección siguiente es la vía buena.

### Cómo consultarlo sin bajarse el repo entero

Es enorme. Clonado disperso, solo los módulos que interesen:

```bash
git clone --depth 1 --branch 18.0 --filter=blob:none --sparse \
    https://github.com/enteza-carrysoft/odoo_enterprise_18.git ent18
cd ent18
git sparse-checkout set sale_renting sale_stock_renting
```

Añadir más módulos después:

```bash
git sparse-checkout set sale_renting sale_stock_renting sale_stock_renting_extension
```

Listar qué módulos hay sin descargar nada:

```bash
git ls-tree -d --name-only HEAD | grep -i rent
```

### Módulos de alquiler en ese repositorio

`sale_renting` · `sale_stock_renting` · `sale_renting_crm` · `sale_renting_planning` ·
`sale_renting_project` · `sale_renting_sign` · `sale_management_renting` · `sale_mrp_renting` ·
`pos_sale_stock_renting` · `website_sale_renting` · `website_sale_stock_renting` ·
`l10n_din5008_sale_renting` · `spreadsheet_dashboard_sale_renting`

Los dos que importan para casi todo son **`sale_renting`** y **`sale_stock_renting`**.

### Ficheros que más se consultan

| Fichero | Qué contiene |
|---|---|
| `sale_stock_renting/models/product_product.py` | `_get_unavailable_qty`, `_get_active_rental_lines`, `_get_virtual_unavailable_qty_in_rent` |
| `sale_stock_renting/models/sale_order_line.py` | `_compute_qty_at_date` (la fórmula de disponibilidad), `_get_rented_quantities`, `write` con los movimientos de stock |
| `sale_stock_renting/models/res_company.py` | `rental_loc_id`, `padding_time`, creación de la ubicación de alquiler |
| `sale_stock_renting/models/product_template.py` | `preparation_time` |
| `sale_stock_renting/models/stock_warehouse.py` | La ruta `route_rental` y el grupo `group_rental_stock_picking` |
| `sale_renting/models/sale_order_line.py` | `is_rental`, `reservation_begin` base, `start_date`/`return_date` |
| `sale_stock_renting/tests/test_rental.py` | **Escenarios de prueba listos**: cómo montar pedidos de alquiler, aplicar existencias, simular recogidas y devoluciones |

Los tests son especialmente útiles: dan los idiomas exactos para construir escenarios
(`with_context(in_rental_app=True)`, `stock.quant` + `action_apply_inventory()`,
`line.update({'is_rental': True})`) en vez de pelearse con los campos calculados.

## Odoo Community

El código de Community (`odoo/odoo`) es público en GitHub, rama `19.0`. Sirve para `stock`,
`sale`, `account`, `uom` y todo lo que no sea Enterprise.

## Cómo verificar en la instancia lo que se lee en el código

Un campo puede existir en el código y no en la instancia, o llamarse distinto entre versiones:

```bash
python .claude/skills/odoo19-dev/scripts/odoo19.py fields product.template --filtro preparation
python .claude/skills/odoo19-dev/scripts/odoo19.py search ir.model.fields \
    '[["model","=","sale.order.line"],["name","=","product_uom_id"]]' name,ttype,store
```

Para saber **qué módulo aporta un campo** —clave para acertar con las dependencias del
manifiesto— el campo `modules` de `ir.model.fields`:

```bash
python ... search ir.model.fields \
    '[["model","=","sale.order"],["name","=","event_date"]]' name,modules,store
```

Así se descubrió que `event_date` lo aporta `rental_custom` y no el alquiler nativo.
