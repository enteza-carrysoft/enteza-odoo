# Acciones cliente OWL en Odoo 19

Cuando lo que pide el negocio **no encaja en ninguna vista de Odoo** (list, form, kanban,
calendar, pivot), la salida es una **acción cliente**: un componente OWL propio que ocupa toda
la pantalla.

Verificado escribiendo `enteza_panel_eventos`, que funcionó a la primera en `enteza26`
(Odoo 19.0.1.3) el 2026-08-01. Ese módulo es la referencia viva: copiar de ahí.

> Para **extender un widget que ya existe** en vez de crear una pantalla nueva, ir al final:
> [Extender un widget nativo](#extender-un-widget-nativo-el-caso-de-qty_at_date).

## Cuándo hace falta y cuándo no

Antes de escribir JavaScript, descartar lo nativo: es más barato de mantener y no se rompe al
actualizar Odoo. Una acción cliente se justifica cuando hacen falta **varios bloques
sincronizados en una sola pantalla** o una interacción que ninguna vista da.

El caso real: el cliente quería calendario del mes + material del día + pedidos del día, los
tres a la vez y sincronizados al pinchar un día. No hay vista de Odoo que haga eso.

## El esqueleto que funciona

### 1. Manifiesto

```python
'assets': {
    'web.assets_backend': [
        'mi_modulo/static/src/**/*',
    ],
},
```

El glob recoge `.js`, `.xml` y `.scss` de golpe. No hay que listarlos uno a uno.

### 2. El componente — `static/src/mi_panel.js`

```js
/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";

export class MiPanel extends Component {
    static template = "mi_modulo.MiPanel";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ /* ... */ });
        onWillStart(async () => { await this.cargar(); });
    }
}

registry.category("actions").add("mi_modulo.mi_panel", MiPanel);
```

`standardActionServiceProps` está en `@web/webclient/actions/action_service` y define
`action`, `actionId`, `className`, `globalState`, `state`, `resId` y `updateActionState`.
**Sin `static props` el componente falla la validación** en modo desarrollo.

### 3. La plantilla — `static/src/mi_panel.xml`

```xml
<templates xml:space="preserve">
    <t t-name="mi_modulo.MiPanel">
        <div class="o_mi_panel o_action d-flex flex-column h-100">...</div>
    </t>
</templates>
```

El `t-name` **tiene que coincidir exactamente** con `static template` del JS.

### 4. La acción y el menú — `views/...xml`

```xml
<record id="action_mi_panel" model="ir.actions.client">
    <field name="name">Mi panel</field>
    <field name="tag">mi_modulo.mi_panel</field>
</record>

<menuitem id="menu_mi_panel" name="Mi panel"
          parent="sale_renting.rental_order_menu"
          action="action_mi_panel" sequence="16"/>
```

El `tag` **tiene que coincidir** con la clave registrada en `registry.category("actions")`.

## Servir datos desde Python

Métodos `@api.model` en un modelo, llamados desde el JS con
`this.orm.call("sale.order", "mi_metodo", [arg1, arg2])`.

**Agregar en Python sobre `search_read` en vez de usar `_read_group`** cuando el volumen es
pequeño: la firma de `_read_group` cambió entre versiones y aquí no se puede probar nada. Con
decenas o cientos de registros la diferencia de rendimiento es irrelevante y el código no
depende de una API incierta. Si el volumen crece, se cambia dentro del método sin tocar el JS.

Para las etiquetas de un campo `selection`, usar **`fields_get`** y no
`_fields['campo'].selection`: es API pública, viene traducida al idioma del usuario y aguanta
que otro módulo convierta la selección en un callable.

```python
etiquetas = dict(self.env['sale.order'].fields_get(['rental_status'])['rental_status']['selection'])
```

Formatear importes en Python con `formatLang(self.env, importe, currency_obj=...)` reduce la
superficie de JS que no se puede probar.

Las horas, a la zona del usuario con `fields.Datetime.context_timestamp(self, momento)`. Los
`Datetime` de Odoo están en UTC y mostrarlos crudos da una hora equivocada.

## Trampas medidas

### `toISOString()` cambia el día

Convierte a UTC. Al este de Greenwich, a partir de cierta hora devuelve **el día anterior**:
el panel mostraría los pedidos del día equivocado. Construir la clave a mano:

```js
function aClaveDia(fecha) {
    const mes = String(fecha.getMonth() + 1).padStart(2, "0");
    const dia = String(fecha.getDate()).padStart(2, "0");
    return `${fecha.getFullYear()}-${mes}-${dia}`;
}
```

### `getDay()` empieza en domingo

Para una rejilla que empieza en lunes: `(fecha.getDay() + 6) % 7`.

### Un error de JS deja la pantalla en blanco

**Sin rastro en el log del servidor.** Se diagnostica solo en la consola del navegador (F12).
No se puede depurar por RPC. Al entregar una acción cliente, decirlo explícitamente y contar
con una ronda de ajuste.

### 🔴 Un informe con `data` pierde los `docids`

Medido leyendo `web/static/src/webclient/actions/reports/utils.js` de la 19 al añadir el parte
del día a `enteza_panel_eventos` (2026-08-03).

Cuando una acción cliente lanza un informe con `report_action(registros, data={...})`, es
tentador dar por hecho que `_get_report_values` recibirá esos `docids`. **No los recibe.**
`getReportUrl` monta la URL de dos formas incompatibles:

```js
if (action.data && JSON.stringify(action.data) !== "{}") {
    url += `?options=${options}&context=${context}`;   // ← sin docids en la ruta
} else {
    url += `/${actionContext.active_ids.join(",")}`;   // ← con docids
}
```

Es decir: **en cuanto `data` no está vacío, los ids desaparecen de la ruta** y el controlador
llama a `_get_report_values(None, data)`. El síntoma es un informe que sale en blanco o con
solo las cabeceras, sin ningún error.

Salidas, de mejor a peor:

1. **Recalcular el conjunto desde el propio `data`** (el día, el filtro…). Es lo que hace el
   parte del día: el informe queda determinado por los mismos parámetros que la pantalla, así
   que no pueden discrepar.
2. Recuperarlos de `data['context']['active_ids']`, que sí sigue viajando.

### El navegador cachea el bundle de assets

Tras instalar o actualizar un módulo con JS o SCSS hace falta **`Ctrl+F5`**. Sin eso se puede
estar viendo la versión anterior y perseguir un fallo que ya no existe.

## Comprobar antes de escribir

El código del cliente web es público y **leerlo gana a suponer**. Rama `19.0` de `odoo/odoo`,
bajo `addons/web/static/src/`. Los dos que más se consultan al hacer esto:

| Fichero | Para qué |
|---|---|
| `webclient/actions/action_service.js` | `standardActionServiceProps` |
| `views/calendar/calendar_arch_parser.js` | Atributos que admite `<calendar>` |
| `views/calendar/calendar_model.js` | Cómo se construye el título de un evento |

---

## Extender un widget nativo (el caso de `qty_at_date`)

Verificado escribiendo el aviso de préstamo del widget de disponibilidad en
`enteza_prestamo_intercompania` (2026-08-02).

**Casi siempre sale más barato extender que crear.** El widget nativo ya trae la posición en
la vista, el icono, el popover y las traducciones; añadirle un bloque son tres ficheros
pequeños y se rompe mucho menos al actualizar Odoo.

### El patrón, en tres piezas

1. **Campos calculados no almacenados** en el modelo, con prefijo propio.
2. **`fieldDependencies`** en el descriptor del widget. Sin esto el cliente web **no se trae
   los campos** y la plantilla los ve vacíos, sin ningún error que lo explique.
3. **`t-inherit` de la plantilla** con un `xpath`.

```js
import { patch } from "@web/core/utils/patch";
import { qtyAtDateWidget } from "@sale_stock/widgets/qty_at_date_widget";

patch(qtyAtDateWidget, {
    fieldDependencies: [
        ...qtyAtDateWidget.fieldDependencies,   // 🔴 arrastrar las que ya había
        { name: "mi_campo", type: "float" },
    ],
});
```

🔴 **`patch` sustituye la propiedad entera.** Escribir la lista a pelo borra las
dependencias que puso el módulo anterior y rompe su widget sin tocar una línea suya —
`sale_stock_renting`, por ejemplo, mete ahí `start_date` y `return_date`, de los que dependen
las fechas que muestra su propio popover. El `spread` funciona porque el fichero propio carga
**después**, que lo garantiza la dependencia del manifiesto.

### 🔴 OWL exige raíz única

Una plantilla de componente tiene que tener **un solo elemento raíz**. Si la plantilla base ya
tiene dos hermanos es porque son `t-if`/`t-else` y solo se pinta uno: **añadir un tercer
hermano rompe el componente**, y meter algo *entre* los dos también, porque `t-else` tiene que
ser el hermano inmediato del `t-if`. Lo que hay que hacer es insertar **dentro** de la rama que
interesa.

### Cómo leer una plantilla de Enterprise de la 19 🔴

`sale_renting`, `sale_stock_renting`, `web_gantt`… son Enterprise y su código de la 19 no es
público. **Pero la instancia lo sirve**: los bundles de assets llevan las plantillas dentro.
Es la única forma verificada de leer código Enterprise de la 19, y evita tener que dar por
buena la 18.

```bash
python .claude/skills/odoo19-dev/scripts/simular_herencia_owl.py \
    --base sale_stock.QtyAtDatePopover \
    --del-bundle sale_stock_renting.QtyAtDatePopover \
    mi_modulo/static/src/widgets/mi_widget.xml
```

Ese script baja el bundle, saca las plantillas por su `t-name`, **aplica la cadena de
herencia** y dice si el `xpath` encuentra su nodo y si el componente queda con raíz única.
Merece la pena por lo que cuesta equivocarse: **un `t-inherit` que no encuentra su `xpath`
tumba el bundle entero**, y el síntoma es una pantalla en blanco sin nada en el log.

Dos detalles del bundle que cuestan un rato averiguar:

- La URL lleva un **hash de versión que cambia** cada vez que Odoo regenera los assets: hay
  que preguntarla por RPC (`ir.attachment`, campo `url`), no fijarla.
- Hay que mandar la cabecera **`X-Odoo-Database`**. Sin ella el servidor responde 404
  «No database is selected», que parece que la URL está mal.

Diferencia real encontrada entre la 18 y la 19 en esa plantilla: `product_uom` pasó a
**`product_uom_id`**. Poco, pero suficiente para pintar `undefined` en pantalla.
