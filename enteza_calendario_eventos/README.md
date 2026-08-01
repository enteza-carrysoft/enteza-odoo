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

En la ventana flotante se muestra el **lugar de entrega** (`partner_shipping_id`) justo debajo
del cliente.

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

No hay acceso al filesystem del servidor, así que la instalación va por `base.import.module`
(mismo camino que `enteza_migration_fields`, ver `scripts/build-target-module.ts`).

⚠️ **Riesgo conocido de ese flujo:** si una vista falla al validar, Odoo hace *rollback del
módulo entero* y lo deja "importado" sin registrar nada, en silencio. Instalar primero en la
instancia de staging y comprobar que el menú aparece antes de tocar `enteza26`.

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
