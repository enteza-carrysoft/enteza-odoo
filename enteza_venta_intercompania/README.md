# Enteza - Venta intercompañía de material perdido

Vimaple cede material a Stileum con un **alquiler de cesión** (meses, precio simbólico).
Stileum lo alquila a sus clientes. Cuando un cliente no devuelve algo y Stileum le factura
las faltas, este módulo prepara **en Vimaple un presupuesto de venta a Stileum** por las
mismas unidades, con el precio de la tarifa que Vimaple tenga para Stileum, y las descuenta
del alquiler de cesión.

Enfoque decidido el 2026-09-28 en lugar de la consigna pura que describe
`docs/FASE1_ANALISIS.md`: con el alquiler, Vimaple sigue teniendo el material en su
inventario valorado (la ubicación de Alquiler es suya) y no hace falta repartir pérdidas por
propietario, porque Stileum no tiene material propio de esos productos.

## Flujo

| # | Qué pasa | Quién |
|---|---|---|
| 1 | Pedido de alquiler en Vimaple, cliente Stileum, marcado **«Cesión intercompañía»**. Líneas de material a 0 € y una línea de servicio «Cuota de cesión» con el importe simbólico | Persona, Vimaple |
| 2 | Entrega del alquiler de cesión (Stock → Alquiler de Vimaple) | Persona, Vimaple |
| 3 | Recepción en Stileum con propietario = Vimaple | Persona, Stileum |
| 4 | Stileum alquila, entrega y recoge como siempre | Stileum |
| 5 | Faltas: «Facturar las Faltas» y factura al cliente | Persona, Stileum |
| 6 | **Al publicar esa factura**: presupuesto de Vimaple a Stileum en borrador y descuento en el alquiler de cesión | **Este módulo** |
| 7 | Revisar, confirmar y facturar el presupuesto; validar su albarán (sale de Alquiler) | Persona, Vimaple |
| 8 | Factura de proveedor en Stileum | Inter-Company Transactions (nativo) |

Nada se confirma, se publica ni se mueve solo.

## Qué hace el módulo

- **`sale.order.enteza_cesion_intercompania`**: marca el alquiler de cesión. El cliente tiene
  que ser el contacto de otra compañía del grupo (`enteza_cesion_company_dest_id`).
- **Al publicar una factura de cliente** (`account.move._post`), toma las líneas de material
  que vienen de una venta de faltas (su pedido lleva `rental_order_id`), busca devoluciones
  pendientes de alquileres de cesión hacia esa compañía y las reparte por fecha.
- Anota esas unidades en la columna «Faltas» de la devolución de la cesión y llama a
  «Facturar las Faltas» de `rental_custom`, que crea el presupuesto, descuenta la demanda y
  deja el resto pendiente.
- **Enlaces** (`enteza.venta.intercompania.enlace`): línea de factura → alquiler de cesión →
  presupuesto. Botón «Venta intercompañía» en la factura.

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
