# Enteza - Venta intercompañía de material perdido

Stileum no tiene material propio: alquila el que le cede Vimaple. Cuando un cliente de
Stileum no devuelve algo, Stileum le factura las faltas. Este módulo hace que, **al publicar
esa factura de faltas**, Vimaple facture a Stileum las mismas unidades **a coste**, y que
Stileum tenga su factura de proveedor, sin que nadie tenga que hacerlo a mano.

## Cambio de la 19.0.2.0.0 (2026-10-03)

La 19.0.1.x exigía un alquiler de «Cesión intercompañía» con su devolución pendiente y creaba
una venta con albarán. En la práctica los albaranes no se procesan (solo se usa el de
recogida para «Facturar las Faltas»), así que nunca había devolución pendiente y no se
generaba nada. Ahora la factura **no depende de albaranes, existencias ni alquiler de
cesión**: basta con la configuración de la compañía. Decisiones del usuario: precio = coste
del artículo en Vimaple; factura publicada sola; solo facturas de faltas nuevas (las 17
FAJ ya publicadas no se tocan); rectificativas en espejo.

## Flujo

| # | Qué pasa | Quién |
|---|---|---|
| 1 | Recogida del alquiler en Stileum: el almacén anota las faltas y pulsa «Facturar las Faltas» | Persona, Stileum |
| 2 | Se publica la factura de faltas al cliente | Persona, Stileum |
| 3 | **Al publicarla**: factura de Vimaple a Stileum por las mismas unidades de material, a coste, **publicada**, en el diario configurado | **Este módulo** |
| 4 | **Al publicarse esa**: factura de proveedor en Stileum | Inter-Company Transactions (nativo) |
| 5 | Si se emite una rectificativa de la factura de faltas («Revertir»), lo mismo en espejo: rectificativa de Vimaple al precio original y rectificativa de proveedor en Stileum | **Este módulo** + nativo |

## Qué entra y qué no

- **Entran** las líneas de **material físico** (`is_storable`) que vienen de una venta de
  faltas (su pedido lleva `rental_order_id`, que pone «Facturar las Faltas»). Se copian las
  unidades **aunque la línea vaya a 0 €** al cliente (en las FAJ reales es habitual: se cobra
  una «Valoración de artículos soportados» global).
- **No entran** servicios (portes, fianza, «Valoración de artículos soportados»), facturas
  que no son de faltas, faltas creadas con el importador de hoja de cálculo (no llevan
  `rental_order_id`), ni rectificativas de facturas que no generaron factura intercompañía.

## Casos límite

| Caso | Comportamiento |
|---|---|
| Artículo sin coste en Vimaple | La factura al cliente se publica igual y queda **«Pendiente»**, con el motivo en el historial y el botón «Procesar venta intercompañía». No se crea nada |
| Falta el diario en la configuración, periodo cerrado en Vimaple o cualquier otro error al publicar | Igual: pendiente, con el motivo |
| Publicar o procesar dos veces | Una sola factura: bloqueo de la factura y comprobación de enlaces antes de crear |
| Rectificativa por más unidades de las facturadas, o de un artículo que no estaba | Pendiente |
| Rectificativa creada a mano, sin «Revertir» | No lleva el enlace a la factura original: no se hace nada |

## Configuración

1. **Ficha de la compañía Stileum** (Ajustes → Compañías), pestaña de información general,
   bloque «Material perdido de otra compañía»:
   - **Material cedido por**: Visueña de Material Plegable.
   - **Diario de la factura intercompañía**: «Facturas STILEUM» (ST) de Vimaple. Para
     verlo en el desplegable hay que tener **las dos compañías activas** en el selector.
2. **Inter-Company Transactions** (`account_inter_company_rules`, ya instalado). En Ajustes
   → Contabilidad, **con Stileum activa**: activar «Generar facturas de proveedor y
   rectificativas», elegir el diario de compras y si se crean en borrador o publicadas. La
   regla se lee en la compañía que **recibe** la factura (código de la 18 EE:
   `company_sudo.intercompany_generate_bills_refund` del partner de la factura).
   🔴 Desde ese momento **cualquier** factura de Vimaple a Stileum (por ejemplo, la mensual
   de reparto de gastos) creará sola su factura de proveedor: **dejar de hacerla a mano** o
   saldrá duplicada.
3. Revisar con la primera factura que la cuenta de ingresos y el IVA que pone Odoo son los
   que quiere la contable (salen de la ficha del producto en Vimaple; en la vajilla, p. ej.,
   70300200 y 21 %).

🔴 **VeriFactu** está instalado y desactivado en las dos compañías (RPC del 2026-10-03). Si
se activa, estas facturas de Vimaple se enviarán a la AEAT al publicarse solas, como
cualquier otra.

## Alquiler de «Cesión intercompañía» (opcional)

Sigue disponible para cuando se lleve el stock en Odoo, pero **la factura intercompañía no
lo necesita**. Un alquiler en Vimaple con cliente Stileum marcado como cesión:

- Calcula la compañía receptora a partir del cliente (tiene que ser el contacto de otra
  compañía del grupo) y propone su almacén. Para elegir el almacén hay que tener las dos
  compañías activas en el selector.
- Pone a 0 € las líneas de material y no genera recargo por retraso.
- Al validar su entrega o su devolución, prepara en la receptora la recepción (con
  propietario Vimaple) o la salida, confirmadas y sin validar.

## Despliegue

Commit → push → `invoke git-aggregate` → Actualizar lista de aplicaciones → actualizar este
módulo. Comprobar por RPC `latest_version` = 19.0.2.0.0. Después, configuración y prueba
con una factura de faltas de un artículo.

## Pruebas

`tests/test_venta_intercompania.py` (factura) y `tests/test_cesion.py` (alquiler de cesión).
**Validadas por sintaxis, no ejecutadas**: en este hosting no hay `--test-enable`.

## Qué no se ha podido verificar en la 19

- `account_inter_company_rules` solo se ha leído en la 18 EE. Este módulo no depende de él:
  si cambiara, la factura de Vimaple se crea igual y la de proveedor se haría a mano.
- El motor de alquiler Enterprise (`sale_stock_renting`), del que dependen los albaranes
  espejo de la cesión, solo se ha leído en la 18.
