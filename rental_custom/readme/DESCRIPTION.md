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

## Volver a trabajar con albaranes

Reactivar «Traslado de alquiler» en Alquiler → Ajustes. Los pedidos nuevos vuelven a generar
entrega y recogida, y el botón del pedido se oculta solo en cuanto el pedido tiene
albaranes. Antes conviene un inventario de corte con las existencias reales.
