## 19.0.2.2.0 (2026-10-22)

- Envases (spec 006): la cantidad no múltiplo del envase ya no se rechaza. El guardado guarda lo
  tecleado y la rejilla muestra el aviso; el envío no se rechaza por este motivo.
- «Repetir pedido» copia todas las líneas y avisa de las que no son múltiplo (solo omite una
  unidad distinta de la base, que el backend no admite).

## 19.0.2.1.0 (2026-10-21)

- Envases (spec 005): el guardado y el envío rechazan las cantidades no múltiplo del envase con
  el mismo mensaje que el backend, sin guardar nada de ese envío.
- «Repetir pedido» omite las líneas que ya no cumplen la regla de envases y avisa de ellas.
- La definición de envase del portal pasa a delegar en `rental_custom`.
