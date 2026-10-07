# Test plan

Pruebas en `rental_custom/tests/test_faltas_desde_pedido.py`, **escritas y no ejecutadas**
(sin `--test-enable` en este hosting). Tras desplegar se comprueba en la interfaz con un
pedido real, con el usuario.

| AC | Scenario | Layer (static/server/rpc/ui/tests/manual) | Status |
|----|----------|--------------------------------------------|--------|
| AC1 | `test_boton_solo_sin_albaranes_abiertos`: pedido con albarán abierto → `missing_from_order_allowed` False y `UserError`; tras cancelar sus albaranes → True | tests | pending |
| AC2 | `test_asistente_lista_lineas_de_material`: línea de servicio excluida, `qty_missing` 0 | tests | pending |
| AC3 | `test_facturar_faltas_crea_el_mismo_pedido`: cabecera y línea iguales a las del camino del albarán (cliente, compañía, origen, enlace, diario, no alquiler, fecha evento) | tests | pending |
| AC4 | `test_faltas_acumulan_y_no_superan_lo_alquilado`: dos tandas suman `qty_lost`; pasarse da `UserError` y no crea pedido | tests | pending |
| AC5 | `test_sin_faltas_solo_marca_devuelto` y `test_con_faltas_marca_devuelto` (`rental_status == 'returned'`) | tests | pending |
| AC6 | `test_confirmar_faltas_valida_la_salida` (con usuario de ventas sin grupo de almacén) y `test_faltas_desde_albaran_no_se_validan_solas` | tests | pending |
| AC7 | `test_facturar_faltas.py` sin modificar | static + tests | pending |
| AC8 | `test_action_confirm_devuelve_accion.py` sin modificar; `action_confirm` devuelve `res` | static + tests | pending |
| AC9 | `ir.model.access.csv` con `sales_team.group_sale_salesman`; `test_usuario_sin_ventas_no_accede` | static + tests | pending |
| AC10 | `odoo_validate`, `validar_vistas.py`, `validar_modulo.py` en verde | static | pass |
