# Test plan

Las pruebas `tests` se escriben en el módulo pero **no se pueden ejecutar** en este hosting
(sin `--test-enable` ni instancia de pruebas). Lo verificable de verdad antes de desplegar es
la capa `static`; las capas `rpc`/`manual` se comprueban tras desplegar, con el usuario.

| AC | Scenario | Layer (static/server/rpc/ui/tests/manual) | Status |
|----|----------|--------------------------------------------|--------|
| AC1 | `test_widget_prestamo.test_falta_no_supera_lo_pedido_con_disponible_negativo`: 50 en almacén, pedido confirmado de 300, nuevo presupuesto de 40 → `enteza_falta` = 40. Tras desplegar: RPC sobre pedido 2648, `enteza_falta` ≤ `product_uom_qty` en todas las líneas | tests + rpc | pending |
| AC2 | `test_widget_prestamo` existentes (80 libres, 95 pedidas → 15) sin cambios | tests | pending |
| AC3 | `test_confirmacion.test_no_se_reserva_mas_de_lo_pedido`: con disponible negativo, aceptar el diálogo deja `qty_reserved` = cantidad de la línea | tests | pending |
| AC4 | `test_disponibilidad.test_deficit_no_supera_lo_pedido` + mensaje de revalidación con `max(0, …)` | tests + static | pending |
| AC5 | `test_confirmacion.test_alquiler_ya_empezado_no_propone_prestamo` y `test_solo_se_proponen_las_lineas_futuras` | tests | pending |
| AC6 | `test_ciclo_vida.test_cancelar_aprobado_cancela_los_albaranes` | tests | pending |
| AC7 | `test_albaranes.test_entrega_parcial_conserva_el_enlace_y_acumula_lo_enviado` | tests | pending |
| AC8 | `test_devolucion.test_no_se_propone_dos_veces_lo_mismo` y `test_aceptar_recalcula_lo_devolvible` | tests | pending |
| AC9 | `tests/__init__.py` importa `test_buscador_producto` | static | pass |
| AC10 | `odoo_validate`, `validar_vistas.py`, `validar_modulo.py` en verde; `ir.model.access.csv` y `security/` sin diff | static | pass |
