# Test plan

Pruebas Python escritas y **no ejecutadas** (producción sin `odoo -u` ni `--test-enable`): se entregan
validadas por sintaxis. Las filas `ui`/`manual` se comprueban en producción tras desplegar, sobre un
presupuesto de alquiler de prueba en borrador que después se cancela, y con permiso del usuario antes
de cualquier escritura.

| AC | Scenario | Layer (static/server/rpc/ui/tests/manual) | Status |
|----|----------|--------------------------------------------|--------|
| AC1 | Crear (`create` con `order_line`, como hace la integración) y modificar una línea de alquiler con 30 uds de un artículo con envase de 25: no lanza error y guarda la cantidad | tests + manual | pending |
| AC2 | Onchange de `product_id`/`product_uom_qty` con 30 uds devuelve `{'warning': ...}` con el texto «BOL BARCO (25): 30 uds no es múltiplo del envase de 25. Prueba con 25 o 50.»; en pantalla sale el aviso y se puede guardar | tests + ui | pending |
| AC3 | Onchange sin advertencia con 50 uds, con artículo sin envase, en línea de venta normal y en línea de pedido de faltas | tests | pending |
| AC4 | Unidad distinta de la base en artículo con envase sigue lanzando `ValidationError`; línea existente en otra unidad no se toca | tests | pass (static: rental_custom/models/sale_order_line_envase.py:68-75 `_check_enteza_envase_unidad` intacta, constrains en product_id/product_uom_id/is_rental, no se dispara con solo cantidad; product_envase.py:89 sin modificar; cubierto por test_unidad_distinta_rechazada y test_linea_antigua_en_otra_unidad_editable, no ejecutados) |
| AC5 | Portal: guardar 90 uds de un artículo con envase de 25 guarda la cantidad y devuelve el aviso; el envío no se rechaza por este motivo | tests + manual | pending |
| AC6 | Portal: «Repetir pedido» copia todas las líneas y avisa de las no múltiplo | tests + manual | pending |
| AC7 | `enteza_envase_count`, columna y etiqueta del parte de recogida sin cambios (tests de la 005 siguen aplicando) | tests + static | pass (static: git status no muestra cambios en rental_custom/views/sale_order_views.xml ni report/rental_order_report_templates.xml ni models/product_envase.py; compute, `_enteza_envase_numero` y `_enteza_envase_label` presentes sin lógica de múltiplo; tests test_count_*, test_etiqueta_parte_recogida, test_parte_todas_las_lineas, test_columna_solo_en_alquiler no ejecutados) |
| AC8 | Tests de múltiplo reescritos (backend y portal); `USAGE.md`, `HISTORY.md`, README del portal y versiones de manifiestos actualizados | static | pass (static: tests rewritten en rental_custom/tests/test_envases.py:114-143, enteza_portal_pedidos/tests/test_envases_portal.py, test_packaging.py:69-88, test_submit_flow.py:65-84; manifiestos 19.0.1.20.0 y 19.0.2.2.0; HISTORY/USAGE/DESCRIPTION de ambos módulos y README del portal:63-66 actualizados) |
