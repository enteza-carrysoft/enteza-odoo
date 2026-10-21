## 19.0.2.1.0 (2026-10-21)

- Envases (spec 005): el guardado y el envío rechazan las cantidades no múltiplo del envase con
  el mismo mensaje que el backend, sin guardar nada de ese envío.
- «Repetir pedido» omite las líneas que ya no cumplen la regla de envases y avisa de ellas.
- La definición de envase del portal pasa a delegar en `rental_custom`.
