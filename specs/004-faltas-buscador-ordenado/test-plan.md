# Test plan

Pruebas Python escritas y **no ejecutadas** (producción sin `--test-enable`). Lo marcado `ui` se
comprueba en pantalla tras desplegar, con un pedido de alquiler confirmado de más de 40 líneas
(abrir «Registrar faltas» y **cancelar** sin facturar).

| AC | Scenario | Layer (static/server/rpc/ui/tests/manual) | Status |
|----|----------|--------------------------------------------|--------|
| AC1 | `test_faltas_buscador.test_lineas_ordenadas_por_referencia` (referencias desordenadas + una sin referencia) | tests | pending |
| AC2 | `test_faltas_buscador.test_referencia_en_linea` + columna «Referencia» y nombre sin `[código]` en pantalla | tests + ui | pending |
| AC3 | `test_faltas_buscador.test_vista_sin_paginacion` (atributo `limit` ≥ 500 y `widget`) + sin paginador en pantalla | tests + ui | pending |
| AC4 | Teclear «48» / parte del nombre / con acento; vaciar | ui | pending |
| AC5 | Intro en el buscador con y sin coincidencias | ui | pending |
| AC6 | Intro en «Faltas» con buscador lleno (vuelve al buscador) y vacío (baja) | ui | pending |
| AC7 | Flechas ↑/↓ en «Faltas», con filtro y tras reordenar por cabecera; ↑ en la primera | ui | pending |
| AC8 | Interruptor «Solo con faltas» + contador | ui | pending |
| AC9 | `test_faltas_buscador.test_faltas_en_todas_las_lineas_se_facturan` + en pantalla: falta en fila filtrada y oculta, Cancelar (no facturar) | tests + ui | pending |
| AC10 | Escape con texto (no cierra), Intro/flechas no facturan | ui | pending |
| AC11 | Validadores (`odoo_validate`, `validar_vistas.py`, `validar_modulo.py`); manifiesto solo con la carpeta nueva; CSV sin filas nuevas; sin `patch(`; pruebas previas sin modificar | static | pass |
