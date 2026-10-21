# Test plan

Pruebas Python escritas y **no ejecutadas** (producción sin `odoo -u` ni `--test-enable`): se entregan
validadas por sintaxis. Las filas `ui` se comprueban en pantalla tras desplegar; crear un presupuesto de
prueba en producción necesita permiso del usuario.

| AC | Scenario | Layer (static/server/rpc/ui/tests/manual) | Status |
|----|----------|--------------------------------------------|--------|
| AC1 | Onchange de `product_id`/`product_uom_qty` no devuelve `warning`; en pantalla, elegir un artículo con envase no abre ninguna ventana | tests + ui | pending |
| AC2 | Indicador verdadero con 1 ud y con 30 uds (envase de 25); en pantalla la celda sale en naranja | tests + ui | pending |
| AC3 | Indicador falso con 50 uds, sin envase, venta normal, sección/nota y pedido de faltas | tests | pending |
| AC4 | 25,0000001 uds con envase de 25 → falso; campo `compute`, `store=False`, sin `inverse`, solo lectura, sin sudo | tests + static | pending |
| AC5 | La cabecera de la columna tiene `help` con el significado | static + ui | pending |
| AC6 | `create`/`write`/`copy` con no múltiplo no lanzan error; la unidad distinta de la base sigue rechazándose | tests | pending |
| AC7 | `enteza_portal_pedidos`, parte de recogida y `enteza_envase_count` sin cambios en el diff | static | pending |
| AC8 | Tests reescritos; `USAGE.md`, `HISTORY.md` y manifiesto 19.0.1.21.0 actualizados | static | pass (revisión estática 2026-10-22: manifiesto 19.0.1.21.0; HISTORY.md entrada 19.0.1.21.0; USAGE.md menciona el naranja y la cabecera; test_envases.py reescrito: test_sin_onchange_con_aviso, test_indicador_verdadero/falso/campo_calculado; tests NO ejecutados) |
