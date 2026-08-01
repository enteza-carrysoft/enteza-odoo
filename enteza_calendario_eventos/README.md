# Enteza · Calendario de eventos de alquiler

Implementa la **fase A** del PRP `.claude/PRPs/prp-modulo-prestamo-intercompania.md` (§10.1).
Se entrega como módulo independiente del préstamo entre compañías: no comparte código con él,
no necesita inventario cargado y su instalación no arrastra al módulo grande si algo falla.

## Qué hace

Añade **Alquiler → Pedidos → Calendario de eventos**: los pedidos de alquiler pivotados sobre
`event_date` en lugar de `rental_start_date`.

La diferencia no es cosmética. En los datos reales, un pedido con evento el **27/06** tiene
`rental_start_date` el **26/06**, porque el material se entrega la víspera. El calendario nativo
muestra el día de la entrega; éste muestra el día del evento.

**Los dos calendarios conviven.** El nativo responde «qué sale hoy del almacén», éste responde
«qué eventos hay el sábado». Este módulo no modifica ni sustituye la vista nativa.

## De qué vista hereda

Hereda en modo **`primary`** de `sale_renting.rental_order_view_calendar`, el calendario nativo
de alquiler (`ir.ui.view` id 1703 en `enteza26`). Al ser `primary`, crea una vista nueva y **no
altera la original**.

Verificado por RPC el 2026-08-01: en Odoo 19 no existe una vista calendario propia del alquiler
independiente de la de ventas. `sale_renting.rental_order_view_calendar` es a su vez una herencia
`primary` de `sale.view_sale_order_calendar` (id 1504) que solo cambia cuatro atributos.

Heredando del de alquiler en lugar del de ventas, este módulo se queda en lo mínimo:
`color="rental_status"`, `edit="0"` y la sustitución de `state` por `rental_status` ya vienen
dadas. Solo se cambian `date_start` a `event_date` y se anula `date_stop` (un `<attribute>`
vacío elimina el atributo), porque el evento es de un día.

**Contrapartida asumida:** cualquier cambio que Odoo haga en el calendario de alquiler llega
también a éste. Fue una decisión explícita frente a la alternativa de heredar directamente del
calendario de ventas y quedar desacoplado a cambio de más XML duplicado.

En la ventana flotante se muestra el **lugar de entrega** (`partner_shipping_id`) justo debajo
del cliente.

## Etiqueta de cada evento

Cada evento se rotula con el **nombre del cliente** y, si es distinto, el lugar de entrega
separado por `·`. El calendario nativo usa el `display_name` del registro, que en `sale.order`
es el número de pedido; el negocio quiere reconocer el evento por el cliente.

Lo aporta `event_calendar_label`, un `Char` calculado **no almacenado** en `sale.order`, al que
apunta el atributo `create_name_field` de la vista.

Dos detalles que conviene no perder:

- **No se puede apuntar `create_name_field` a `partner_id` directamente.** El título se usa tal
  cual, sin procesar (`web/static/src/views/calendar/calendar_model.js`, `normalizeRecord`), y
  un many2one llega al cliente web como `[id, nombre]`: se vería el array entero. De ahí el
  campo `Char`.
- **Basta con el atributo**, no hace falta declarar además un `<field>`: el parser añade el
  campo a los que se leen del servidor (`calendar_arch_parser.js`, `FIELD_ATTRIBUTE_NAMES`).

El título es también la **cabecera de la ventana flotante**, así que ahí ya no se ve el número
de pedido. Sigue estando a un clic, en «Ver».

> **Hoy se verá solo el nombre del cliente.** Medido por RPC el 2026-08-01: en los 1.153 pedidos
> de alquiler de `enteza26` el lugar de entrega es **siempre el mismo contacto que el cliente**,
> así que la condición anti-duplicado deja fuera la segunda parte. Aparecerá sola en cuanto se
> empiecen a informar direcciones de entrega propias, sin tocar el módulo.

## Dependencias

| Módulo | Por qué |
|---|---|
| `sale_renting` | Alquiler nativo: `is_rental_order`, `rental_status` |
| `rental_custom` | **Aporta `event_date`** en `sale.order` (verificado por RPC en `enteza26`: `ir.model.fields` id 11505) |

Sin la dependencia de `rental_custom` el orden de carga no está garantizado y la vista falla al
validar durante la instalación.

## Requisito de configuración

El lugar de entrega solo se ve con el ajuste **Ventas → Configuración → Ajustes → Presupuestos y
pedidos → «Direcciones de cliente»** activado (grupo `account.group_delivery_invoice_address`
— en Odoo 19 vive en `account`, no en `sale`).

Ya está activo en `enteza26` desde el 2026-08-01 (`scripts/enable-delivery-address.ts`). El
módulo **no lo activa ni lo desactiva**: solo lo comprueba al instalarse y deja un aviso en el
log si estuviera apagado (`hooks.py`).

Si el campo no aparece en el popover, mira primero el ajuste antes de tocar la vista.

## Instalación

El despliegue es por **`git pull`**: Xtendoo sincroniza la rama `19.0` de este repositorio
contra el addons path de `enteza26`.

1. Commit y push a `19.0`.
2. Xtendoo hace `git pull`.
3. Odoo → Aplicaciones → **Actualizar lista de aplicaciones**.
4. Quitar el filtro «Aplicaciones» (este módulo lleva `application: False` y si no, no sale),
   buscarlo e **Instalar**.

⚠️ **Que el módulo aparezca en la lista no significa que esté instalado.** `git pull` solo deja
los ficheros en el servidor. Verificar siempre:

```bash
python .claude/skills/odoo19-dev/scripts/odoo19.py search ir.module.module \
    '[["name","=","enteza_calendario_eventos"]]' name,state,latest_version,imported
```

Si tras instalar el menú no aparece, recargar con `Ctrl+F5`: Odoo cachea la barra de menús.

## Verificación tras instalar

1. **Alquiler → Pedidos → Calendario de eventos** existe y abre en vista mes.
2. Un pedido con `event_date = 27/06` y `rental_start_date = 26/06` aparece el **27**.
3. El mismo pedido sigue apareciendo el **26** en el calendario nativo de alquiler.
4. Al pinchar el evento, la ventana flotante muestra cliente y, debajo, lugar de entrega.

Corresponden a las pruebas 15 y 16 del §15 del PRP. Todavía **no están automatizadas**: no hay
entorno con `odoo-bin --test-enable` (ver limitación abajo).

## Limitación pendiente

No existe instancia de pruebas ni acceso a CLI. Hasta que Xtendoo facilite la staging, este
módulo está **validado por sintaxis, no ejecutado**.
