Portal de pedidos de alquiler: el cliente, con sus credenciales del portal, monta su propia
solicitud de material para un evento en una rejilla tipo hoja de cálculo (pensada para pedidos
de 80-100 líneas), con filtros por categoría y por las dimensiones de búsqueda que el negocio
configure (marca, modelo, color...), un semáforo de disponibilidad orientativo y control de
envases cerrados.

La solicitud **es** un pedido de alquiler (`sale.order`) en borrador. Al enviarla, el comercial
asignado recibe un aviso (chatter y actividad) y decide si confirma o contrapropone. El cliente
sigue la traza (solicitud, presupuesto, pedido, factura, cobro) con las páginas nativas del
portal de Odoo 19.

No es comercio electrónico: no instala `website` ni `website_sale`, solo `portal`, y no hay
pago online. La disponibilidad la calcula el motor nativo de `sale_stock_renting`.

## Envases (desde la `19.0.2.1.0`)

Los artículos con un envase configurado (unidad «Envase de N» en «Envases» de la ficha,
definida en `rental_custom`) solo se pueden pedir en múltiplos de N unidades:

- Al guardar, si alguna cantidad nueva o modificada no es múltiplo, **no se guarda nada de ese
  envío** y la rejilla muestra el mensaje, por ejemplo «BOL BARCO (25): 30 uds no es múltiplo
  del envase de 25. Prueba con 25 o 50.». Lo tecleado sigue en pantalla.
- Al enviar la solicitud se aplica el mismo mensaje, también a solicitudes que ya tenían
  cantidades no múltiplo guardadas antes de configurar el envase.
- «Repetir pedido» copia un pedido anterior pero **omite** las líneas que ya no cumplen la
  regla de envases y avisa de cuáles y por qué.
