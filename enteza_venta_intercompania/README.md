# Enteza - Venta intercompañía de material perdido

Vimaple cede material a Stileum con un **alquiler de cesión** (meses, precio simbólico).
Stileum lo alquila a sus clientes. Cuando un cliente no devuelve algo y Stileum le factura
las faltas, este módulo prepara **en Vimaple la factura a Stileum, en borrador**, por las
mismas unidades, con el precio de la tarifa que Vimaple tenga para Stileum, y las descuenta
del alquiler de cesión.

Enfoque decidido el 2026-09-28 en lugar de la consigna pura que describe
`docs/FASE1_ANALISIS.md`: con el alquiler, Vimaple sigue teniendo el material en su
inventario valorado (la ubicación de Alquiler es suya) y no hace falta repartir pérdidas por
propietario, porque Stileum no tiene material propio de esos productos.

## Flujo

| # | Qué pasa | Quién |
|---|---|---|
| 1 | Pedido de alquiler en Vimaple, cliente Stileum, marcado **«Cesión intercompañía»** con su almacén receptor. Las líneas de material salen solas a 0 €; se añade a mano una línea de servicio «Cuota de cesión» con el importe simbólico | Persona, Vimaple |
| 2 | Entrega del alquiler de cesión (Stock → Alquiler de Vimaple) | Persona, Vimaple |
| 3 | **Al validar la entrega**: recepción preparada en el almacén receptor, con propietario = Vimaple | **Este módulo** (la valida una persona de Stileum) |
| 4 | Stileum alquila, entrega y recoge como siempre | Stileum |
| 5 | Faltas: «Facturar las Faltas» y factura al cliente | Persona, Stileum |
| 6 | **Al publicar esa factura**: venta de Vimaple a Stileum confirmada, su **factura en borrador** en el diario de faltas intercompañía de la cesión, y descuento en el alquiler de cesión | **Este módulo** |
| 7 | Revisar y **publicar** la factura; validar el albarán de la venta (sale de Alquiler) | Persona, Vimaple |
| 8 | Factura de proveedor en Stileum | Inter-Company Transactions (nativo) |
| 9 | Fin de la cesión (total o parcial): Vimaple valida la devolución del alquiler de cesión | Persona, Vimaple |
| 10 | **Al validarla**: salida preparada en Stileum por las unidades devueltas | **Este módulo** (la valida una persona de Stileum) |

Ninguna factura se publica sola y ningún albarán se valida solo. Lo único que se confirma
sin intervención es la venta de Vimaple a Stileum, y solo para poder crear su factura.

## Qué hace el módulo

- **`sale.order.enteza_cesion_intercompania`**: marca el alquiler de cesión. El cliente tiene
  que ser el contacto de otra compañía del grupo (`enteza_cesion_company_dest_id`), y al
  confirmar hace falta el almacén receptor (`enteza_cesion_warehouse_dest_id`).
- **Precio**: las líneas de material de una cesión van a 0 € y no generan recargo por retraso.
- **Albaranes espejo** (`stock.picking.enteza_cesion_origen_picking_id`): al validar la
  entrega o una devolución de la cesión, se prepara en la receptora la recepción (desde
  Proveedores, con propietario la dueña) o la salida (hacia Clientes). Uno por albarán de
  origen, confirmado y sin validar. No usan el tránsito intercompañía: en la 19 exige
  existencias para reservar, y la dueña no deja nada en él.
- **Al publicar una factura de cliente** (`account.move._post`), toma las líneas de material
  que vienen de una venta de faltas (su pedido lleva `rental_order_id`), busca devoluciones
  pendientes de alquileres de cesión hacia esa compañía y las reparte por fecha.
- Anota esas unidades en la columna «Faltas» de la devolución de la cesión y llama a
  «Facturar las Faltas» de `rental_custom`, que crea el presupuesto, descuenta la demanda y
  deja el resto pendiente.
- **Enlaces** (`enteza.venta.intercompania.enlace`): línea de factura → alquiler de cesión →
  venta → factura intercompañía. Botón «Factura intercompañía» en la factura de faltas.
- **Diario**: el de «Diario de faltas intercompañía» de la cesión (en Enteza, «Facturas
  STILEUM»). Obligatorio al confirmar la cesión.

### Casos límite

| Caso | Comportamiento |
|---|---|
| Producto sin ninguna cesión hacia esa compañía | Se ignora: es material propio |
| Se factura más de lo que queda pendiente en las cesiones | La factura se publica igual y queda **«Pendiente»**, con el motivo en el historial y el botón «Procesar venta intercompañía». No se crea nada |
| Faltas anotadas a mano en la devolución de la cesión | Pendiente, hasta que se facturen o se borren |
| Publicar o procesar dos veces | Una sola venta: bloqueo de la factura y comprobación de enlaces antes de crear |
| Nota de crédito al cliente o devolución física posterior | Nada automático. Se corrige a mano con el enlace a la vista |
| Faltas creadas con el importador de hoja de cálculo | No llevan enlace al alquiler y no entran |

## Configuración antes de instalar

1. **Actualizar `rental_custom` a 19.0.1.14.0** antes que este módulo. Aporta la facturación
   de faltas parcial, el precio por tarifa y la salida de lo perdido desde Alquiler.
2. **Inter-Company Transactions** (`account_inter_company_rules`): instalarlo, activar
   «Generar facturas de proveedor» en borrador en las dos compañías y elegir el usuario.
   🔴 Desde ese momento la factura mensual de reparto de gastos Vimaple → Stileum generará
   sola su factura de proveedor: **dejar de hacerla a mano** o saldrá duplicada.
3. **Tarifas**, en este orden:
   1. Crear «Tarifa general», sin reglas y con la secuencia más baja.
   2. Activar Tarifas en Ajustes. 🔴 Si se activan con solo la tarifa especial, Odoo se la
      aplica a **todos** los clientes (`product.pricelist._get_partner_pricelist_multi`).
   3. Crear «Intercompañía Stileum» con las reglas de venta del material perdido.
   4. Con la compañía Vimaple activa, asignarla en la ficha del contacto Stileum → Ventas.

   Las reglas de tarifa no cambian el precio de alquiler: por eso la cuota simbólica va en
   una línea de servicio (decisión A del 2026-09-28).
4. **Consigna** (propietarios de stock) en Ajustes de Inventario, para recibir en Stileum con
   propietario Vimaple y que Stileum no lo valore como existencia suya.
5. La asesoría tiene que validar el precio simbólico de la cesión (operación vinculada).

Para abrir la venta de Vimaple desde una factura de Stileum hay que tener **las dos
compañías activas** en el selector.

## Despliegue

Commit → push → `invoke git-aggregate` → Actualizar lista de aplicaciones → actualizar
`rental_custom` → instalar este módulo. Comprobar por RPC `state` y `latest_version`.

## Pruebas

`tests/test_venta_intercompania.py` y `rental_custom/tests/test_facturar_faltas.py`.
**Validadas por sintaxis, no ejecutadas**: en este hosting no hay `--test-enable`. Antes de
darlo por bueno, hacer una prueba real guiada con una cesión de 1 artículo.

## Qué no se ha podido verificar en la 19

- El motor de alquiler Enterprise (`sale_stock_renting`) sólo se ha leído en la 18: que la
  devolución de alquiler sale de `rental_loc_id` y que `_action_done` sólo suma a
  `qty_returned` los movimientos con línea de alquiler.
- Los campos de `account_inter_company_rules`: el módulo no depende de ellos para no fallar
  si cambiaron de nombre.
