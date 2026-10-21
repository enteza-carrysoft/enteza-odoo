# Security review — 006-envases-advertencia-no-bloqueo

Módulos: `rental_custom` 19.0.1.20.0 y `enteza_portal_pedidos` 19.0.2.2.0 (Odoo 19.0 EE, `enteza`,
producción, sin desplegar). Es una revisión estática del código y se limita a lo que cambia respecto
a la spec 005, que ya está aprobada (`specs/005-envases-multiplos-alquiler/security-report.md`). El
revisor no tiene shell, así que no ha hecho `git diff`. Lo nuevo se ha localizado por los
comentarios «Spec 006» y comparando con las líneas que cita el informe de la 005.

Modelo de permisos de referencia: es una spec en modo `bug`, así que `architecture.md` es la
plantilla y su `## Security` está en TODO. El modelo lo fijó el desarrollador en
`state.json → clarify.security` («Sin grupos nuevos», «Nadie obtiene permisos nuevos», «Sin
reglas nuevas», «sudo: Ninguno nuevo», «Ninguna [ruta] nueva») y se repite en `spec.md →
Constraints` («Sin permisos, modelos ni rutas nuevas»). La revisión se ha hecho contra ese
modelo.

## Verdict
APPROVED

## Findings

| Severity | Rule | File:line | Resolution |
|---|---|---|---|
| INFO | odoo_security_scan | ambos módulos | 0 ERROR. Los WARN `sudo-unjustified` son los mismos 2 + 21 de la 005. Solo cambian algunos números de línea: `portal.py` 224→225 y `sale_order.py` 177→179, 459→462, 508→501. Los ficheros nuevos o modificados de esta spec (`sale_order_line_envase.py`, `sale_order_envases.py`) no tienen ningún `sudo()`. |
| INFO | odoo_validate | ambos módulos | 0 ERROR. `rental_custom` tiene 6 WARN `v15-command` previos en `views/rental_loss_report_views.xml`, ajenos a esta spec. El portal no tiene hallazgos. |
| PASS | (4) restricción de unidad base | `rental_custom/models/sale_order_line_envase.py:68-75`; `product_envase.py:89-99` | Se ha quitado solo la restricción de múltiplos. `_check_enteza_envase_unidad` sigue como `@api.constrains('product_id', 'product_uom_id', 'is_rental')` y lanza `ValidationError`. El filtro que usa, `_enteza_envase_lineas_a_validar` (l.49-55), no cambia: líneas de alquiler con producto, sin las de faltas. AC4 se mantiene. |
| PASS | onchange nuevo | `sale_order_line_envase.py:57-66` | Solo devuelve `{'warning': ...}`, sin escribir nada y sin `sudo`. Corre con los derechos del usuario sobre su propia línea. El mensaje lleva el nombre del artículo y cantidades que el usuario ya puede leer. Por `create`/`write` (API) no se ejecuta, que es lo que pide la spec. |
| PASS | (1) reconciliación sin validación previa ni savepoint: ¿abre una vía de escritura nueva? | `enteza_portal_pedidos/models/sale_order.py:451-519` | No. Los filtros que deciden QUÉ se puede escribir no cambian: `_enteza_portal_check_composing()` (l.540), la propiedad del pedido (`enteza_get_solicitud`, `controllers/common.py:51-53`), `qty <= 0` descartada (l.472), `product_id` limitado a `_enteza_portal_catalogo_valido()` (l.474), unidad fijada a `producto.uom_id` al crear (l.507) y `write` solo de `product_uom_qty` (l.498). La validación previa de la 005 solo RECHAZABA; quitarla permite cantidades no múltiplo, que es justo lo que pide la spec (AC5). No añade productos, pedidos ni campos escribibles. |
| LOW (funcional, no bloquea) | (1) atomicidad sin savepoint | `sale_order.py:489-513`; `controllers/common.py:76-93` | Sin `cr.savepoint()`, si un `ValidationError` o `UserError` del ORM salta a mitad del bucle (`unlink` → `write` → `create`), `enteza_json_endpoint` lo convierte en `{'error': ...}` sin relanzarlo. La transacción se confirma entonces con la reconciliación a medias: unas líneas borradas y otras sin crear. **No es un riesgo de seguridad**: cualquier estado parcial es un subconjunto de lo que el mismo cliente podría dejar con una petición válida (su pedido, en `composing`, con artículos del catálogo en unidad base). Además, la causa que motivó el savepoint en la 005 ya no existe: la restricción de múltiplo se ha quitado y la de unidad no puede saltar desde el portal, porque crea con `uom_id` y solo escribe la cantidad. Es lo mismo que hacía el portal antes de la 005. Recomendación opcional: mantener el `with self.env.cr.savepoint():` alrededor de l.490-517 para que guardar sea todo o nada, sea cual sea el error futuro. |
| PASS | avisos de guardado (portal) | `models/sale_order_envases.py:13-26`; `sale_order.py:486-487`; `static/src/grid/request_grid.xml:63-64` | Los productos llegan ya filtrados por el catálogo válido (`cesto`, l.467-477), así que los mensajes solo nombran artículos que el portal ya sirve a ese cliente. Son `str`, viajan en el JSON `warnings` y la rejilla OWL los pinta con `t-esc`, que escapa. Sin `sudo` nuevo: `Product` es el `sudo()` previo de l.462 y solo se lee. |
| PASS | (2) avisos de «Repetir pedido» en `request.session` | `controllers/portal.py:118-129, 236-242`; `views/portal_templates.xml:179-190` | La sesión se guarda en el servidor, así que el navegador no puede inyectar la clave `enteza_portal_omitidas`. Se lee con `pop` (se muestra una sola vez) y solo DESPUÉS de `enteza_get_solicitud(order_id)` (propiedad comprobada), y se descarta si `order_id` no coincide (l.120-121). Contenido: un entero y dos listas de `str` que salen de `_enteza_envase_error_multiplo` / `_enteza_envase_error_unidad` sobre las líneas del pedido de origen, cuyo `commercial_partner_id` es el del usuario (l.227-232). No hay datos de otros clientes. La plantilla pinta cada mensaje con `t-esc` (l.182, l.188): se escapa, aunque el nombre de un artículo tuviera HTML. |
| PASS | (3) controles de «Repetir pedido» | `controllers/portal.py:216-242`; `sale_order.py:135-186`; `portal_templates.xml:150-154` | La ruta sigue igual: `auth='user'`, `methods=['POST']`, `csrf=True`, y el formulario manda `csrf_token`. La propiedad se sigue comprobando igual (`commercial_partner_id`, `is_rental_order`, `state == 'sale'`), y si falla devuelve `MissingError` sin distinguir «no existe» de «no es tuyo». El filtro de líneas copiables no cambia (`rent_ok` y `type == 'consu'`, l.149-151). El único cambio del bucle es que una cantidad no múltiplo ya no se omite (`continue`): se copia y se anota en `avisos`. Se siguen omitiendo las líneas con unidad distinta de la base (l.170-174). Lo que se crea es igual en forma a lo de antes de la 005, sin campos nuevos. |
| PASS | envío | `sale_order.py:634-635` | Solo se quita un rechazo. El resto de comprobaciones del envío (estado, fechas, almacén, líneas no vacías) y la escritura de estado no cambian. |
| PASS | (5) sudo | ficheros de la spec | Ninguno nuevo. Los `sudo()` que tocan las rutas cambiadas (`portal.py:225`, `sale_order.py:153,161,163,179,462,501`) ya existían y no se han ampliado. |
| PASS | csrf / rutas / SQL / eval / Markup | ficheros modificados | No hay rutas nuevas ni `csrf=False`, `cr.execute`, `eval`/`exec`, `Markup()` sobre datos del usuario ni `t-raw`. |
| INFO (previo, fuera de alcance) | destinatario de «Repetir» | `sale_order.py:153-161` | La solicitud destino se busca o crea con `origen.partner_id`, no con el partner del usuario logado. Si el pedido de origen es de otro contacto de la misma empresa, la solicitud queda a nombre de ese contacto. Las dos partes son del mismo `commercial_partner_id` y la regla nativa 171 (`child_of commercial_partner_id`) ya da acceso a ambas, así que no hay fuga entre clientes. Ya era así antes de esta spec; se anota para una revisión funcional futura. |

## Permission model reviewed
- groups: ninguno nuevo (clarify: «Sin grupos nuevos»). Los ficheros revisados no tienen `res.groups`.
- ACL rows checked: 0 nuevas y ninguna necesaria, porque no hay modelos nuevos. `odoo_validate` no da ningún error de ACL en ninguno de los dos módulos. Cada modelo nuevo cubierto: no aplica.
- record rules: ninguna nueva, como dice clarify. Siguen mandando las reglas nativas de portal y multicompañía. El onchange y el compute corren sin `sudo`.
- sudo: ninguno nuevo; los previos no se han ampliado.
- rutas: ninguna nueva. `/my/solicitudes/<id>/repetir` sigue siendo `auth='user'`, POST, `csrf=True` y con comprobación de propiedad. Las rutas JSON de guardado y envío siguen pasando por `enteza_get_solicitud`.

## Unresolved questions
- Ninguna bloquea.
- Recomendación (funcional): volver a envolver la reconciliación del portal en un `savepoint` para que el guardado sea atómico. Ver el hallazgo LOW.
- Recomendación (documental): copiar en `architecture.md → ## Security` las respuestas de `clarify.security`, para que el modelo de permisos quede en el artefacto de la spec y no solo en `state.json`.
