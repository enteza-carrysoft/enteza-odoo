# Enteza — Factura agrupada por familias

Añade un informe **«Factura agrupada por familias»** al desplegable de *Imprimir* de la factura.

**No sustituye a la factura oficial de Odoo**: se añade al lado. La estándar sigue disponible e
intacta, así que desinstalar este módulo no deja nada roto.

## Por qué

Dos peticiones de contabilidad del 2026-08-03:

1. **Las facturas de alquiler ocupan demasiados folios.** Medido sobre `AS/2026/01079`
   (BAJOPLATO): 60 líneas que imprimían **118 renglones**, porque 57 llevaban debajo el periodo
   de alquiler —«del 30/07/2026 13:00 al 31/07/2026 13:00»—, que es **el mismo para toda la
   factura**. Seis folios.
2. **Poder verla agrupada por familia** de producto.

Y tres más del 2026-08-04, ya con el informe impreso delante: que **salga la dirección de
envío**, que se cierre el **blanco de la cabecera**, y que los **impuestos bajen al pie**.

## Qué hace

**El periodo sale una sola vez**, en un recuadro bajo los datos de la factura, en lugar de
repetirse en cada línea. Comprobado sobre la factura real: **de 118 renglones a 61, un 48 %
menos**, y ninguna línea se queda sin descripción.

Sólo se agrupa así cuando **toda la factura viene de un único pedido de alquiler**. Si agrupa
varios pedidos, el periodo se queda en cada línea, que es lo correcto: no sería el mismo para
todas.

El recuadro va **en dos bloques**: a la izquierda el **periodo de alquiler** (sólo fechas, sin
horas) y a la derecha la **fecha del evento** (`event_date`), que es la que mira el negocio. La
**fecha de vencimiento se mantiene** donde estaba, arriba con los datos de la factura.

Cada bloque aparece sólo si hay dato: si la factura agrupa varios pedidos o varias fechas de
evento, ese lado se deja en blanco en vez de dar una fecha que no sería cierta para todas las
líneas.

**Las líneas van agrupadas por familia**, con un encabezado por familia y su subtotal. En la
factura del ejemplo: VAJILLAS (12), MANTELERÍAS (10), MENAJE (9), CRISTALERÍAS (8), MESAS (6),
CUBERTERÍAS (5), BOL Y CHUPITO (3), SILLAS (3)…

Las líneas cuyo producto no tiene familia se imprimen al final bajo **«Otros conceptos»**, para
que no se pierda ningún importe.

### Dirección de envío y cabecera (2026-08-04)

Las dos cosas eran **el mismo fallo**. Los layouts de la 19 (`external_layout_bubble` en
Vimaple, `external_layout_striped` en Stileum) esperan que el informe les rellene tres
variables: `address` (el cliente), `information_block` (el lugar de entrega) y
`layout_document_title` (el título). La primera versión maquetaba el cliente por su cuenta y
dejaba las otras dos vacías, así que el layout imprimía igualmente **sus huecos**: un `<h2>` en
blanco al lado de la dirección, y ningún sitio donde poner el envío. De ahí el espacio muerto
entre los datos de la empresa y los del cliente, y de ahí que la dirección de envío no
apareciera nunca.

Ahora se rellenan las tres, siguiendo el mismo patrón que la factura estándar de Odoo. El
**lugar de entrega sale a la izquierda del cliente**, y sólo cuando es distinto de él: en las
facturas heredadas de la 15 suele coincidir, y repetir la misma dirección dos veces no aporta
nada. En `AS/2026/01079` sí difiere («BAJOPLATO S.L» → «BAJOPLATO S.L, MOTRIL»), y hay 1.827
facturas de cliente con el campo informado.

A diferencia de la factura estándar, el bloque de entrega **no lleva restricción de grupo**.
Odoo lo esconde tras `account.group_delivery_invoice_address`; aquí se imprime siempre, porque
si un usuario de contabilidad no estuviera en ese grupo vería desaparecer la dirección sin
saber por qué.

> El margen superior del papel (52 mm del formato A4) **no se ha tocado**. Es el que trae Odoo
> y lo ocupa entero la cabecera: logo, las cuatro líneas de `company_details` y el NIF suman
> unos 50 mm a 90 ppp. Bajarlo metería la cabecera dentro del cuerpo. El blanco que sobraba
> estaba en el cuerpo, no en el margen.

### Los impuestos, en el pie (2026-08-04)

**La columna «Impuestos» desaparece de las líneas.** Aquí todo se vende al mismo tipo, así que
repetir «21% S» sesenta veces sólo gastaba ancho de papel. El dato pasa al pie de totales, entre
la base imponible y el total, con **el porcentaje y el importe**.

Se agrupa **por porcentaje**, no por impuesto. En esta base conviven `21% G` y `21% S`, que son
dos cuentas distintas para el mismo 21 %, y en el papel tienen que salir en **un solo renglón**.
Tampoco se agrupa por grupo de impuesto, que sería lo natural, porque los grupos de `enteza26`
se llaman «VAT 21%» y «Withholding 19%» —en inglés— y saldrían así impresos.

Las **retenciones no se mezclan con el IVA**: tienen porcentaje negativo, así que caen en su
propio renglón («Retención 19 %») con el importe en negativo. Cuando hay más de un tipo, cada
renglón indica además la base sobre la que se calcula.

El importe no se recalcula: se toma de las líneas de impuesto del asiento, que es lo que ya
cuadró Odoo al validar la factura.

## Qué NO hace

- **No toca los datos.** El periodo se sigue guardando en la descripción de la línea; sólo deja
  de imprimirse. Quitar el módulo devuelve todo a como estaba.
- **No cambia la factura oficial** ni la numeración ni los importes.

## Detalle técnico

`models/account_move.py` añade cuatro métodos auxiliares, **públicos a propósito** porque QWeb no
puede llamar a métodos que empiezan por `_`:

| Método | Para qué |
|---|---|
| `account.move.enteza_familias_usadas()` | familias presentes, en orden alfabético |
| `account.move.enteza_lineas_de_familia(familia)` | líneas de una familia |
| `account.move.enteza_lineas_sin_familia()` | líneas de producto sin familia |
| `account.move.enteza_pedido_alquiler()` | el pedido de alquiler, **sólo si es uno** |
| `account.move.enteza_periodo_alquiler()` | `(desde, hasta)` como fechas **sin hora** |
| `account.move.enteza_fecha_evento()` | `event_date`, si toda la factura comparte una |
| `account.move.enteza_impuestos_agrupados()` | impuestos por porcentaje, para el pie |
| `account.move.line.enteza_descripcion()` | descripción sin el renglón del periodo |

`enteza_periodo_alquiler()` convierte el huso **en Python, no en la plantilla**:
`rental_start_date` se guarda en UTC y recortar la hora sobre el valor UTC daría el día
equivocado en los alquileres que empiezan o terminan de madrugada.

`enteza_fecha_evento()` lee `event_date` del **pedido**. Existe también en la línea, pero ahí es
un related de `order_id.event_date` con `store=False`: el valor bueno está en la cabecera y
leerlo ahí evita calcularlo línea a línea. Es un `date`: no hay huso que convertir.

> **Si el bloque sale vacío, no es el informe: es que el pedido no tiene fecha de evento.** El
> campo está en el formulario del pedido y se rellena solo si alguien lo escribe. A 2026-08-03,
> 1.157 de los 1.159 pedidos de alquiler la tienen; los dos que faltan (`S00014` y `S00016`) se
> crearon en la 19 sin rellenarla. Si interesa que no vuelva a pasar, se puede hacer obligatorio
> en pedidos de alquiler — es otro módulo.

> ⚠️ **Los 16 pedidos con devolución a las 23:59.** La migración guardó su `rental_return_date`
> como `23:59:59` **UTC**, que en hora española es el día siguiente. Odoo ya los muestra así hoy
> en pantalla; este informe sólo lo hace más visible. Son pedidos de un día ya cerrados. Si se
> quiere cuadrar, hay que corregir el dato, no el informe.

El patrón que detecta el periodo exige que el renglón lleve **dos fechas**, para no borrar por
error una descripción que empiece por «del». Contempla castellano e inglés.

## Estado

Validado con `validar_vistas.py` y `validar_modulo.py`, y el patrón de limpieza probado contra
los 60 textos reales de `AS/2026/01079`.

El agrupador de impuestos se ha probado replicando su algoritmo fuera de Odoo, con los datos
reales de cinco facturas traídas por RPC. **Las cinco cuadran al céntimo** contra su
`amount_tax`:

| Factura | Caso | Resultado |
|---|---|---|
| `AS/2026/01081` | un solo tipo | IVA 21 % → 384,33 |
| `AS/2026/00483` | **dos impuestos del mismo 21 %** | un renglón: 937,16 − 286,65 = **650,51** |
| `LV/2026/00029` | **IVA + retención** | 21 % → 160,94 y −19 % → −145,62 = **15,32** |
| `AS/2026/01079` | factura migrada de la 15 | IVA 21 % → 300,91 |
| `AJ/2026/00004` | compañía Stileum | IVA 21 % → 418,11 |

⚠️ **La plantilla no se ha podido renderizar**: esta instancia no tiene entorno de pruebas, y la
clave de API no sirve para abrir sesión web, así que no hay forma de pedir el PDF desde fuera.
Lo verificado es el XML (esquema y sintaxis) y la aritmética de los impuestos. **Hay que
imprimir una factura y mirarla** antes de darlo por bueno.

> ℹ️ **Las facturas migradas de la 15 imprimen su detalle a cero.** No es el informe: en la 15
> el importe iba en una línea de resumen. `AS/2026/01079` tiene 60 líneas de detalle a 0,00 y
> una línea «TOTAL ALQUILER SEVILLA SEGÚN C.» con los 1.432,91 €. En las facturas nacidas en la
> 19 (`AS/2026/01081`, `AJ/2026/0000x`…) el detalle lleva su importe.

## Instalación

`git pull` de Xtendoo → Aplicaciones → Actualizar lista de aplicaciones → instalar
**Enteza - Factura agrupada por familias**. Después, abrir una factura de alquiler e imprimir con
la nueva opción del desplegable.
