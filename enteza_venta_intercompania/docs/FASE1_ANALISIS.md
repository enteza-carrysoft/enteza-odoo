# Fase 1 · Análisis de arquitectura — `enteza_venta_intercompania`

> Material cedido entre compañías, alquilado con Odoo Rental y facturado entre ellas cuando
> el cliente no lo devuelve. Encargo: `PROMPT_intercompany_rental_stock_odoo19.md`.
> Fecha: 2026-09-27. **Documento de análisis: no hay código del módulo.**
>
> ⚠️ **Superado el 2026-09-28.** Se eligió otro enfoque: un alquiler de cesión Vimaple → Stileum
> en lugar de la consigna pura. Lo implementado y su porqué están en el `README.md` del módulo.
> Este análisis se conserva por los hallazgos (H3, trampas de valoración y de alquiler).

---

## Resumen en una pantalla

**Se puede hacer casi todo con lo nativo.** Lo que hay que programar es pequeño y está
localizado: enlazar la venta de faltas con su línea de alquiler, repartir las unidades
perdidas por propietario, crear la factura A → B en borrador y sacar físicamente del stock
las unidades perdidas.

| Paso del negocio | Quién lo hace |
|---|---|
| A cede material a B sin venderlo | **Nativo**: dos albaranes por el tránsito intercompañía y, en la recepción de B, «Asignar propietario» = A (Consigna) |
| B lo alquila, entrega y recoge | **Nativo** (Rental + albaranes de alquiler), sin tocar |
| El cliente no devuelve parte | **Ya existe** en `rental_custom`: «Facturar las Faltas» crea una venta aparte. Se usa en producción (131 pedidos) |
| B factura esa venta al cliente | **Nativo** |
| A factura a B en borrador, precio de tarifa | **Módulo nuevo** |
| Las unidades perdidas salen del stock | **Módulo nuevo**: hoy no salen nunca (ver hallazgo 3) |
| A publica y B recibe su factura de proveedor | **Nativo**: `account_inter_company_rules` (hoy **sin instalar**) |

**Hay que decidir 10 cosas antes de programar** (sección K). Las cuatro que bloquean:

1. Instalar `account_inter_company_rules` en producción. Efecto colateral: la factura mensual
   de reparto de gastos Vimaple → Stileum generaría sola su factura de proveedor, que hoy se
   hace a mano.
2. Activar en Ajustes **Consigna** (propietarios de stock) y **Tarifas**. Hoy están las dos
   apagadas.
3. Criterio contable de R1: A deja de valorar el material en cuanto sale hacia B. Lo tiene que
   validar la asesoría.
4. Cómo se relacionan este módulo y `enteza_prestamo_intercompania`, que modela lo mismo con
   otro criterio de propiedad.

### Tres hallazgos que el encargo no preveía

1. **La facturación del material perdido ya existe**, y no es como la suponía el encargo
   (H3a). No añade una línea al pedido de alquiler: crea **otro pedido de venta**, enlazado
   al alquiler por `sale.order.rental_order_id`, y anota `sale.order.line.qty_lost`. Está en
   `rental_custom` (instalado, `19.0.1.13.0`) y lleva 131 pedidos. Lo que **no** tiene es un
   enlace **línea a línea** con la línea de alquiler, y sin ese enlace no se puede saber de
   quién es cada unidad perdida.
2. **La consigna no se ha usado nunca en esta base**: hay 0 `stock.quant` con propietario y el
   grupo `stock.group_tracking_owner` no tiene usuarios. Todo lo que dependa de propietarios
   empieza de cero, sin datos antiguos que convertir.
3. **Las unidades perdidas se quedan para siempre en «Customers/Alquiler».** «Facturar las
   Faltas» cancela el albarán de devolución pendiente y suma la pérdida a `qty_returned`, pero
   no mueve el stock. El albarán de salida que crea la venta de faltas sale de `Stock`, no de
   `Alquiler`, y se cancela a mano: 59 de 60 están cancelados. Hoy hay 267 quants con cantidad
   en las dos ubicaciones de alquiler. Con material de A dentro, esto dejaría a A como
   propietaria eterna de unidades que ya no existen. **Hay que resolverlo.**

---

## Cómo se ha verificado cada cosa

Tres fuentes. No son intercambiables:

| Marca | Fuente | Cuánto vale |
|---|---|---|
| `[RPC]` | Consulta por RPC a la base de producción `enteza`, 2026-09-27 | Manda sobre todo lo demás |
| `[C19 ruta:línea]` | Odoo 19.0 Community, `odoo/odoo`, commit `4e7b84d` (2026-09-26) | Verificado en 19 |
| `[EE18 ruta:línea]` | Odoo **18.0** Enterprise, `enteza-carrysoft/odoo_enterprise_18` | **Así era en la 18.** No hay código Python de Enterprise 19 accesible |

🔴 **Límite que el encargo exige declarar (§0.4.2).** Del Enterprise 19 solo se ha podido
verificar lo que se ve por RPC: campos, módulos, grupos y vistas. La lógica Python de
`sale_renting`, `sale_stock_renting` y `account_inter_company_rules` en 19 **no es legible**.
Lo que se afirma de esa lógica viene de la 18 y lleva la marca `[EE18]`. Así lo ha pedido el
usuario («revisa el repositorio odoo 18 enterprise»). Se mitiga en dos pasos:

- Tras instalar `account_inter_company_rules`, confirmar por RPC los nombres de campo de
  `res.company` que usa el módulo (`intercompany_user_id`, `intercompany_generate_bills_refund`,
  `intercompany_document_state`).
- Hacer una prueba real guiada (TESTING.md) antes de darlo por bueno.

**Spikes en base de pruebas: no son posibles.** `enteza` es producción y no hay instancia de
pruebas ni `odoo-bin` (CLAUDE.md, restricciones 1 a 3). Las pruebas se escribirán, pero se
entregarán **validadas por sintaxis, no ejecutadas**.

---

## A. Funcionalidades nativas que se usan

| Necesidad | Funcionalidad Odoo 19 | Personalización |
|---|---|---|
| Multiempresa | Compañías sin jerarquía; partners de compañía compartidos (`company_id` vacío) `[RPC: res.partner 1 y 6]` | Ninguna |
| Stock y cesión | Albarán de salida en A a «Inter-company transit» + recepción en B desde el tránsito `[C19 stock/data/stock_data.xml:34]` | Ninguna (ver K-9) |
| Propiedad / Consigna | `stock.picking.owner_id` («Asignar propietario»), que al validar se copia a los movimientos y a sus líneas `[C19 stock/models/stock_picking.py:651, 1277-1279]` | Ninguna. Hay que **activar** Consigna (K-2) |
| Alquiler | `sale_renting` + `sale_stock_renting` con albaranes de alquiler `[RPC: instalados]` | Ninguna |
| Devoluciones | Devolución de alquiler encadenada a la entrega (MTO, `move_orig_ids`) `[EE18 sale_stock_renting/models/sale_order_line.py:376-405]` | Ninguna |
| Declarar material perdido | «Facturar las Faltas» de `rental_custom` (módulo del cliente, instalado) | Un enlace nuevo línea a línea (H) |
| Facturación B → cliente | Factura estándar del pedido de faltas | Ninguna |
| Facturación A → B | `account.move` estándar | **Creación automática en borrador** |
| Tarifa | API de `product.pricelist` `[C19 product/models/product_pricelist.py:112-169]` | Llamarla con la tarifa configurada |
| Factura de proveedor en B | `account_inter_company_rules` («Create Vendor Bills») `[EE18 account_inter_company_rules/models/account_move.py:11-25]` | Ninguna. Hay que **instalarlo** (K-1) |
| Usuario con permisos en A | `res.company.intercompany_user_id` del mismo módulo `[EE18 …/res_company.py:22-27]` | Se reutiliza, no se duplica |
| Auditoría | `create_uid`, chatter, `mail.thread` | Ninguna |

---

## B. Modelos estándar implicados

| Modelo | Papel | Evidencia |
|---|---|---|
| `stock.quant` | Existencias por ubicación **y propietario** (`owner_id`) | `[C19 stock/models/stock_quant.py:74]` |
| `stock.move` / `stock.move.line` | El movimiento y su detalle; el propietario vive en `stock.move.line.owner_id` | `[C19 stock/models/stock_move_line.py:64, 420]` |
| `stock.picking` | Albaranes. `owner_id` asigna propietario al validar | `[C19 stock_picking.py:651, 1277]` |
| `stock.location` | «Customers/Alquiler» es `usage='internal'`, de la compañía (id 16 Vimaple, 17 Stileum) | `[RPC res.company.rental_loc_id]` `[EE18 sale_stock_renting/models/res_company.py:239-254]` |
| `sale.order` / `sale.order.line` | Alquiler (`is_rental`, `qty_delivered`, `qty_returned`) y venta de faltas (`rental_order_id`, `qty_lost`) | `[RPC]` |
| `account.move` / `account.move.line` | Factura de faltas de B (`sale_line_ids`) y factura A → B | `[C19 account/models/account_move.py:5571]` |
| `product.pricelist` / `.item` | Precio A → B | `[C19 product_pricelist.py:112-169, product_pricelist_item.py:570]` |
| `res.company` | `rental_loc_id`, `inventory_valuation` y los campos intercompany | `[RPC]` `[EE18]` |

Datos de la base que condicionan el diseño `[RPC 2026-09-27]`:

- Las dos compañías valoran en **periódico** (`inventory_valuation='periodic'`) y todas las
  categorías usan **coste estándar**. Ver F.
- Tarifas: solo hay tres, las tres **archivadas**. El grupo `product.group_product_pricelist`
  no tiene usuarios.
- Ya existe un diario de ventas en Vimaple llamado «Facturas STILEUM» (id 46), usado en
  `ST/2026/00001`.

---

## C. Flujo de datos, de la cesión a la factura de proveedor

Con el ejemplo del encargo: A tiene 20 de X, cede 10 a B, B alquila 10, vuelven 8 y B factura
2 × 100 €. Tarifa A → B: 60 €.

| # | Documento | Compañía | Ubicación origen → destino | Propietario (ml) | Valoración |
|---|---|---|---|---|---|
| 1 | Salida de cesión (tipo de operación de salida de A) | A | A/Stock → Inter-company transit | — (de A) | **Sale del inventario de A**: el tránsito no tiene compañía `[C19 stock_account/models/stock_location.py:36-41]`. Ver R1 |
| 2 | Recepción de cesión (tipo de recepción de B) con **Asignar propietario = partner de A** | B | Transit → B/Stock | A | Excluida en B: el propietario no es B `[C19 stock_account/models/stock_move_line.py:38-45]` |
| 3 | Entrega de alquiler (nativa) | B | B/Stock → Customers/Alquiler | La que reserve: **cualquier propietario** (R2) | Interna → interna: no cambia nada |
| 4 | Devolución de alquiler (nativa, encadenada), 8 uds. | B | Alquiler → B/Stock | **La misma que salió**: la reserva encadenada respeta el propietario `[C19 stock_move.py:2146-2160]` | Sin efecto |
| 5 | «Facturar las Faltas» sobre el pendiente (2 uds.) | B | Cancela el pendiente de devolución; crea la venta de faltas S… | — | Nada. **Hoy las 2 uds. se quedan en Alquiler** (hallazgo 3) |
| 6 | Factura de B al cliente (2 × 100 €) → **publicar** | B | — | — | Ingreso en B |
| 7 | **Módulo**: al publicar 6, reparto por propietario → 2 uds. de A | — | — | — | — |
| 8 | **Módulo**: factura de cliente A → B en **borrador**, 2 × 60 € | A | — | — | Nada hasta publicar |
| 9 | **Módulo**: albarán «Material no devuelto», listo para validar | B | Alquiler → Customers | A (reserva estricta por propietario) | Excluida de B (propietario A); A ya no la valoraba |
| 10 | Una persona de A revisa y **publica** 8 | A | — | — | Ingreso en A |
| 11 | Factura de proveedor en B, en borrador (nativo) | B | — | — | Compra en B |

El paso 9 lo valida una persona de almacén: nada se mueve solo (CLAUDE.md).

---

## D. Puntos de extensión (firmas reales)

| Qué | Dónde | Firma | Fuente |
|---|---|---|---|
| Disparo al publicar | `account.move._post` | `def _post(self, soft=True)` → tras `super()` | `[C19 account/models/account_move.py:5571]` |
| Enlace de la línea de faltas | `stock.picking.action_create_sale_order` (de `rental_custom`) | Hook nuevo `_prepare_falta_sale_line_vals(move)` en `rental_custom` (K-6) | `[repo rental_custom/models/stock_picking.py]` |
| Que la venta de faltas no genere albarán desde Stock | `sale.order.line._action_launch_stock_rule` | `def _action_launch_stock_rule(self, *, previous_product_uom_qty=False)` → excluir las líneas de faltas | `[C19 sale_stock/models/sale_order_line.py:385]` |
| Reserva por propietario | `stock.move._update_reserved_quantity` | `(need, location_id, lot_id=None, package_id=None, owner_id=None, strict=True)` | `[C19 stock_move.py:1906]` |
| Precio | `product.pricelist._get_product_price_rule` + `product.pricelist.item._compute_price` / `_show_discount` | Patrón de `sale.order.line._get_display_price_ignore_combo` | `[C19 sale/models/sale_order_line.py:659-733]` |
| Bloqueo | `recordset.lock_for_update()` | `(*, allow_referencing=False)` | `[C19 odoo/orm/models.py:5577]` |
| Índice único | `models.UniqueIndex` | — | `[C19 odoo/orm/table_objects.py:185]` |

**Por qué no se sobrescribe la generación de la factura de proveedor.** El `_post` de
`account_inter_company_rules` crea la factura de proveedor en la compañía del partner cuando
esta tiene «Generate Bills» activo `[EE18 account_move.py:15-24]`. Al publicar la factura
A → B, eso ocurre solo. El módulo no toca nada ahí.

---

## E. Propiedad del stock (R2, R4, R6)

**Cómo sigue A siendo la propietaria.** La recepción en B se valida con `owner_id` = partner
de A. Odoo lo copia a las líneas de movimiento `[C19 stock_picking.py:1277-1279]` y el quant
de B/Stock queda con `owner_id = A` `[C19 stock_move_line.py:420]`.

**R2 · Propietarios mezclados: confirmado, y no impide nada.**

- La **entrega** de alquiler reserva quants de **cualquier propietario**:
  `_update_reserved_quantity(need, location, strict=False)` sin `owner_id`
  `[C19 stock_move.py:2138]`.
- 🔴 En la 19, **`restrict_partner_id` no limita la reserva.** Solo se usa en informes
  (`product.py:186`) y en la valoración (`stock_account/stock_move.py:675`). Fijarlo en los
  movimientos no evitaría la mezcla, así que no se usará para eso.
- La **devolución** de alquiler va encadenada a la entrega (`move_orig_ids`, MTO)
  `[EE18 sale_stock_renting/models/sale_order_line.py:398-403]`. La reserva encadenada toma
  las líneas del movimiento de origen con su propietario y en modo estricto
  `[C19 stock_move.py:2146-2160]`: **vuelve con el propietario con el que salió**.
- Por eso el reparto es exacto, sin suposiciones. Por línea de alquiler y propietario:

```
pendiente(propietario) = Σ entregado  (move lines hechas con destino Alquiler)
                       − Σ devuelto   (move lines hechas con origen Alquiler y destino interno)
                       − Σ ya procesado en el registro de enlaces del módulo
```

La única ambigüedad posible es que la venta de faltas facture **menos** unidades de las
pendientes y haya varios propietarios en la misma línea. Hoy «Facturar las Faltas» factura el
pendiente completo, así que casi no se dará. Aun así hay que decidir el criterio (K-7).

**R4 · Cambio de propiedad sin segundo traslado: opción P1.** Las unidades de A salen
**directamente** de Alquiler hacia el cliente, con propietario A (paso 9 de C). No hay ningún
traslado A → B ni una «recepción documental» (P2). P2 se descarta por tres motivos:

- Con valoración periódica no aporta nada contable (F).
- Serían dos movimientos más sin realidad física.
- *Synchronize Stock Moves* no puede generarlos, porque solo actúa sobre albaranes con pedido
  de venta y de compra (siguiente punto).

🔴 **Detalle crítico del paso 9.** El movimiento de salida **no puede llevar la línea de
alquiler en `sale_line_id`**. `sale_stock_renting` suma a `qty_returned` todo movimiento
hecho que salga de la ubicación de alquiler con una línea de alquiler
`[EE18 sale_stock_renting/models/stock_move.py:61-75]`, y `rental_custom` ya sumó ahí la
pérdida: se contaría dos veces. Llevará la línea **de la venta de faltas**, que no es de
alquiler. Así cuenta como entregada en esa venta y el alquiler no se toca.

**R6 · *Synchronize Stock Moves* no sirve para la cesión.** Solo actúa si el albarán tiene
`sale_id`, es de salida y existe un pedido de compra enlazado por `client_order_ref`
`[EE18 sale_purchase_stock_inter_company_rules/models/stock_picking.py:13-21]`. Una cesión
sin pedidos no entra. Además no copia el propietario (crea las líneas con
`_prepare_move_line_vals` de la recepción). **No se instala.** La cesión son dos albaranes
nativos y la recepción lleva «Asignar propietario» (K-9).

---

## F. Valoración (R1)

**Situación real** `[RPC]`: las dos compañías usan **periódico** (*at closing*) y coste
**estándar** en todas las categorías.

**Consecuencias** `[C19 stock_account/models/stock_move.py:659-667]`: los movimientos de
stock **no generan asientos**, porque `_should_create_account_move()` exige `real_time`. El
efecto contable solo aparece en el cierre, a partir del informe de valoración.

| Momento | A | B |
|---|---|---|
| Cesión (pasos 1-2) | El informe de valoración de A **deja de incluir** las unidades: el tránsito no tiene compañía y las ubicaciones de B no son de A `[C19 stock_location.py:36-41]` | No las incluye: propietario A `[C19 stock_move_line.py:38-45]` |
| Alquiler y devolución | Sin efecto | Sin efecto |
| Factura A → B publicada | Ingreso (700) | Compra (600) vía factura de proveedor |
| Salida del material perdido (paso 9) | Sin efecto: ya no lo valoraba | Sin efecto: propietario A |

🔴 **R1 queda confirmado.** Mientras el material está cedido, **no figura en el inventario
valorado de nadie**, aunque jurídicamente sigue siendo de A. En la 19 no existe un informe
nativo de stock consignado valorado: `_get_valued_consigned_qty` solo interviene en el coste
de un movimiento `[C19 stock_account/models/stock_move.py:273-275, 691]`.

| Opción | Qué es | Valoración |
|---|---|---|
| **V1 (recomendada)** | Tránsito estándar. En el cierre, la asesoría suma a las existencias de A «existencias en poder de terceros» con el listado nativo de quants filtrado por propietario = A | Cero código, cero hacks. Cuadra con el PGC (continental, periódico). Exige un paso manual en el cierre |
| V2 | Ubicación espejo de A dentro del almacén de B | **Descartada**: un albarán de B no admite una ubicación de otra compañía (`check_company`) y duplicaría el conteo físico |
| V3 | Sin consigna: el material pasa a ser de B al cederlo (lo que hace `enteza_prestamo_intercompania`) | Contradice el principio del encargo (propiedad ≠ ubicación) |

**Si algún día pasan a perpetuo** (`real_time`): en P1, la factura de proveedor de B cargaría
existencias sin entrada valorada. Habría que revisar la cuenta de compra de esos productos en
B. No aplica hoy y se anotará en ARCHITECTURE.md.

---

## G. Idempotencia, concurrencia y atomicidad

- **Registro de enlaces** `enteza.venta.intercompania.enlace`: una fila por línea de factura
  de B y compañía propietaria. `models.UniqueIndex('(source_move_line_id, owner_company_id)')`
  `[C19 table_objects.py:185]`. Un reintento o un proceso paralelo **falla en la base de
  datos** en vez de duplicar.
- **Bloqueo**: `lock_for_update()` sobre las líneas de alquiler afectadas, ordenadas por id,
  antes de calcular el pendiente `[C19 orm/models.py:5577]`. Serializa dos publicaciones que
  compartan línea.
- **Atomicidad**: cada factura de B se procesa dentro de un `savepoint`. O se crean todas sus
  facturas A → B, sus albaranes y sus enlaces, o nada. Un fallo de configuración no revierte
  la publicación de B: la deja **pendiente** (R7).
- **Reproceso**: el botón «Procesar venta intercompañía» llama a la misma función. Como el
  pendiente ya descuenta lo registrado, repetirlo N veces da el mismo resultado.
- **Sin cron**: en esta instancia los crones no se ejecutan (memoria del proyecto). El camino
  de recuperación es el botón.

---

## H. Código que hace falta (lista cerrada)

| Elemento | ¿Lo hace Odoo 19? | Decisión |
|---|---|---|
| Modelo `enteza.venta.intercompania.relacion`: propietaria, receptora, tarifa, diario opcional, activo. `UniqueIndex` por par | No hay nada nativo por par con diario. La tarifa sí existe por partner y compañía (`specific_property_product_pricelist`, `company_dependent`) `[C19 product/models/res_partner.py:26-29]` | **Nuevo**, pequeño. Alternativa sin modelo en K-4 |
| Modelo `enteza.venta.intercompania.enlace` (registro de enlaces, G) | No | **Nuevo** |
| `sale.order.line.enteza_rental_line_id` (Many2one a la línea de alquiler, indexado) | No: `rental_custom` solo enlaza a nivel de pedido | **Nuevo** |
| Hook `_prepare_falta_sale_line_vals(move)` en `rental_custom` + extensión que añade el enlace | No | **Cambio mínimo en `rental_custom`** (K-6) |
| Excluir las líneas de faltas de `_action_launch_stock_rule` | El contexto nativo `skip_procurement` existe `[C19 sale_stock/models/sale_order_line.py:391]`, pero aplica a todo el pedido | **Nuevo**, por línea (K-5) |
| Albarán «Material no devuelto», Alquiler → Clientes, con reserva estricta por propietario | No | **Nuevo** (K-5) |
| `_post` + reparto + factura A → B | No | **Nuevo** |
| Factura de proveedor en B | **Sí** `[EE18]` | Nada |
| Usuario para crear en A | **Sí**: `intercompany_user_id` `[EE18]` | Se reutiliza |
| Campos en la factura de B (RF-14): generada Sí/No, pendiente, factura intercompañía | No | **Nuevos**, calculados, no almacenados salvo el estado |
| Botones inteligentes: factura intercompañía, factura origen, alquiler origen | No | **Nuevos** (tres, solo visibles si hay enlace) |
| Vistas: relación (lista/formulario + menú en Contabilidad → Configuración), herencia mínima de la factura | — | **Nuevas** |
| Seguridad: `ir.model.access.csv` + reglas multiempresa sobre propietaria/receptora | — | **Nuevas** |
| Tipos de operación de cesión | No hacen falta: sirven los de salida y recepción de cada almacén | Nada |

---

## I. Riesgos R1–R7: conclusión

| | Conclusión | Evidencia | Recomendación |
|---|---|---|---|
| R1 | **Confirmado.** A deja de valorar lo cedido | `[C19 stock_location.py:36-41]` | V1 + ajuste de cierre con el listado por propietario (K-3) |
| R2 | **Confirmado** que la entrega mezcla propietarios. **Refutado** que haga el cálculo ambiguo: la devolución encadenada conserva el propietario | `[C19 stock_move.py:2138, 2146-2160]` `[EE18 sale_order_line.py:398-403]` | Fórmula de E. `restrict_partner_id` no sirve en 19 |
| R3 | Resuelto por lo existente: «Facturar las Faltas». Falta el enlace por línea y la salida física | `[RPC]` `[repo rental_custom]` | H + K-5, K-6 |
| R4 | P1. P2 no aporta nada con periódico | F | Salida Alquiler → Clientes con propietario A |
| R5 | `intercompany_user_id` de la compañía propietaria + `with_company(A)` | `[EE18 account_move.py:24]` | Se reutiliza. Cada `sudo()`/`with_user()` irá justificado en el código |
| R6 | *Synchronize Stock Moves* no aplica: exige pedido de venta y de compra, y no copia el propietario | `[EE18 sale_purchase_stock_inter_company_rules/models/stock_picking.py:13-35]` | Cesión nativa manual (K-9) |
| R7 | Disparo en `_post` solo de `out_invoice`. Las notas de crédito no hacen nada | `[C19 account_move.py:5571]` | Posponer si falta configuración (K-8) |

**Incompatibilidades que hay que decir claramente:**

- **Consigna + valoración.** Lo que tiene B de A no figura en ningún inventario valorado (R1).
  No es un fallo: es cómo decide la 19 qué se valora. Se resuelve en el cierre contable, no
  con código.
- **Rental + material perdido.** El alquiler no tiene salida nativa para lo perdido. Si el
  módulo no crea el albarán del paso 9, las unidades de A quedan como existencia fantasma en
  Alquiler.
- **Inter-Company Transactions + facturación manual actual.** Al activarlo, **cualquier**
  factura de venta de una compañía a la otra genera la de proveedor, incluida la mensual de
  reparto de gastos (`ST/2026/00001`). Nace en borrador por defecto
  (`intercompany_document_state='draft'` `[EE18 res_company.py:8-15]`).
- **`enteza_prestamo_intercompania`** mueve material entre compañías **sin propietario**: allí
  el material pasa a ser de la receptora. Son dos modelos de negocio distintos para el mismo
  hecho físico. Este módulo **no depende de él ni lo toca**, pero hay que saber cuándo se usa
  cada uno (K-10).

---

## J. Dependencias del manifiesto

```python
'depends': [
    'sale_stock_renting',          # rental_loc_id, albaranes de alquiler; arrastra sale_renting, sale_stock, stock
    'rental_custom',               # «Facturar las Faltas»: rental_order_id, qty_lost, action_create_sale_order
    'account_inter_company_rules', # intercompany_user_id y la factura de proveedor en B
],
```

`[RPC]`: los tres existen en la instancia. `account_inter_company_rules` está en estado
`uninstalled` y se instalaría como dependencia (K-1). **No** se depende de
`enteza_prestamo_intercompania` ni de `sale_purchase_stock_inter_company_rules`.

---

## K. Preguntas para decidir

**Bloqueantes**

1. **¿Instalamos `account_inter_company_rules` en producción?** Y después:
   - Activar «Generar facturas» en las dos compañías, en modo **borrador**.
   - Elegir el usuario «Crear como» de cada compañía.
   - Efecto: la factura mensual de reparto de gastos generará sola su factura de proveedor en
     Stileum. **Hay que dejar de hacerla a mano** o saldrá duplicada.
2. **¿Activamos Consigna y Tarifas en Ajustes?** Consigna es imprescindible. Tarifas hace
   visible el campo «Tarifa» en los pedidos de venta de todo el mundo.
3. **Asesoría: ¿vale V1?** El material cedido sale del inventario valorado de A y se suma en
   el cierre como «existencias en poder de terceros», con el listado de stock filtrado por
   propietario.
4. **Configuración: ¿modelo de relación (recomendado) o tarifa del partner?**
   - Modelo propio: permite elegir el diario de A. Ya existe «Facturas STILEUM» (id 46), que
     seguramente es el que corresponde.
   - Tarifa del partner (`Stileum` visto desde Vimaple → Ventas → Tarifa): no crea ningún
     modelo, pero no deja elegir diario.
   - ¿Qué diario usa A para facturar a B?

**De diseño (con recomendación)**

5. **Salida física de lo perdido.** Recomendado:
   - Crear el albarán «Material no devuelto» (Alquiler → Clientes), **para todo el material
     perdido, también el propio de B**, listo para que lo valide almacén.
   - Que la venta de faltas deje de generar su albarán desde Stock, que hoy se cancela a mano.
   - Consecuencia: el stock fantasma deja de crecer. Los 267 quants que ya hay en Alquiler son
     otro asunto, a revisar aparte.
6. **Enlace por línea: ¿tocamos `rental_custom`?** Recomendado: añadir un hook mínimo en
   `action_create_sale_order` para que este módulo guarde la línea de alquiler de origen.
   - Las faltas creadas con el **importador de hoja de cálculo** no llevan ningún enlace al
     alquiler y **no generarán factura intercompañía**. Se verán marcadas como «no
     identificable». ¿Aceptable?
7. **Si se factura menos de lo pendiente y hay varios propietarios**, ¿de quién se descuenta?
   Recomendado: primero del **tercero** (A), después del propio de B.
8. **Si falta configuración al publicar** (sin relación, sin tarifa…): ¿**posponer**
   (recomendado: se publica la factura de B, queda «pendiente» con aviso y botón para
   reprocesar) o **bloquear** la publicación?
9. **Cesión A → B**: ¿dos albaranes nativos a mano (recomendado para empezar) o un asistente
   que, al validar la salida en A, cree la recepción en B con el propietario ya puesto?
10. **Préstamo vs. cesión.** Con `enteza_prestamo_intercompania` el material pasa a ser de B;
    con este módulo sigue siendo de A. ¿Qué material va por cada camino? Si el mismo material
    puede ir por los dos, hay que decidirlo ahora.

---

**STOP.** No se empieza la Fase 2 sin aprobación explícita y respuesta a K-1 … K-4.
