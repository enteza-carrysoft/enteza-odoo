---
name: odoo19-dev
description: Conocimiento y operativa para desarrollar módulos en la instancia Odoo 19 EE de Enteza (`enteza26`). Activar al crear o modificar módulos de este repositorio, investigar modelos y campos de la 19, consultar o escribir datos por RPC, resolver dudas sobre el alquiler nativo (sale_renting / sale_stock_renting), decidir dependencias de un manifiesto, o depurar por qué un módulo no instala. Cubre el catálogo de módulos del repo y su estado real de instalación, las convenciones de la 19, el motor de disponibilidad de alquiler y dónde está el código fuente de Odoo Enterprise.
license: MIT
---

# Odoo 19 — Desarrollo de módulos para Enteza

## Propósito

Este repositorio (`enteza-odoo`, rama `19.0`) es el **directorio de addons** de la instancia
Odoo 19 Enterprise del cliente. Cada carpeta de la raíz es un módulo.

Este skill concentra lo que hace falta para desarrollar aquí sin equivocarse: cómo consultar
la instancia, cómo funciona el alquiler nativo, qué convenciones tiene la 19 y qué módulos
hay ya —que es la equivocación más cara, porque **varias cosas que parecen faltar ya están
escritas**.

> **La migración 15→19 es otro proyecto.** Vive en `E:\apps\AI\MigrarOdoo` con su propio
> skill `odoo-ops` (specs S1–S16, `id_map`, cuadre de facturas, delta). Si la pregunta es
> "cómo migro este registro de la 15", es allí; aquí no.

## Cuándo usarlo

- "Crea/modifica un módulo", "añade un campo", "haz una vista"
- "¿Cómo se llama este campo en la 19?", "¿existe este modelo?"
- "Consulta/cuenta X en la 19", "ejecuta este método"
- "¿De qué tiene que depender el manifiesto?"
- "¿Por qué no instala el módulo?"
- Cualquier duda sobre alquiler: disponibilidad, padding, albaranes, `rental_status`

## Reglas de oro

1. **`enteza26` es PRODUCCIÓN** con la contabilidad migrada y cuadrada al céntimo. Antes de
   escribir, confirmar con el usuario. `archive` antes que `unlink`.
2. **No hay instancia de pruebas ni acceso al filesystem del servidor** (hosting Xtendoo).
   No se pueden ejecutar pruebas con `odoo-bin --test-enable`. Todo lo que se entregue está
   validado por sintaxis, no por ejecución: **decirlo siempre al entregar**.
3. **Verificar contra la instancia antes de asumir.** Un campo puede llamarse distinto o no
   existir. Una consulta cuesta segundos; un manifiesto mal es una instalación rota.
4. **Mirar primero si ya existe.** Ver `references/catalogo-modulos.md`. Hay 33 módulos y
   varios resuelven cosas que parecen pendientes.
5. **Credenciales solo en `.env.local`** (no versionado). Nunca en código ni en salidas.

## Cómo consultar la instancia

Cliente JSON-RPC autónomo, solo biblioteca estándar de Python:

```bash
python .claude/skills/odoo19-dev/scripts/odoo19.py fields sale.order --filtro rental
python .claude/skills/odoo19-dev/scripts/odoo19.py search res.company '[]' id,name
python .claude/skills/odoo19-dev/scripts/odoo19.py count sale.order '[["is_rental_order","=",true]]'
python .claude/skills/odoo19-dev/scripts/odoo19.py read res.partner 176 name,vat
python .claude/skills/odoo19-dev/scripts/odoo19.py search ir.module.module '[["state","=","installed"]]' name --limit 300
```

Las escrituras (`create`, `write`, `exec`) **no hacen nada sin `--execute`**: sin el flag
muestran lo que harían. Es deliberado, porque la base es producción.

Flags: `--limit`, `--order`, `--company N` (1 Visueña, 2 Stileum — obligatorio en campos
company-dependent como el código de `account.account`), `--filtro` (solo en `fields`).

Requiere `.env.local` en la raíz del repo con `ODOO19_URL`, `ODOO19_DB`, `ODOO19_USER`,
`ODOO19_API_KEY`. Detalle en `references/instancia-y-conexion.md`.

## Cómo se instala un módulo aquí

**La vía real es `git pull`** (confirmado el 2026-08-01): Xtendoo sincroniza la rama `19.0` de
este repositorio contra el addons path de `enteza26`. Commit → push → `git pull` de Xtendoo →
Aplicaciones → Actualizar lista de aplicaciones → Instalar/Actualizar.

🔴 **Ojo:** que un módulo aparezca en la lista **no significa que esté instalado**. `git pull`
solo deja los ficheros. Comprobar siempre el `state` por RPC antes de dar por buena una
instalación. En `ir.module.module`, `imported = False` indica que llegó por filesystem.

Sigue sin haber acceso a `odoo -u`, así que **no se pueden ejecutar pruebas**.

La otra vía, zip por `base.import.module`, sigue disponible y tiene dos trampas medidas, las
dos con fallo **silencioso**:

1. **Si una vista falla al validar, Odoo hace rollback del módulo entero.** Y falla en casos
   que en un arranque normal no fallarían: una vista que referencia un campo nuevo del propio
   módulo puede no encontrarlo, porque en la instalación "en caliente" el registro ORM aún no
   lo tiene listo dentro de la misma transacción.
2. **El zip debe llevar separadores `/`.** `Compress-Archive` de PowerShell genera rutas con
   `\` y Odoo no las reconoce como estructura de directorios: el módulo queda "importado" sin
   registrar ni un fichero, sin error.

Consecuencia práctica: **entregar módulos pequeños y con pocas vistas**, y probar la
instalación antes de darla por buena. Ver `references/instancia-y-conexion.md`.

## Dónde investigar cada cosa 🔴

Elegir mal la fuente hace perder el tiempo y, peor, da respuestas falsas con apariencia de
verificadas. Son tres fuentes y no son intercambiables:

| Qué se quiere saber | Dónde mirar |
|---|---|
| **Python** de **Enterprise** (`sale_renting`, `sale_stock_renting`…) | **`https://github.com/enteza-carrysoft/odoo_enterprise_18`** (rama `18.0`) — repositorio del cliente. Entrada directa: `https://github.com/enteza-carrysoft/odoo_enterprise_18/tree/18.0/sale_renting` |
| **JS y plantillas OWL** de Enterprise, **de la 19** | El **bundle de assets de la propia instancia**: `scripts/simular_herencia_owl.py --del-bundle nombre.Plantilla`. No hace falta conformarse con la 18 para nada del cliente web |
| ORM, `base`, `stock`, `sale`, `account`, `uom`, vistas, seguridad | `https://github.com/odoo/odoo`, rama **`19.0`** (Community) |
| Si un campo/modelo existe **de verdad en esta instancia** | RPC con `odoo19.py fields ...` — manda sobre las anteriores |

⚠️ **En `odoo/odoo` no está el código de alquiler.** Es Enterprise: buscarlo ahí solo lleva a
concluir que "Odoo no trae esto", que es el error clásico documentado más abajo.

⚠️ **El repositorio del cliente es la 18, no la 19.** Para los módulos de alquiler la
diferencia es mínima y sirve para entender la mecánica, pero **lo que se lea ahí hay que
confirmarlo contra `enteza26`** antes de darlo por bueno. Los métodos privados (`_get_...`) no
se pueden llamar por RPC, así que de esos la 18 es la única referencia disponible: cuando un
desarrollo dependa de uno, **decirlo al entregar**.

Cómo consultar el repositorio sin bajárselo entero, y qué ficheros son los que más se miran:
`references/codigo-fuente-odoo.md`.

## Conocimiento crítico (detalle en references/)

- **Instancia**: `enteza26`, Odoo 19 EE, hosting Xtendoo. Dos compañías **sin jerarquía**:
  `1` Visueña de Material Plegable ("Vimaple") y `2` Stileum.
- **Productos compartidos**: 1.908 plantillas con `company_id = False`, 1.054 con
  `rent_ok = True`. **No romper esto**: que un mismo producto tenga existencias en las dos
  compañías es la premisa de todo el desarrollo de alquiler.
- **Negocio**: alquiler de material para eventos (sillas, mesas, vajilla). Muy estacional y
  concentrado en fines de semana.
- **Renombrados y cambios de la 19 que más muerden**: `product_uom`→`product_uom_id` (sólo en
  `sale.order.line`; en `stock.move` sigue siendo `product_uom`) ·
  `stock.picking.move_ids_without_package` **eliminado** (usar `move_ids`; costó un
  `AttributeError` en producción en `rental_custom` el 2026-08-08 porque el código nuevo copió
  el nombre de un método antiguo del propio repo sin volver a comprobarlo por RPC — ese código
  antiguo tampoco se había ejecutado nunca) · `tax_id`→`tax_ids` ·
  `type='product'`→`type='consu'` + `is_storable=True` · `detailed_type` y `uom_po_id`
  eliminados · `attrs`/`states` eliminados en vistas (usar `invisible="..."`, `readonly="..."`
  directos) · en `uom.uom` el factor es `relative_factor`, no `factor` · **`res.groups` ya no
  tiene `category_id`**: ahora el grupo apunta a `privilege_id` (modelo nuevo
  `res.groups.privilege`), y es el privilegio el que apunta a la `ir.module.category` — un
  `<record model="res.groups">` con `category_id` falla la instalación con `ValueError:
  Invalid field 'category_id' in 'res.groups'` (repetido dos veces ya: `rental_custom` el
  2026-08-07 y `enteza_prestamo_intercompania` el 2026-08-01, que documenta el patrón completo
  en `enteza_prestamo_intercompania/security/prestamo_security.xml`).
- **Alquiler**: `sale_renting` **y `sale_stock_renting`** están instalados. El segundo trae
  el **motor de disponibilidad completo** (`product._get_unavailable_qty`), el padding y la
  ubicación de alquiler. Antes de calcular disponibilidad a mano, leer
  `references/alquiler-en-19.md`: casi siempre ya está resuelto.
- **El material alquilado sigue siendo inventario de su compañía**: `rental_loc_id` apunta a
  una ubicación con `usage='internal'` bajo `Customers`. Por eso `qty_available` no responde
  "¿puedo alquilar esto el día 15?" — esa pregunta es temporal, no de existencias.
- **Albaranes de alquiler activos**: el grupo `sale_stock_renting.group_rental_stock_picking`
  está implicado por `base.group_user`, así que **todos** los usuarios internos lo tienen: los
  alquileres generan albaranes reales por la ruta `route_rental`.
- **Módulos propios de Enteza instalados** (verificado por RPC el 2026-08-04):
  `enteza_calendario_eventos` (`19.0.1.2.0`, vista calendario nativa pivotada en
  `event_date`), `enteza_panel_eventos` (`19.0.4.0.0` instalado; hay `19.0.5.0.0` en el
  repositorio sin desplegar — filtro de material a solo Bienes/alquilables y fuente más
  compacta) y **`enteza_prestamo_intercompania`** (`19.0.10.0.2` instalado; `19.0.10.0.3` en
  el repositorio sin desplegar). `enteza_panel_eventos` **depende de**
  `enteza_prestamo_intercompania` desde su `19.0.4.0.0` (columna «Prestados» del bloque de
  material): no se puede desinstalar el segundo sin romper el primero. Un intento anterior de
  subir el módulo de préstamo falló por un `<group expand=…>` en la vista de búsqueda: ver
  `convenciones-modulo.md` y validar siempre con `scripts/validar_vistas.py` antes de
  desplegar — ese mismo fichero tiene los gotchas que ese validador NO detecta (`@string`
  como selector de xpath, campos nuevos en `res.company` sin `prefetch=False`).
- **`rent_ok` no basta para saber si una línea es material físico.** De 1.060 productos con
  `rent_ok=True` en `enteza26`, 6 son `type == 'service'` (fianza, anticipo de cliente,
  portes, alquiler de ambiente, precio por plaza, hasta una furgoneta). Para agregados de
  "material de alquiler" filtrar **`type == 'consu'` (Bienes) Y `rent_ok`**. Detalle en
  `references/alquiler-en-19.md`.
- **Actualizar un módulo por la interfaz puede decir que ha ido bien sin haber aplicado
  nada.** Verificar siempre por RPC (`latest_version` frente al `version` del manifiesto), y
  si hay dudas, lanzar la actualización directamente por RPC — ver
  `references/instancia-y-conexion.md`.
- **Vistas calendario**: en la 19 **no existe una vista calendario propia del alquiler**.
  `sale_renting.rental_order_view_calendar` es una herencia `primary` de
  `sale.view_sale_order_calendar` que solo cambia cuatro atributos. Para un calendario nuevo,
  heredar `primary` del de alquiler sale más barato. La etiqueta de cada evento se cambia con
  `create_name_field`, que **necesita un campo de texto**: un many2one llega al cliente web
  como `[id, nombre]` y se vería el array entero.
- **Existencias: ya no están a cero.** El 2026-08-01 había **4 `stock.quant` con cantidad**
  (antes 0). La carga de inventario ha empezado. Aun así siguen siendo casi nada: un cálculo
  de disponibilidad dirá "no hay stock" de casi todo, y **no es un fallo del código**.
- **Dos almacenes** (verificado el 2026-08-01, corrige el estado anterior): `Sevilla` (`SEV`,
  compañía 1 Vimaple) y `Jerez` (`JER`, compañía 2 Stileum). Stileum **ya tiene almacén**. El
  cliente ha confirmado que **habrá más**, así que nada debe asumir uno por compañía.
- **Hay demanda futura real**: 3 pedidos de alquiler confirmados con `rental_start_date`
  posterior al 2026-08-01 (aparte de los 1.153 migrados, todos ya pasados y `returned`).
- **Direcciones de cliente**: el grupo es `account.group_delivery_invoice_address` — en la 19
  vive en `account`, **no** en `sale`. Referenciarlo con el prefijo antiguo rompe la
  instalación. Está activado desde el 2026-08-01.
- **Contexto del equipo**: arrancaron en Odoo 19 la primera semana de agosto de 2026. Desde el
  2026-08-07 **el stock se controla desde Odoo** — dejaron de llevar el almacén en paralelo
  con la aplicación externa. Priorizar que nada se mueva sin aprobación humana, y que todo sea
  reversible y trazable, por encima de la automatización.

## Ficheros de referencia

- `references/instancia-y-conexion.md` — instancia, credenciales, el cliente RPC, cómo se
  instala un módulo y las trampas del import en caliente.
- `references/convenciones-modulo.md` — estructura de un módulo, sintaxis de vistas de la 19,
  renombrados, seguridad y multi-compañía, errores frecuentes de manifiesto.
- `references/alquiler-en-19.md` — `sale_renting` y `sale_stock_renting`: motor de
  disponibilidad, padding, `reservation_begin`, `rental_status`, campos almacenados y no
  almacenados, y qué NO reimplementar.
- `references/catalogo-modulos.md` — los 33 módulos del repositorio con su estado real de
  instalación, y cuáles solapan entre sí.
- `references/owl-acciones-cliente.md` — cuándo hace falta un componente OWL propio en vez de
  una vista nativa, el esqueleto que funciona en la 19 y las trampas medidas (`toISOString`,
  caché de assets, pantalla en blanco sin log).
- `references/codigo-fuente-odoo.md` — dónde está el código de Odoo Enterprise y cómo
  consultarlo sin descargarse el repo entero.

## Ejemplos

- "¿Cómo se llama el campo de unidad de medida en la línea de pedido?" →
  `odoo19.py fields sale.order.line --filtro uom` (es `product_uom_id`).
- "¿Está instalado X?" → `odoo19.py search ir.module.module '[["name","=","X"]]' name,state`.
- "Añade un campo al pedido" → módulo nuevo o existente, `_inherit = 'sale.order'`, y
  **sin vista en el mismo módulo** si se va a instalar en caliente (ver trampa 1).
- "Calcula si hay material disponible el 15 de agosto" → **no lo calcules a mano**:
  `product._get_unavailable_qty(desde, hasta, warehouse_id=...)`. Ver
  `references/alquiler-en-19.md`.
