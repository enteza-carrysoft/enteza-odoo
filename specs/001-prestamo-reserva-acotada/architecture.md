# Architecture

## Root Cause

- **AC1–AC4.** `sale_order_line._compute_enteza_prestamo` calcula
  `falta = product_uom_qty - disponible - cubierto` con `disponible` sin acotar. El motor
  (`enteza.disponibilidad.disponible`) devuelve negativo a propósito (déficit del almacén),
  pero ese déficit es de **otros** pedidos confirmados: la parte del almacén propio que
  le corresponde a una línea nueva es `max(disponible, 0)`. `deficit()` tiene el mismo
  defecto, y de ahí sale el «solo hay -X libres» de `_revalidar_disponibilidad`.
- **AC5.** `sale_order._enteza_lineas_con_deficit` no mira si el alquiler ya ha empezado.
- **AC6.** `enteza_stock_loan.action_cancelar` solo cambia el estado; la cancelación de
  albaranes vive en `_enteza_cancelar_por_vacio` y no se reutiliza.
- **AC7.** `stock.picking._create_backorder_picking` hace `copy()` y `stock.move._split` hace
  `copy_data()`: `enteza_loan_id`, `enteza_devolucion` y `enteza_loan_line_id` son
  `copy=False` y se pierden. `_enteza_albaran_validado` compara `albaran ==
  picking_out_id` (falla con el backorder) y hace `qty_sent = quantity` (sobrescribe).
- **AC8.** `_calcular_devolucion` y `action_devolver` usan `qty_pending` = enviado −
  devuelto, sin descontar devoluciones en curso.

## Fix Plan

Módulo `enteza_prestamo_intercompania`, versión `19.0.10.0.3` → `19.0.10.1.0`. Sin cambios de
esquema (solo lógica).

1. `models/sale_order_line.py` · `_compute_enteza_prestamo`: `propio = max(disponible, 0.0)`;
   `falta = product_uom_qty - propio - cubierto`.
2. `models/enteza_disponibilidad.py` · `deficit()`: `falta = cantidad - max(disponible, 0)`.
3. `models/enteza_stock_loan.py` · `_revalidar_disponibilidad`: el texto usa
   `max(0, necesaria - falta)`.
4. `models/sale_order.py` · `_enteza_lineas_con_deficit`: añade `linea.start_date >
   fields.Datetime.now()`. Al no haber líneas, `action_confirm` ya confirma directamente.
5. `models/enteza_stock_loan.py`: método `_enteza_cancelar_albaranes()` (cancela ida
   `picking_out_id`/`picking_in_id` no `done`/`cancel`, con `sudo()` como hoy), usado por
   `action_cancelar` y `_enteza_cancelar_por_vacio`.
6. `models/stock_picking.py`:
   - `StockPicking._create_backorder_picking`: tras `super()`, copia `enteza_loan_id` y
     `enteza_devolucion` al backorder.
   - `StockMove._prepare_move_split_vals`: añade `enteza_loan_line_id`.
   - `StockPicking._enteza_albaran_raiz()`: sube por `backorder_id` hasta el original.
7. `models/enteza_stock_loan.py` · `_enteza_albaran_validado`: compara la raíz del albarán con
   `picking_out_id`/`picking_in_id`; en la salida, `qty_sent += quantity` de los
   movimientos `done` de ese albarán.
8. `models/enteza_stock_loan_line.py`: `_qty_en_devolucion()` (movimientos de albaranes
   `enteza_devolucion` que aterrizan en `warehouse_src_id.lot_stock_id`, no `done`/`cancel`)
   y `_qty_devolvible()` = `qty_pending - en_devolucion`. `_calcular_devolucion` usa
   `_qty_devolvible()` como pendiente; `action_proponer_devolucion` filtra por él;
   `wizard/enteza_prestamo_devolucion.action_devolver` revalida contra
   `_qty_devolvible()` en el momento de aceptar.
9. `tests/__init__.py`: importa `test_buscador_producto`. Pruebas nuevas según test-plan.
10. `README.md`: entrada de la 19.0.10.1.0.

## Security

Sin grupos, ACL, reglas ni rutas nuevas. Los `sudo()` son los existentes: la cancelación de
albaranes reutiliza el de `_enteza_cancelar_por_vacio`; `_qty_en_devolucion` lee
`stock.move` con `sudo()` igual que `_enteza_cancelar_movimientos` (el albarán de vuelta es de
la otra compañía) y solo devuelve una cantidad agregada. `action_cancelar` sigue exigiendo
`group_prestamo_responsable`.
