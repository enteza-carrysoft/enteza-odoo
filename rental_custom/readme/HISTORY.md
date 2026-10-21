## 19.0.1.20.0 (2026-10-22)

- Envases (spec 006): la cantidad no múltiplo del envase deja de rechazarse y pasa a ser una
  advertencia al elegir el artículo o cambiar la cantidad (onchange). Los pedidos creados por
  API se guardan sin error. Se mantiene el rechazo de una unidad distinta de la base.

## 19.0.1.19.0 (2026-10-21)

- Envases en las líneas de alquiler: campo «Nº envases», regla de múltiplos y de unidad base
  (spec 005).
- Parte de recogida: imprime todas las líneas de alquiler y añade la columna «Pedido».
