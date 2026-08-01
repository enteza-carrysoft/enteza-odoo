# Acciones cliente OWL en Odoo 19

Cuando lo que pide el negocio **no encaja en ninguna vista de Odoo** (list, form, kanban,
calendar, pivot), la salida es una **acción cliente**: un componente OWL propio que ocupa toda
la pantalla.

Verificado escribiendo `enteza_panel_eventos`, que funcionó a la primera en `enteza26`
(Odoo 19.0.1.3) el 2026-08-01. Ese módulo es la referencia viva: copiar de ahí.

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
