# Architecture

Módulo `rental_custom`, `19.0.1.15.0` → `19.0.1.16.0`. Todo aditivo.

## Models

### `sale.order` (`models/sale.py`)
- `missing_auto_validate = fields.Boolean(copy=False, readonly=True, prefetch=False)`:
  marca el pedido de faltas creado desde el pedido de alquiler. `prefetch=False` por la misma
  razón que `missing_from_rental_location` (entre cargar el código y actualizar, el prefetch
  pediría una columna que aún no existe).
- `missing_from_order_allowed = fields.Boolean(compute=...)`, no almacenado:
  `is_rental_order and state == 'sale' and not picking_ids.filtered(state not in done/cancel)`.
- `_prepare_missing_sale_order_vals(self, partner, company, origin, order_lines,
  from_rental_location)` (`@api.model`, en el pedido de ALQUILER de origen = `self`, que puede
  estar vacío): devuelve el dict de cabecera que hoy se escribe a mano en
  `stock_picking._create_missing_sale_order` (`partner_id`, `company_id`, `origin`,
  `order_line`, `rental_order_id`, `journal_id` = `company.rental_missing_journal_id`,
  `missing_from_rental_location`, `is_rental_order=False`, `event_date`). Un único sitio
  que construye la cabecera.
- `_prepare_missing_line_vals(product, qty, uom)` (`@api.model`): la línea `is_rental=False`
  sin `price_unit`. Compartida igual.
- `action_open_missing_wizard()`: `ensure_one`, rechaza con `UserError` si
  `not missing_from_order_allowed` («tiene albaranes abiertos: usa Facturar las Faltas en
  la recogida»), abre `rental.missing.wizard`.
- `_mark_rental_returned()`: para las líneas `is_rental` del pedido escribe
  `qty_delivered = product_uom_qty` y `qty_returned = product_uom_qty` donde sean menores (un
  solo `write` por línea con ambas claves). Con el ajuste apagado, el nativo crea los
  movimientos stock ↔ alquiler (neto cero) y el pedido pasa a `returned`.
- `action_confirm()`: se conserva tal cual el `return super().action_confirm()` como valor
  devuelto (AC8). Antes del `return`: guarda `res = super()...`; si `res is True`, valida
  `self.filtered('missing_auto_validate')._validate_missing_pickings()`; `return res`.
- `_validate_missing_pickings()`: `sudo()` acotado a
  `picking_ids.filtered(state not in done/cancel and picking_type_code == 'outgoing')`; por
  movimiento `quantity = product_uom_qty`, `picked = True`; `picking._action_done()`. Mensaje
  en el pedido.

### `stock.picking` (`models/stock_picking.py`)
- `_create_missing_sale_order` usa los dos helpers de arriba en vez de escribir el dict a
  mano. Mismo resultado (AC7); el resto del método no cambia.

### Nuevo `rental.missing.wizard` + `rental.missing.wizard.line` (`wizard/rental_missing_wizard.py`)
- Cabecera: `order_id` (m2o `sale.order`, required, readonly), `line_ids`.
- Línea: `sale_line_id`, `product_id` (readonly), `qty_rented` (readonly), `qty_lost_prev`
  (readonly), `qty_missing` (editable, 0).
- `default_get`/creación desde `action_open_missing_wizard`: una línea por `order_line`
  `is_rental` con `product_id.type == 'consu'`.
- `action_confirm()`:
  1. Valida `0 <= qty_missing <= qty_rented - qty_lost` (con `float_compare` y el redondeo
     de la UdM) → `UserError` y nada se crea.
  2. Si hay faltas: crea el pedido con los helpers, `missing_from_rental_location=False`
     (las unidades vuelven a Stock al marcar devuelto) y `missing_auto_validate=True`;
     suma `qty_lost`; mensajes en los dos pedidos.
  3. `order._mark_rental_returned()` (también sin faltas, con mensaje «devuelto sin faltas»).
  4. Devuelve la acción del pedido de faltas, o cierra si no hubo.

## Views
- `views/sale_order_views.xml`: en el `header` del formulario de alquiler, botón
  `action_open_missing_wizard` «Registrar faltas», `invisible="not missing_from_order_allowed"`,
  más el campo invisible.
- `wizard/rental_missing_wizard_view.xml`: formulario con la lista de líneas (solo
  `qty_missing` editable), botones «Facturar las faltas» y «Cancelar».

## Security
- `security/ir.model.access.csv`: dos filas (`rental.missing.wizard` y su línea) para
  `sales_team.group_sale_salesman`, 1,1,1,1.
- Sin reglas nuevas. Único `sudo()` nuevo: `_validate_missing_pickings`, limitado a albaranes
  de salida abiertos de pedidos con `missing_auto_validate` (decisión b del usuario).

## Manifest
- `version` → `19.0.1.16.0`; `data` añade `wizard/rental_missing_wizard_view.xml` (antes de
  `views/sale_order_views.xml`). `depends` sin cambios: `sales_team` ya llega por
  `sale_management`.

## Reports
Ninguno.

## Tours
Ninguno (no ejecutables en este hosting).

## Demo data
Ninguna.

## Documentation
- Descripción del flujo en el docstring del asistente y en la nota del commit.
- `rental_custom` no tiene `readme/`; se añade `readme/DESCRIPTION.md` breve con los dos
  caminos de faltas y cómo volver a albaranes (reactivar «Traslado de alquiler»).

## Tests (`tests/test_faltas_desde_pedido.py`, registrado en `tests/__init__.py`)
Escritos, no ejecutados. Ver test-plan.md.
