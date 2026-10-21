# Security review — 007-envases-aviso-visual-sin-ventana

Módulo: `rental_custom` 19.0.1.21.0. Alcance revisado: `models/sale_order_line_envase.py`,
`views/sale_order_views.xml`, `tests/test_envases.py` (más los helpers que el compute invoca en
`models/product_envase.py`, solo lectura).

## Verdict
APPROVED

## Findings
| Severity | Rule | File:line | Resolution |
|---|---|---|---|
| INFO | odoo_security_scan | — | 0 ERROR. Los 2 WARN `sudo-unjustified` (`models/sale.py:186`, `wizard/rental_order_rename_wizard.py:20`) son anteriores y están fuera del alcance de esta spec; el cambio no añade ningún `sudo()`. |
| INFO | odoo_validate | — | 0 ERROR. Los 6 WARN `v15-command` de `views/rental_loss_report_views.xml` son anteriores y no afectan a la seguridad. |
| INFO | Campo calculado | models/sale_order_line_envase.py:26-30, 63-78 | `enteza_envase_no_multiplo`: Boolean, `compute` sin `store`, sin `inverse`, sin `compute_sudo` (por defecto False en no almacenados) => solo lectura y evaluado con los derechos y compañías del usuario. No abre vía de escritura (un `write` sobre él no hace nada) ni lee datos de otra compañía: solo usa la propia línea, su pedido y las UdM del producto, que el usuario ya puede leer. Test `test_indicador_campo_calculado` (tests:155-161) lo afirma. |
| INFO | Restricción unidad base | models/sale_order_line_envase.py:80-87; product_envase.py:89-99 | `_check_enteza_envase_unidad` sigue con `@api.constrains('product_id','product_uom_id','is_rental')` y `raise ValidationError`; misma exclusión de faltas (`order_id.rental_order_id`). No se ha relajado. Cubierto por `test_unidad_distinta_rechazada` (tests:259-269). |
| INFO | Onchange eliminado | — | No queda ningún `_onchange_enteza*` en el repositorio (grep); `test_sin_onchange_con_aviso` (tests:126-130). |
| INFO | Vista | views/sale_order_views.xml:48-54 | Solo `column_invisible="1"` y `decoration-warning`; sin `groups`, sin `t-raw`/`Markup`, sin botones ni acciones. Un atributo de decoración no concede ni quita permisos. |
| INFO | Cobertura de test (no bloqueante) | tests/test_envases.py:335-349 | `test_usuario_stileum` (AC18 de la 005) comprueba con usuario de otra compañía solo `enteza_envase_count`, no el nuevo indicador. Como usa los mismos helpers y no hay `sudo`, el riesgo es nulo; se sugiere añadir un `assertFalse(linea.enteza_envase_no_multiplo)` ahí. |
| INFO | Documentación SDD | specs/007-.../architecture.md:9-10 | `## Security` está vacía (`TODO`), igual que en la 006. El modelo de permisos decidido está en `spec.md` (`## Constraints`: «Sin permisos, modelos, ACL ni rutas nuevas»), y el código lo cumple. Se recomienda copiar esa línea a `architecture.md` para trazabilidad. |

## Permission model reviewed
- groups: ninguno nuevo · ACL rows checked: 0 nuevas (no hay modelos nuevos; `sale.order.line` se hereda con `_inherit`, cubierto por las ACL nativas) · record rules: ninguna nueva; se aplican las nativas multi-compañía de `sale.order.line` porque no hay `sudo` ni `compute_sudo`.
- Sin rutas/controladores nuevos, sin `sudo()`, sin dominios dinámicos, sin `ir.config_parameter`.
- Tests validados por lectura; no se han ejecutado (no hay entorno de pruebas en producción).

## Unresolved questions
Ninguna bloqueante.
