## 19.0.1.21.0 (2026-10-22)

- Envases (spec 007): desaparece la ventana de aviso al elegir el artículo o cambiar la
  cantidad. Ahora la celda «Nº envases» se pone en naranja cuando la cantidad de la línea de
  alquiler no es múltiplo del envase (campo calculado `enteza_envase_no_multiplo`). La cabecera
  explica el color al pasar el ratón. Sin cambios por API.

## 19.0.1.20.0 (2026-10-22)

- Envases (spec 006): la cantidad no múltiplo del envase deja de rechazarse y pasa a ser una
  advertencia al elegir el artículo o cambiar la cantidad (onchange). Los pedidos creados por
  API se guardan sin error. Se mantiene el rechazo de una unidad distinta de la base.

## 19.0.1.19.0 (2026-10-21)

- Envases en las líneas de alquiler: campo «Nº envases», regla de múltiplos y de unidad base
  (spec 005).
- Parte de recogida: imprime todas las líneas de alquiler y añade la columna «Pedido».
