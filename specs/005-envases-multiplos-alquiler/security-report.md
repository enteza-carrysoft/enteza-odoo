# Security review — 005-envases-multiplos-alquiler

Módulos: `rental_custom` 19.0.1.19.0 y `enteza_portal_pedidos` 19.0.2.1.0 (Odoo 19.0 EE, `enteza`,
producción, sin desplegar). Revisión estática de código: el módulo no está instalado con esta
versión, así que no hay comparación con la instancia en vivo. No se pudo hacer `git diff` (el
revisor no tiene shell): lo nuevo se ha separado de lo previo por los ficheros sin versionar del
`git status` y por los comentarios «Spec 005» del código.

## Verdict
APPROVED

## Findings

| Severity | Rule | File:line | Resolution |
|---|---|---|---|
| INFO | odoo_security_scan | ambos módulos | 0 ERROR. 2 WARN `sudo-unjustified` en `rental_custom` (`models/sale.py:186`, `wizard/rental_order_rename_wizard.py:20`) y 21 en el portal (`controllers/common.py:51`, `controllers/portal.py:29,55,224`, `models/sale_order.py` x14, `tests/test_portal_http.py` x3). **Todos previos**: ninguno está en los ficheros nuevos (`product_envase.py`, `sale_order_line_envase.py`, `report/*`, `sale_order_envases.py`, `test_envases*.py`). `sale.py:186` lleva su justificación en el docstring (l.182-183), no en la misma línea con `# sudo:`. Los sudo que tocan las rutas cambiadas (`portal.py:224`, `sale_order.py:153,161,163,177,459,508`) son los mismos llamadores de siempre; las líneas nuevas solo leen o lanzan error, sin crear ni escribir nada nuevo. No bloquea. |
| INFO | odoo_validate | ambos módulos | 0 ERROR. 6 WARN `v15-command` en `rental_custom/views/rental_loss_report_views.xml` (previos, sin relación con la seguridad). Portal: sin hallazgos. |
| PASS | campo calculado | `rental_custom/models/sale_order_line_envase.py:17-46` | `enteza_envase_count`: `compute`, sin `store`, sin `inverse`, sin `compute_sudo` (por defecto False en un campo no almacenado). Es de solo lectura: si alguien lo escribe, `product_uom_qty` no cambia. Lee `product_tmpl_id.uom_ids` / `uom.uom` con los derechos del usuario: no puede saltarse las reglas multicompañía (AC18). No hay `sudo()` en el fichero. |
| PASS | restricciones | `sale_order_line_envase.py:56-73`, `product_envase.py:61-99` | Las `@api.constrains` solo lanzan `ValidationError`; no escriben nada. Los mensajes solo muestran el nombre del artículo, la cantidad y los nombres de las unidades de la propia línea, datos que el usuario ya puede leer. No dan una vía de escritura nueva. |
| PASS | portal: validación previa | `enteza_portal_pedidos/models/sale_order.py:481-491` | Los `cambios` se construyen DESPUÉS de filtrar `cesto` contra `_enteza_portal_catalogo_valido()` (l.471). Un `product_id` arbitrario del cliente nunca llega a `_enteza_envase_error_multiplo`: el mensaje solo puede nombrar artículos del catálogo que el portal ya sirve, así que no expone artículos de otros clientes ni internos. |
| PASS | portal: savepoint | `sale_order.py:496-524` | El `unlink`/`write`/`create` va dentro de `cr.savepoint()`. Si salta un `ValidationError` del ORM, se revierte toda la reconciliación aunque `enteza_json_endpoint` capture el error y la transacción se confirme. La cabecera (`_enteza_portal_escribir_header`) sigue escribiéndose fuera del savepoint: es comportamiento previo y son campos que el cliente puede editar. Hallazgo funcional, no de seguridad. |
| PASS | portal: envío | `sale_order.py:641-646` | Solo valida las líneas del propio pedido, que ya ha pasado la comprobación de propiedad. |
| PASS | `action_enteza_portal_repetir(omitidas=None)` | `sale_order.py:135-184`; `controllers/portal.py:215-241` | La ruta es `auth='user'`, `methods=['POST']`, `csrf=True`, y el formulario manda `csrf_token` (`portal_templates.xml:153-154`). Propiedad: `origen.partner_id.commercial_partner_id == partner.commercial_partner_id`, más `is_rental_order` y `state == 'sale'` (l.224-233). Si falla, devuelve `MissingError` y no dice si el pedido existe o es de otro. Lo nuevo dentro del bucle solo DESCARTA líneas (`continue`) y no amplía lo que se crea. Los textos de `omitidas` salen de las líneas del pedido de origen, que es del propio cliente. |
| PASS | `request.session` | `controllers/portal.py:118-128, 237-240` | La sesión de Odoo se guarda en el servidor: el navegador solo tiene el sid y no puede inyectar ni cambiar `enteza_portal_omitidas`. Solo se lee después de `enteza_get_solicitud(order_id)` (propiedad comprobada) y solo si `order_id` coincide. `pop` asegura que se muestra una sola vez. Contenido: un entero y una lista de `str` (`_()` con argumentos devuelve `str` en la 19), que se pueden serializar en JSON. |
| PASS | escapado QWeb (portal) | `views/portal_templates.xml:179-184` | Cada mensaje de `omitidas` se pinta con `t-esc`: se escapa. Aunque el nombre de un artículo tuviera HTML, saldría como texto. |
| PASS | t-raw → t-out (cambio ajeno) | `views/portal_templates.xml:326, 342` | `mensaje['body']` es `mail.message.body` (`fields.Html`, saneado al guardarse), así que llega como `Markup`. `t-out` pinta `Markup` sin escapar y escapa cualquier `str`, mientras que `t-raw` lo pintaba todo en crudo. Con un cuerpo `Markup` el resultado es el mismo y con un `str` es más seguro. Además `t-raw` está obsoleto desde la 17. Los mensajes siguen filtrados por `message_type == 'comment'` y por `not subtype_id.internal` (`sale_order.py:824-827`): el cliente no ve notas internas. Es seguro; se aprueba el cambio. |
| PASS | informe QWeb | `rental_custom/report/rental_order_report_templates.xml:11-20` | Hereda `sale_renting.report_rental_order_document`. Solo cambia el atributo `t-foreach` y añade una columna. Usa `t-out` (no `t-raw`) sobre `_enteza_envase_label()`, que devuelve `str` y por tanto se escapa. |
| PASS | `_enteza_pickup_lines` | `sale_order_line_envase.py:97-103` | Recorre `self.order_line` del mismo `doc`: son las mismas líneas, de la misma compañía, que quien imprime ya puede leer. No hay `search` ni `sudo` ni dominio dinámico. Ahora salen también las líneas de alquiler sin `qty_delivered`, que son del mismo pedido y ya aparecen en el presupuesto. No es una fuga. |
| PASS | SQL / eval | ficheros nuevos y modificados | No hay `cr.execute`, `eval`/`safe_eval`/`exec`, `Markup()` sobre datos del usuario ni `csrf=False`. No hay rutas nuevas. |
| INFO | precisión (previo) | `sale_order.py:432, 460` | `precision_get('Product Unit of Measure')` es el nombre de la 18 (riesgo 9 de `architecture.md`). Solo afecta a la comparación de cantidades. No es de seguridad y es previo. |

## Permission model reviewed
- groups: ninguno nuevo (en `## Security` de `architecture.md`: "Grupos: ninguno nuevo"). No hay `res.groups` en los ficheros nuevos.
- ACL rows checked: 0 nuevas, ninguna nueva necesaria (no hay modelos nuevos; `odoo_validate` no da errores de ACL en ninguno de los dos módulos). Cada modelo nuevo cubierto: no aplica.
- record rules: ninguna nueva, de acuerdo con `## Security`. Las reglas multicompañía nativas de `sale.order.line` / `product.template` siguen mandando, porque el compute no usa sudo.
- sudo: ninguno nuevo. Los previos no se han ampliado: las líneas nuevas que corren con sudo (`repetir`, reconciliación) solo omiten o rechazan.
- rutas: ninguna nueva; `/my/solicitudes/<id>/repetir` es `auth='user'`, POST, `csrf=True` y comprueba la propiedad.

## Unresolved questions
- Ninguna que bloquee. Pendiente de comprobar en pantalla al desplegar (no es seguridad): que las anclas
  del xpath del informe (`doc.order_line.filtered('qty_delivered')`, `th` «Pickedup»,
  `span[@t-field='line.qty_delivered']`) coinciden con el `arch_db` de la vista 1712. Si no
  coinciden, falla la actualización del módulo; no se produce una fuga.
- Recomendación menor, no bloquea: dejar el comentario `# sudo: <motivo>` en la línea de los
  sudo previos para que el escáner deje de avisar.
