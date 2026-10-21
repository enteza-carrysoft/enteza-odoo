**Pedir en múltiplos (aviso, no bloqueo).** Al elegir el artículo o cambiar la cantidad de una
línea de alquiler con envase que no es múltiplo, sale el aviso «BOL BARCO (25): 30 uds no es
múltiplo del envase de 25. Prueba con 25 o 50.»; se puede guardar igualmente. Los pedidos que
llegan por la integración (API) se crean sin aviso ni error. Lo que sí se rechaza es una unidad
distinta de la base: la línea tiene que ir en Units (los envases se calculan solos en «Nº
envases»).

**Líneas antiguas y duplicados.** Los pedidos con cantidades no múltiplo siguen funcionando
(entregar, devolver, facturar y duplicar) sin ningún mensaje.

**Parte de recogida.** Imprimir «Pickup and Return Receipt» desde el pedido de alquiler: salen
todas las líneas con la columna «Pedido» (por ejemplo «50 uds (2 envases de 25)»).

**Botón «+» del catálogo de productos.** Suma de uno en uno y guarda al momento; con envase
sale el aviso de múltiplo, pero la línea se guarda.
