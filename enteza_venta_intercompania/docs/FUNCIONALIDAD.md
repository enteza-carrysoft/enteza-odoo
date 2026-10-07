# Venta intercompañía de material perdido — cómo funciona

> **Documento vivo.** Describe cómo funciona el módulo **ahora**. Se actualiza en el mismo
> commit que cualquier cambio de funcionalidad, y cada cambio se anota en el
> [historial](#historial-de-cambios) del final.
>
> Versión descrita: **19.0.2.1.0** · Última revisión: 2026-10-07

## En una frase

Cuando **Stileum** factura las faltas a su cliente (material que no se ha devuelto), Odoo
crea y publica sola la factura de **Vimaple a Stileum** por esas mismas unidades, a coste
y con los mismos descuentos. Con esa factura, Stileum recibe automáticamente su factura de
proveedor.

## Por qué existe

Stileum no tiene material propio, porque alquila el de Vimaple. Si un cliente de Stileum
pierde o rompe algo, Stileum se lo cobra, pero el material era de Vimaple, así que Vimaple
tiene que facturárselo a Stileum.

## Qué hace cada uno

| # | Qué pasa | Quién |
|---|---|---|
| 1 | En la recogida del alquiler, el almacén anota las faltas y pulsa «Facturar las Faltas» | Persona (Stileum) |
| 2 | Se publica la factura de faltas al cliente (diario «FALTAS STILEUM», FAJ) | Persona (Stileum) |
| 3 | **Al publicarla**, se crea y **publica** la factura de Vimaple a Stileum en el diario «Facturas STILEUM» (ST) | Este módulo |
| 4 | **Al publicarse esa**, se crea la factura de proveedor en Stileum, **en borrador** | Inter-Company (Odoo) |
| 5 | Contabilidad revisa y publica la factura de proveedor | Persona (Stileum) |

Las **rectificativas** siguen el mismo camino. Si se rectifica una factura de faltas con
«Revertir», Vimaple emite la rectificativa a Stileum y Stileum recibe la suya de proveedor.

## Cómo se calcula cada línea

| Dato | De dónde sale |
|---|---|
| Artículos y unidades | Las mismas líneas de **material** (artículos físicos) de la factura de faltas. Se copian aunque al cliente se le cobren a 0 € |
| Precio | El **coste** del artículo en Vimaple |
| **Descuento** | El de la línea del artículo en la factura de faltas. **Si esa línea no tiene descuento**, el descuento general de la factura, que es el de «Valoración de artículos soportados» |
| Cuenta e IVA | Los de la ficha del producto en Vimaple (en vajilla, 70300200 y 21 %) |
| Fecha | La de la factura de faltas |

En una **rectificativa**, el precio y el descuento son los de la factura de Vimaple
original, aunque el coste haya cambiado después. Así se anula exactamente lo que se cobró.

**Ejemplo.** FAJ/2026/00008 tiene 4 artículos con un 40 % y el resto sin descuento, más la
«Valoración» con un 50 %. En la factura de Vimaple esos 4 artículos llevan el 40 % y todos
los demás el 50 %.

## Qué NO entra

- Servicios: portes, fianza, la propia «Valoración», rappels…
- Facturas que no son de faltas.
- Faltas creadas con el importador de hoja de cálculo, porque no llevan el enlace con el
  alquiler (para facturas antiguas ver [Facturas anteriores al módulo](#facturas-anteriores-al-módulo)).
- Rectificativas de facturas de faltas que no generaron factura de Vimaple, o creadas a
  mano sin «Revertir».

## Cuando algo no cuadra: «Pendiente»

La factura al cliente **nunca se bloquea**. Si no se puede crear la de Vimaple, la factura
de faltas queda marcada **«Pendiente»**: el motivo aparece en su historial y en ella hay un
botón **«Procesar venta intercompañía»** para reintentarlo cuando esté resuelto.

| Motivo | Qué hacer |
|---|---|
| Un artículo no tiene coste en Vimaple | Ponerle coste y pulsar el botón |
| Falta el diario en la configuración, o el periodo de Vimaple está cerrado | Corregirlo y pulsar el botón |
| La factura tiene **varios descuentos generales distintos** (p. ej. dos «Valoración» con 99 % y 50 %) | No se adivina cuál aplicar. Dejar uno solo, o crear la factura de Vimaple a mano |
| Rectificativa de más unidades de las facturadas, o de un artículo que no estaba | Revisar la rectificativa |

Publicar o procesar dos veces la misma factura **no duplica** nada.

## Dónde se ve

- En la factura de faltas: el botón **«Factura intercompañía»** abre la factura de Vimaple.
- En la factura de Vimaple: la referencia es la factura de faltas, y el historial lo indica.
- En la factura de proveedor de Stileum: «Generada automáticamente desde ST/…».

## Configuración

1. **Ficha de la compañía Stileum**, bloque «Material perdido de otra compañía»:
   - **Material cedido por**: Visueña de Material Plegable.
   - **Diario de la factura intercompañía**: «Facturas STILEUM» (ST) de Vimaple. Para verlo
     en el desplegable hay que tener las dos compañías activas.
2. **Diario de faltas** de cada compañía (lo pone «Facturar las Faltas», módulo
   `rental_custom`): Stileum FAJ, Vimaple FA.
3. **Inter-Company**: Ajustes → Ajustes generales → «Empresas» → «Transacciones entre
   empresas» → «Crear facturas de proveedor», **con Stileum activa**. Estado: borrador.
   En Vimaple debe quedar desactivado.

⚠️ Con Inter-Company activo, **cualquier** factura de Vimaple a Stileum (por ejemplo, la de
reparto de gastos) crea sola su factura de proveedor: ya no hay que hacerla a mano.

⚠️ **Volver a publicar** una factura de Vimaple a Stileum (pasarla a borrador y publicarla)
crea **otra** factura de proveedor en Stileum. Antes hay que borrar la anterior.

⚠️ **VeriFactu** está instalado pero desactivado. Si se activa, estas facturas automáticas
se enviarán a la AEAT como cualquier otra.

## Facturas anteriores al módulo

Las facturas de faltas emitidas antes de instalar el módulo no generaron nada. Para
generarlas existe una acción que **solo se lanza por RPC** y solo puede usarla un
administrador de contabilidad:

```
account.move.action_enteza_ic_generar_historico(fecha)
```

Crea la factura de Vimaple con la **fecha indicada**. Como los pedidos de faltas antiguos
pueden no llevar el enlace con el alquiler, en este caso basta con que la factura esté en
el diario de faltas de su compañía: se toma todo su material. Calcula precio y descuento
igual que en el uso normal.

## Alquiler de «Cesión intercompañía» (opcional)

La factura **no lo necesita**. Queda disponible para cuando se lleve el stock entre
compañías en Odoo: un alquiler de Vimaple a Stileum marcado como cesión pone el material a
0 €, no cobra recargo por retraso y, al validar la entrega o la devolución, prepara en
Stileum la recepción (con propietario Vimaple) o la salida, sin validarlas.

## Historial de cambios

| Versión | Fecha | Cambio |
|---|---|---|
| 19.0.2.1.0 | 2026-10-07 | Los **descuentos** pasan a la factura de Vimaple (el de la línea o, si no tiene, el de «Valoración»). Acción para **facturas anteriores al módulo** con fecha a elegir. Con ella, las 17 FAJ previas (01-08 a 22-09) se facturan a 30-09-2026: las 9 que ya existían se corrigieron (ST/2026/00002–00010) y las 8 restantes se generaron (ST/2026/00011–00018), con sus facturas de proveedor en borrador |
| 19.0.2.0.0 | 2026-10-03 | Rehecho a **«solo facturación»**: la factura ya no depende de albaranes ni de la cesión. Precio a coste, publicada sola, rectificativas en espejo. Configuración en la ficha de Stileum |
| 19.0.1.1.0 | 2026-09-28 | Albaranes espejo de la cesión; la venta de Vimaple se confirma y su factura queda en borrador |
| 19.0.1.0.0 | 2026-09-28 | Primera versión: venta de Vimaple a Stileum del material perdido en una cesión |

Pruebas automáticas: escritas en `tests/`, **no ejecutadas** (el hosting no lo permite).
Lo verificado en real está en el historial de la versión correspondiente.
