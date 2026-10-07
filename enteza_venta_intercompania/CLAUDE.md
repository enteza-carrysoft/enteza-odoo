# CLAUDE.md — enteza_venta_intercompania

Despliegue, límites de las pruebas y sus trampas: ver el `CLAUDE.md` de la raíz del repo.

## Regla obligatoria: documento de funcionalidad

`docs/FUNCIONALIDAD.md` describe cómo funciona el módulo **ahora**, para personas no
técnicas (contabilidad, gerencia). Petición del usuario del 2026-10-07.

**Cualquier cambio que añada, quite o modifique funcionalidad de este módulo actualiza ese
documento en el mismo commit:**

1. Reescribir las secciones afectadas para que describan el comportamiento nuevo, no
   añadir parches del tipo «antes era… ahora es…».
2. Añadir una fila al **Historial de cambios** (versión, fecha, qué cambia).
3. Actualizar la versión y la fecha de la cabecera.

Un cambio puramente interno (refactor sin efecto visible) no necesita fila, pero si cambia
algo que el usuario ve o una regla de cálculo, sí. El `README.md` es la referencia
técnica; `FUNCIONALIDAD.md` es la funcional: no copiar uno en el otro.
