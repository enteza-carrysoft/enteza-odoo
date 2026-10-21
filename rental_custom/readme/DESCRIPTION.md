Personalizaciones del alquiler de Enteza: fecha de evento obligatoria, días facturables,
cambio de número del presupuesto y facturación del material no devuelto («faltas»).

## Faltas: dos caminos que conviven

- **Desde el albarán de recogida** («Facturar las Faltas» y la columna «Faltas»). Es el
  camino cuando los alquileres generan albaranes («Traslado de alquiler» activado en
  Alquiler → Ajustes).
- **Desde el pedido de alquiler** («Registrar faltas», desde la `19.0.1.16.0`). Solo aparece
  cuando el pedido no tiene albaranes abiertos. Se anotan las faltas de cada artículo y:
  - si hay faltas, se crea el mismo pedido de faltas que en el otro camino. Al confirmarlo,
    su salida de almacén se valida sola: la baja del material queda hecha y enlazada a la
    factura, así que **no hay que hacer la baja a mano**;
  - en todos los casos, el pedido de alquiler pasa a «Devuelto».

Los dos caminos acumulan en «No devueltas (facturadas)» de la línea y no dejan facturar más
faltas que lo alquilado.

## Registrar faltas con muchas líneas (desde la `19.0.1.17.0`)

Las líneas salen en el mismo orden que el pedido de alquiler (el del papel impreso, desde la
`19.0.1.17.1`) y todas en una página. Encima de la lista:

- **Buscador**: deja solo los artículos cuya referencia empieza por lo escrito o cuyo nombre
  lo contiene. Intro salta a las faltas del primero; Intro en «Faltas» vuelve al buscador
  vacío. Escape con texto solo vacía el buscador.
- **Flechas ↑ ↓** en «Faltas»: recorren la columna como en una hoja de cálculo.
- **«Solo con faltas»** y el contador, para repasar antes de facturar.

Filtrar no borra nada: lo escrito en artículos ocultos también se factura.

## Volver a trabajar con albaranes

Reactivar «Traslado de alquiler» en Alquiler → Ajustes. Los pedidos nuevos vuelven a generar
entrega y recogida, y el botón del pedido se oculta solo en cuanto el pedido tiene
albaranes. Antes conviene un inventario de corte con las existencias reales.

## Envases en las líneas de alquiler (desde la `19.0.1.19.0`)

Muchos artículos se alquilan por envases completos (bandejas, cestas, cajas): «BOL BARCO (25)».
Un **envase** es una unidad de medida («Envase de 25», unidad de referencia Units, contiene 25)
añadida en «Envases» de la ficha del artículo. La línea sigue yendo en **unidades** y al precio
de la **unidad suelta**; el módulo no toca el cálculo de precios.

- **Regla de múltiplos**: en una línea de alquiler de un artículo con envase, la cantidad tiene
  que ser múltiplo del envase (25, 50, 75…; el cero se acepta). Si no, el guardado se rechaza
  con un mensaje que dice el artículo, la cantidad y los múltiplos más cercanos. La unidad de la
  línea tiene que ser la unidad base del artículo (Units), no el envase.
- **«Nº envases»**: columna de solo lectura junto a la cantidad en el pedido de alquiler
  (50 uds con envase de 25 → 2; 30 uds en una línea antigua → 1,2). Vacía si el artículo no
  tiene envase.
- **Parte de recogida** («Pickup and Return Receipt»): imprime ahora **todas** las líneas de
  alquiler (antes solo las ya recogidas), con una columna nueva «Pedido» («50 uds (2 envases de
  25)») antes de «Recogido» y «Devuelto». Se siguen imprimiendo las líneas no de alquiler con
  algo entregado.
- **Portal de clientes** (`enteza_portal_pedidos`): rechaza las cantidades no múltiplo con el
  mismo mensaje y «Repetir pedido» omite y avisa de las líneas que ya no cumplen.

Qué NO cambia: el precio (por unidad suelta), la venta normal, los pedidos de faltas, los
artículos sin envase y las líneas ya existentes (solo se validan al cambiar su cantidad,
producto o unidad).
