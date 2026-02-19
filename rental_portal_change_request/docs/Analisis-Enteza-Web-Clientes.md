# Prompt de desarrollo para Odoo 19: Portal privado de alquiler con solicitudes de cambio post-confirmación

## Resumen ejecutivo

Eres un **desarrollador senior/IA coder** especializado en Odoo Enterprise y sistemas de alquiler con control de disponibilidad. Quiero que implementes, en **Odoo 19 Enterprise autoalojado en nuestro VPS**, un **portal privado** (solo clientes a los que damos acceso) donde el cliente pueda:

- Consultar pedidos de alquiler (muchos con **80+ líneas**).
- **Solicitar cambios** sobre un pedido ya **confirmado** (estado “Sales Order”) mediante un flujo de **Change Request + Revisión** (enmienda), en lugar de editar directamente el pedido confirmado.
- Editar esa revisión en una UI tipo **tabla minimalista** (OWL) con **alta productividad** (quick add por SKU, búsqueda, agrupación por familias, paginación/lazy load).
- Enviar la solicitud; y que nuestro equipo comercial reciba una **notificación inmediata** (chatter + actividad + opcional email) con trazabilidad completa.

La implementación debe priorizar operaciones **atómicas server-side** (un solo método transaccional para aplicar cambios) porque, en Odoo, las operaciones relacionadas con reservas y consistencia deben ejecutarse en una única transacción para evitar inconsistencias por concurrencia. citeturn6view0

La UI será privada (sin SEO) y muy interactiva, por lo que OWL en portal es apropiado cuando necesitamos interactividad fuerte y no nos importa indexación. citeturn13view0

**Salida requerida de tu trabajo (obligatorio):**
1) Un **repo git** (skeleton) con árbol de archivos y breve explicación de cada file,  
2) Stubs completos de los archivos críticos (models, controllers, atomic methods, OWL),  
3) Ejemplos de APIs JSON (portal y JSON-2 opcional) + tests,  
4) Scripts de migración/upgrade del módulo y notas de mantenimiento.

## Contexto y objetivos del producto

Soy una empresa de alquiler para eventos/bodas. En nuestro flujo:

- El cliente planifica con antelación y puede pedir cambios muchas veces.
- **Reservamos stock cuando se confirma el presupuesto** (es decir, cuando el presupuesto se convierte en pedido confirmado). En Odoo, al confirmar un presupuesto se convierte oficialmente en un pedido de venta. citeturn15view0
- El eCommerce estándar no está pensado para que el cliente edite un pedido confirmado libremente; además existe el ajuste “Lock Confirmed Sales” que bloquea ediciones en pedidos confirmados y es frecuente tenerlo habilitado. citeturn15view0
- El **pago online debe estar desactivado**: el pago es posterior y fuera de la web.
- La **fecha de recogida** coincide con el **último día del periodo de alquiler** (pickup = rental_end).

Objetivos funcionales principales:

- Portal “Mis Alquileres” con lista y detalle de pedidos.
- En cada pedido confirmado, botón **“Solicitar cambios”** → crea una **solicitud de cambio** y una **revisión** editable.
- El cliente edita la revisión con una tabla compacta (no cards gigantes), pudiendo:
  - cambiar cantidades,
  - añadir/eliminar líneas,
  - añadir notas por línea,
  - encontrar productos por SKU (default_code), nombre y filtros,
  - ver disponibilidad estimada durante la edición y disponibilidad definitiva antes de enviar.
- Enviar solicitud:
  - se bloquea para el cliente (solo lectura),
  - se notifica automáticamente a comerciales,
  - queda registro/auditoría completa.
- El comercial puede aprobar, rechazar o solicitar ajustes.
- Al aprobar: aplicar la revisión al pedido confirmado de forma **atómica**, recalcular precios/rental, y recomputar reservas según estrategia.

## Restricciones no funcionales y condiciones del entorno

Entorno y hosting:

- Odoo 19 Enterprise desplegado en **VPS (on‑premise)**.
- Debe estar desplegado detrás de reverse proxy con **HTTPS**, y en ese caso Odoo recomienda habilitar `proxy_mode` y terminar TLS en el proxy. citeturn10view2
- En instalaciones Enterprise por código, el path de `enterprise` debe ir antes en `addons-path` para que se cargue correctamente. citeturn10view1
- Si hay multi‑DB, debemos configurar `dbfilter` para que website/portal resuelva la DB correcta. citeturn3view3

Módulos Odoo requeridos (funcionales) y dependencias:

- `website`, `portal` (portal privado) citeturn2search7
- `sale` / `sale_management` (ventas y confirmación de presupuestos) citeturn15view0
- `sale_rental` (Rental) con “Rental Transfers” si usáis movimientos de stock en alquiler. citeturn14view0
- `stock` (Inventory) para reservas y operación types. citeturn14view3
- `website_sale` (si mantenemos catálogo/selector sobre eCommerce estándar; aunque sin checkout/pago). Odoo indica que shop/product/checkout se generan cuando se instala `website_sale`. citeturn13view1
- `mail` (chatter/seguidores/actividades); la integración por herencia `mail.thread` es la forma estándar. citeturn5view1

Rendimiento y escalabilidad mínima:

- Catálogo objetivo: **4.000+ SKUs**.
- Pedidos objetivo: **80+ líneas** editables con UX fluida.
- Evitar N+1 y bucles con `search()` por iteración; Odoo cachea y hace prefetch si trabajas con recordsets correctamente. citeturn5view2
- Implementar índices para búsquedas frecuentes (SKU/código/nombre) usando mecanismos soportados por Odoo (declaración de `Index`/`UniqueIndex`) y, opcionalmente, trigram en PostgreSQL para acelerar búsquedas tipo `ILIKE`/similaridad. citeturn10view3turn8search1
- Si habilitas trigram, debes instalar extensión en DB con `CREATE EXTENSION`. citeturn8search8

Seguridad:

- Todo acceso en portal debe estar protegido por login (`auth="user"`), ejecutando con permisos del usuario autenticado. citeturn5view3
- Record rules deben asegurar que un portal user solo ve/edita lo suyo; las reglas se evalúan por registro y son “default-allow” (si hay rights y no aplica ninguna regla, se concede). citeturn3view2
- Seguridad en módulos: definir `ir.model.access.csv`, grupos y record rules en ficheros de `security/` siguiendo estructura estándar. citeturn2search15

## Diseño funcional y modelo de datos

Quiero que implementes el patrón **“Change Request + Revision”**:

- El pedido confirmado **no** es editable directamente por el cliente.
- Cada “solicitud de cambio” crea un **pedido revisión** (borrador) que el cliente edita.
- Un comercial aprueba y el sistema aplica la revisión al pedido confirmado en un único método atómico.

### Cambios en `sale.order`

Añade estos campos (prefijo `x_` o sin prefijo pero con el namespace del módulo; decide una convención y úsala siempre):

- `x_parent_order_id`: M2O a `sale.order` (pedido original). Solo relleno en pedidos “revisión”.
- `x_revision_ids`: O2M inverso.
- `x_active_change_request_id`: M2O a `rental.change_request` (si hay una solicitud activa).
- `x_rental_pickup_date`: `Datetime` computed/stored = `rental_end` (fin del periodo). Debe ser editable por staff si en un futuro se necesita; por defecto igual al fin del periodo.

Índices recomendados (usa `models.Index` donde aplique):

- Índice en `x_parent_order_id`
- Índice compuesto (`partner_id`, `state`) para filtrar pedidos en portal
- Índice (opcional) en `write_date` para validación de concurrencia
Odoo permite declarar `Index` y `UniqueIndex` como atributos de modelo. citeturn10view3

> Nota: no reinventes la lógica de “rental period”; Odoo ya usa un rango (start/end) y recalcula precios con “Update Rental Prices”. citeturn14view1

### Nuevo modelo `rental.change_request`

Crea modelo: `rental.change_request` con estas propiedades:

- `_inherit = ['mail.thread', 'mail.activity.mixin']` para chatter + actividades. citeturn5view1turn4search9
- Campos principales:
  - `name`: secuencia (CR-YYYY-XXXXX)
  - `order_id`: M2O a `sale.order` (pedido confirmado objetivo)
  - `revision_order_id`: M2O a `sale.order` (pedido borrador revisión)
  - `partner_id`: related a `order_id.partner_id` (store)
  - `requested_by_user_id`: M2O a `res.users` (portal user)
  - `state`: `draft` | `editing` | `submitted` | `approved` | `rejected` | `cancelled` | `applied`
  - `customer_message`: Text (mensaje del cliente)
  - `internal_note`: Text (solo staff)
  - `expected_order_write_date`: Datetime (concurrency token)
  - `expected_revision_write_date`: Datetime (concurrency token)
  - `diff_json`: JSON/Text (snapshot del diff calculado en submit; útil para auditoría)
  - `submitted_at`, `decided_at`, `decided_by`, etc.
- Restricciones:
  - Solo **1 change_request activa** (`draft|editing|submitted`) por `order_id`.
  - Solo permitir change_request si `order_id.state == 'sale'` (confirmado) y no en estado bloqueado por condiciones operativas que definas (p. ej., picking done).

### Nuevo modelo `rental.change_request.line`

Crea `rental.change_request.line` para trazabilidad explícita del cambio (aunque también exista `revision_order_id`):

- `change_request_id`: M2O
- `product_id`: M2O (`product.product`)
- `uom_id`
- `qty`: Float
- `operation`: `add|update|remove`
- `original_line_id`: M2O `sale.order.line` (si existe)
- `revision_line_id`: M2O `sale.order.line` (si existe)
- `note`: Char/Text
- `sequence`: Int

Justificación: necesito auditoría completa, diffs claros para comercial, y poder reconstruir la evolución.

### Estrategia de reservas y disponibilidad

Requisitos:

- Presupuestos (draft) → “soft-hold”: **no reservan** y la disponibilidad mostrada al cliente es orientativa.
- Pedido confirmado (`sale`) → **reservar** según “At Confirmation” (o configuración equivalente en Operation Types). Odoo define métodos de reserva y “At Confirmation” reserva al confirmar si hay stock disponible. citeturn14view3turn1search7
- Aprobación de cambios → recomputar reservas y disponibilidad:
  - cancelar/ajustar reservas previas si cambian cantidades,
  - respetar “padding time”, “rental transfers”, “unavailability days” y duración mínima configuradas. citeturn14view0

Importante: como el pago web está desactivado, el pedido puede requerir confirmación manual para que se reserve stock; Odoo avisa que si se paga “al recoger” o por transferencia, la cotización puede no confirmarse y el stock no se reserva hasta confirmar manualmente. citeturn15view1

## Arquitectura técnica y APIs atómicas

### Principio arquitectónico

Toda operación que afecte a coherencia (líneas, pricing, reservas, movimientos, estado) debe ejecutarse en **métodos server-side atómicos**. Odoo documenta que encadenar múltiples llamadas sin una sola transacción es peligroso en reservas/pagos, y recomienda una única llamada a un método que realice todo. citeturn6view0

Aunque el portal llame por JSON-RPC interno, quiero el mismo principio: “un botón crítico = un método atómico”.

### Métodos obligatorios y nombres exactos

Implementa estos métodos con firmas y semántica estrictas:

#### Modelo: `rental.change_request`

- `@api.model`
  - `start_from_order_atomic(order_id: int) -> dict`
    - Crea `rental.change_request` y `revision_order_id` (copia del pedido confirmado a un pedido revisión en draft).
    - Guarda `expected_order_write_date` del pedido original.
    - Devuelve payload inicial para UI.

- `patch_revision_atomic(change_request_id: int, patch: dict, expected_revision_write_date: str|None) -> dict`
  - Aplica cambios incrementales en la revisión (add/update/remove líneas, notas).
  - Debe devolver:
    - `revision_write_date` actualizado,
    - resumen de líneas,
    - totales estimados,
    - resultado de “availability check” (al menos por producto/cantidad).

- `submit_atomic(change_request_id: int, customer_message: str, expected_revision_write_date: str) -> dict`
  - Cambia a `submitted`, calcula `diff_json` y crea notificaciones.

- `approve_atomic(change_request_id: int, approver_user_id: int|None = None) -> dict`
  - Uso interno (no portal). Marca `approved` y llama a `apply_revision_atomic(...)`.

- `reject_atomic(change_request_id: int, reason: str) -> dict`
  - Marca `rejected`, notifica al cliente.

- `apply_revision_atomic(change_request_id: int, expected_order_write_date: str, expected_revision_write_date: str) -> dict`
  - **Método principal**: bajo lock, aplica la revisión al pedido confirmado.
  - Debe ser **idempotente** (si ya aplicado, devolver estado consistente).
  - Debe recalcular:
    - precios de alquiler si cambia periodo o líneas (usar wrapper interno si hace falta, pero que el método exista),
    - reservas/movimientos de stock según estado operativo.

#### Modelo: `sale.order` (helpers)

- `action_portal_open_change_request(self) -> dict`
  - Valida que el usuario tenga derecho portal sobre el pedido.
  - Retorna URL/IDs para abrir editor.

### Controladores y endpoints exactos

Usa `odoo.http` controllers para:

#### Páginas (HTML)

- `GET /my/rentals`
- `GET /my/rentals/<int:order_id>`
- `GET /my/rentals/<int:order_id>/change-request/<int:change_request_id>`

Deben ser `auth='user'` y respetar record rules. citeturn5view3

#### RPC desde OWL (JSON-RPC sobre HTTP)

Implementa rutas `type='jsonrpc'` (Odoo 19 las documenta como `jsonrpc` frente a `http`). citeturn5view3turn11search0

- `POST /rental_portal/jsonrpc/change_request/start`
- `POST /rental_portal/jsonrpc/change_request/patch`
- `POST /rental_portal/jsonrpc/change_request/submit`
- `POST /rental_portal/jsonrpc/change_request/cancel`

Notas de seguridad de controllers:
- Define `auth='user'` (portal) y evita `sudo()` salvo para lecturas estrictamente necesarias y siempre tras validar ownership. citeturn5view3turn3view2
- Gestiona CSRF explícitamente: Odoo permite `csrf` y especifica el comportamiento por tipo de controller (`http` vs `jsonrpc`). citeturn5view3

### Esquemas JSON requeridos

#### Esquema: `start`

**Request (params):**
```json
{
  "order_id": 123
}
```

**Response (result):**
```json
{
  "change_request": {
    "id": 55,
    "name": "CR-2026-00055",
    "state": "editing",
    "order_id": 123,
    "revision_order_id": 987,
    "expected_order_write_date": "2026-02-19 10:12:33"
  },
  "order": {
    "id": 123,
    "name": "S00045",
    "partner_id": 777,
    "rental_start": "2026-08-10 10:00:00",
    "rental_end": "2026-08-11 12:00:00",
    "pickup_date": "2026-08-11 12:00:00"
  },
  "revision": {
    "id": 987,
    "write_date": "2026-02-19 10:12:40",
    "lines": [
      {
        "line_id": 1,
        "product_id": 1001,
        "sku": "VJ-PLATO-27",
        "name": "Plato llano 27cm",
        "qty": 120,
        "uom": "u",
        "note": "",
        "availability": {"status": "ok", "available_qty": 9999}
      }
    ],
    "totals": {"untaxed": 0.0, "tax": 0.0, "total": 0.0}
  }
}
```

#### Esquema: `patch`

**Request (params):**
```json
{
  "change_request_id": 55,
  "expected_revision_write_date": "2026-02-19 10:12:40",
  "patch": {
    "actions": [
      {"op": "update_qty", "line_id": 1, "qty": 140},
      {"op": "add_line", "product_id": 2002, "qty": 30, "note": "Zona ceremonia"},
      {"op": "remove_line", "line_id": 9}
    ]
  }
}
```

**Response (result):**
```json
{
  "ok": true,
  "revision_write_date": "2026-02-19 10:14:02",
  "lines_updated": [1, 42],
  "availability_summary": {
    "status": "warning",
    "conflicts": [
      {"product_id": 2002, "requested": 30, "available": 12}
    ]
  },
  "totals": {"untaxed": 0.0, "tax": 0.0, "total": 0.0}
}
```

#### Esquema: `apply_revision_atomic` (interno / JSON-2 opcional)

Si se usa vía **External JSON-2 API** (opcional para servicios internos), la ruta debe ser `/json/2/<model>/<method>` y autenticación por `Authorization: bearer <API_KEY>`. citeturn3view0turn6view0

Ejemplo de body JSON-2 (sin envolver en JSON-RPC):
```json
{
  "ids": [55],
  "expected_order_write_date": "2026-02-19 10:12:33",
  "expected_revision_write_date": "2026-02-19 10:14:02"
}
```

### Concurrencia, locks y manejo transaccional

Requisitos duros:

- Debes implementar **optimistic concurrency**:
  - `expected_order_write_date` debe igualar `order.write_date` en el momento de aplicar; si no, devolver error “order_changed”.
- Debes implementar **row lock** al aplicar:
  - SQL: `SELECT id FROM sale_order WHERE id=%s FOR UPDATE NOWAIT;`
- La aplicación debe ejecutarse dentro de un contexto seguro:
  - Usa `env.cr.savepoint()` para rollback parcial y lanza `UserError` consistente en conflictos.
- Debes garantizar que si hay dos comerciales intentando aprobar a la vez, solo uno gana y el otro recibe conflicto limpio.

## Requisitos de UI en portal con OWL/QWeb y reglas UX

### Enfoque UI

Como el portal es privado y necesitamos interactividad fuerte, usa OWL en portal/website: Odoo especifica que OWL se recomienda cuando no importa SEO (portal privado) y cuando se necesita interactividad en tiempo real. citeturn13view0

Implementación permitida (elige una y justifica):

- **Opción preferida**: “standalone OWL application” montada en una página del portal (más control de layout y estado). Odoo documenta los elementos necesarios: componente root, bundle de assets, vista QWeb que carga assets y controller que renderiza. citeturn12view0  
  - Debes incluir CSRF token y session_info en el global `odoo` tal y como recomienda el tutorial. citeturn12view1
- Alternativa: `<owl-component>` embebido en una plantilla portal con `public_components` registry. citeturn13view0

### Componentes OWL obligatorios (nombres y contratos)

Define como mínimo:

- `RentalChangeRequestApp` (root)
  - **props**:
    - `orderId: Number`
    - `changeRequestId: Number`
    - `csrfToken: String`
    - `sessionInfo: Object`
  - **events internos**: `loaded`, `error`, `submitted`

- `OrderLinesTable`
  - **props**:
    - `lines: Array`
    - `groupBy: 'category'|'none'`
    - `readonly: Boolean`
  - **events**:
    - `lineQtyChanged({lineId, qty})`
    - `lineRemoved({lineId})`
    - `lineNoteChanged({lineId, note})`

- `QuickAddBySKU`
  - **props**: `placeholder`, `disabled`
  - **events**:
    - `addRequested({skuOrQuery, qty})`

- `CatalogSidePanel`
  - filtros + búsqueda + resultados paginados
  - debe soportar “search-within-filters” para listas largas, sin congelar la UI.

### Reglas UX obligatorias

- **No checkout / no pago**:
  - El portal y el flujo de cambios NO deben mostrar pago.
  - Si mantienes `website_sale`, debes ocultar/inhabilitar checkout y cualquier botón de pago. Odoo documenta que shop/product/checkout se generan con `website_sale` y se modifican vía plantillas standard con XPath/SCSS. citeturn13view1turn1search17
- Flujo “request-change”:
  - Pedido confirmado: botón “Solicitar cambios”.
  - Editor: “Guardar borrador”, “Enviar cambios”.
  - Tras submit: solo lectura, etiqueta de estado, historial visible.
- Notificaciones y auditoría:
  - Cada submit debe escribir en chatter del pedido y del change_request; Odoo indica que heredar `mail.thread` habilita mensajes y notificaciones a followers. citeturn5view1
  - Crear actividad para el comercial (y/o para un grupo de comerciales); actividades se gestionan desde el chatter. citeturn4search9

### Rendimiento UI y backend para 4.000+ SKUs

Backend:

- Para búsquedas, evita `ilike '%term%'` sin índices. Si implementas fuzzy/search-as-you-type:
  - Habilita `pg_trgm` y crea índices GIN `gin_trgm_ops` en campos de búsqueda (p. ej. SKU y nombre). PostgreSQL documenta que `pg_trgm` soporta búsquedas rápidas para `LIKE/ILIKE` y similaridad con índices GiST/GIN. citeturn8search1turn0search3
  - Documenta claramente el paso de `CREATE EXTENSION`. citeturn8search8
- Usa recordsets y prefetch (o `search_fetch/fetch`) para evitar explotar queries y latencia; Odoo explica cache/prefetch y cómo reducir queries masivas. citeturn5view2turn8search4

Frontend:

- Paginación/lazy load en resultados de catálogo.
- Virtualización (si la implementas) solo si es estable con Odoo assets y no rompe accesibilidad.
- Para 80 líneas, la tabla debe ser editable con teclado sin re-render global en cada input.

## Calidad, pruebas, despliegue y criterios de aceptación

### Tests obligatorios

Quiero tests reales Odoo:

- **Unit tests Python** (`TransactionCase`) para:
  - creación de change_request,
  - constraints (1 activo por pedido),
  - `apply_revision_atomic` (casos OK y conflictos),
  - reglas de seguridad (portal no puede tocar pedidos ajenos).
- **HTTP tests** (`HttpCase`) para flujo portal:
  - login portal,
  - start/patch/submit,
  - verificación de estados y respuestas.

Odoo documenta que los tests se ejecutan al instalar/actualizar módulos con `--test-enable`, y que se usan `TransactionCase`/`HttpCase` con tags. citeturn3view1turn2search4

### Edge cases que debes cubrir

- Conflicto por concurrencia:
  - el pedido confirmado cambió en backend mientras el cliente editaba.
- Conflicto por disponibilidad:
  - al aprobar, ya no hay stock suficiente (otro pedido lo reservó).
- Solicitud múltiple:
  - cliente intenta crear 2 change_requests activos.
- Cambios cerca de logística:
  - existen transfers/pickings creados (pero no hechos) → comportamiento definido (recrear/ajustar) o bloquear.
- Cancelaciones:
  - cliente cancela solicitud en borrador,
  - comercial rechaza con motivo,
  - el pedido original se cancela: invalidar solicitudes vinculadas.

### Despliegue en VPS

Incluye instrucciones para desplegar el/los módulos como custom addons:

- Añadir ruta del repo a `addons-path` (respetando que `enterprise` vaya antes, si aplica). citeturn10view1
- Actualizar módulo con `odoo-bin -u <module_name> -d <db>` y reinicio de servicio (systemd si aplica).
- Configurar HTTPS vía reverse proxy y `proxy_mode = True` si hay proxy. citeturn10view2
- Recomendaciones de `dbfilter` si hay varias DB o varios dominios. citeturn3view3

### Criterios de aceptación

Considero el proyecto “Done” si:

- Un cliente portal autorizado ve su lista de pedidos de alquiler.
- En un pedido confirmado puede arrancar una solicitud de cambio y editarla.
- La edición soporta 80+ líneas de manera usable (tabla compacta).
- Hay quick add por SKU, búsqueda y filtros con paginación.
- No existe flujo de pago/checkout en web para este proceso.
- Al enviar solicitud, se crea chatter + actividad para comercial.
- El comercial aprueba y el sistema aplica cambios de forma atómica, con recomputación de precios y reservas, sin corrupción de datos.
- Existe trazabilidad (auditoría) completa de qué cambió, quién y cuándo.
- Hay suite de tests ejecutable y documentada.

### Checklist de supuestos que debes preguntarme antes de cerrar implementación

Antes de asumir nada, devuélveme una lista corta confirmable (sí/no o valor) con:

- SO del VPS (Ubuntu/Fedora/otro) y método de instalación (paquete vs source).
- Versión PostgreSQL y si tenemos permisos para `CREATE EXTENSION pg_trgm`.
- Si usamos `website_sale` hoy o si el selector será totalmente custom (standalone OWL).
- Si hay multi-compañía / multi-almacén y qué warehouse usar para disponibilidad.
- Si “Rental Transfers” está activado actualmente. citeturn14view0
- Política exacta si ya hay pickings en curso: ¿bloquear cambios o permitir solo aumentos/añadidos?
- Sistema de notificación preferido: solo chatter/actividad, o también email (SMTP/catchall configurado).
- Necesidad de integraciones externas (Slack/Teams) y si se usarán API keys (JSON-2) para bots internos. citeturn3view0turn6view0