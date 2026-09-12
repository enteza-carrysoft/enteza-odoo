# Enteza - Descuento en factura — Odoo 19

Añade a la factura de cliente el mismo botón "Descuento" que ya existe en el pedido de
venta, pero **no es una extensión de ese wizard**: Odoo no tiene ninguno equivalente para
`account.move` (verificado contra `addons/account/wizard` de Odoo 19 Community), así que
este módulo reimplementa solo la variante que ha pedido el cliente — aplicar un porcentaje
a la columna Descuento de **todas** las líneas de la factura de una vez.

## Funcionamiento

- Botón **Descuento** en la ficha de la factura, entre las líneas y los totales (mismo
  sitio que en el pedido de venta).
- Solo visible en **facturas de cliente** (`out_invoice`) y sus **abonos** (`out_refund`),
  y solo mientras la factura está en **borrador** — una vez validada, las líneas contables
  ya no se tocan así.
- Abre un wizard con un único campo de porcentaje. Al pulsar "Aplicar", escribe ese
  porcentaje en el campo `discount` de todas las líneas de factura que no sean una sección
  o una nota.
- No toca las facturas de proveedor ni los asientos manuales — se puede ampliar más
  adelante si hace falta, cambiando la condición `invisible` del botón.

## Instalación

1. `git pull` en la instancia.
2. Aplicaciones → *Actualizar lista de aplicaciones*.
3. Instalar **Enteza - Descuento en factura**.
4. Comprobar por RPC que `latest_version` queda en `19.0.1.0.0` antes de darla por
   instalada (ver `catalogo-modulos.md` del skill `odoo19-dev`).

## Notas de mantenimiento

- El wizard calca `sale.order.discount` (`addons/sale/wizard/sale_order_discount.py`) en su
  variante "On All Order Lines": mismo campo `discount_percentage` con `widget="percentage"`
  (se guarda como fracción 0–1, no como 0–100) y la misma validación de que no supere 1.0.
- 🔴 **`account.move.line.display_type` no es como `sale.order.line.display_type`.** En
  `sale.order.line` es `False` para una línea de producto normal, y por eso el wizard nativo
  filtra con `not line.display_type`. En `account.move.line` es un `Selection`
  **`required=True`**: una línea de producto vale `'product'`, nunca `False`. Copiar el
  filtro tal cual (`not line.display_type`) deja el recordset vacío y el wizard no escribe
  nada — sin ningún error, el botón "Aplicar" simplemente no hace efecto. El filtro correcto
  es `line.display_type == 'product'` (dentro de `invoice_line_ids`, que ya viene acotado
  por dominio a `('product', 'line_section', 'line_subsection', 'line_note')`, así que
  equivale a excluir solo secciones y notas).
- El botón se inserta con un xpath sobre `//group[hasclass('oe_invoice_lines_tab')]`, que es
  el grupo que envuelve narración + totales en `account.view_move_form`. Si Odoo cambia esa
  clase en una futura versión, el xpath deja de encontrar el nodo y la vista falla al
  cargar — comprobar tras cualquier actualización de Odoo.
- Sin pruebas ejecutadas: no hay acceso a `odoo-bin --test-enable` en esta instancia.
