# Changelog

## 19.0.2.0.0

- Impuestos de alquiler en el producto (`rental_taxes_id`).
- Configuración fiscal en la categoría del producto: impuestos de venta,
  cuenta de ingresos por alquiler e impuestos de alquiler.
- Herencia producto → categoría → estándar para cuentas e impuestos.
- Los impuestos de venta caen a la categoría cuando el producto no tiene
  impuestos de cliente propios.
- **Corrección**: la distinción alquiler/venta pasa a evaluarse por línea
  (`sale.order.line.is_rental`) y ya no por pedido. Antes, cualquier línea de
  un pedido de alquiler recibía la cuenta de alquiler, incluidas las líneas de
  venta de material roto o no devuelto.
- Los impuestos resueltos se mapean con la posición fiscal del pedido, igual
  que hace Odoo de forma nativa con `fiscal_position.map_tax`.

## 19.0.1.0.0

- Campo de cuenta de ingresos por alquiler dependiente de compañía.
- Aplicación automática al crear facturas desde pedidos de alquiler.
- Respaldo a la cuenta estándar.
- Compatibilidad con posiciones fiscales.
- Pruebas de venta, alquiler, respaldo y mapeo fiscal.
