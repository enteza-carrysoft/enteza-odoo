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
| `account.move.line.enteza_descripcion()` | descripción sin el renglón del periodo |

`enteza_periodo_alquiler()` convierte el huso **en Python, no en la plantilla**:
`rental_start_date` se guarda en UTC y recortar la hora sobre el valor UTC daría el día
equivocado en los alquileres que empiezan o terminan de madrugada.

`enteza_fecha_evento()` lee `event_date` de las **líneas de pedido**, no del pedido, porque el
campo existe en los dos sitios y así también sale cuando la factura agrupa varios pedidos del
mismo evento. Es un `date`: no hay huso que convertir.

> ⚠️ **Los 16 pedidos con devolución a las 23:59.** La migración guardó su `rental_return_date`
> como `23:59:59` **UTC**, que en hora española es el día siguiente. Odoo ya los muestra así hoy
> en pantalla; este informe sólo lo hace más visible. Son pedidos de un día ya cerrados. Si se
> quiere cuadrar, hay que corregir el dato, no el informe.

El patrón que detecta el periodo exige que el renglón lleve **dos fechas**, para no borrar por
error una descripción que empiece por «del». Contempla castellano e inglés.

## Estado

Validado con `validar_vistas.py` y `validar_modulo.py`, y el patrón de limpieza probado contra
los 60 textos reales de `AS/2026/01079`.

⚠️ **No se ha podido ejecutar en Odoo**: esta instancia no tiene entorno de pruebas ni acceso a
`odoo-bin --test-enable`. Hay que instalarlo y comprobar la salida antes de darlo por bueno.

## Instalación

`git pull` de Xtendoo → Aplicaciones → Actualizar lista de aplicaciones → instalar
**Enteza - Factura agrupada por familias**. Después, abrir una factura de alquiler e imprimir con
la nueva opción del desplegable.
