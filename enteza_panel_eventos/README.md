# Enteza · Panel de eventos del día

Reproduce en Odoo la pantalla de control diario de la aplicación de gestión que Enteza usaba
antes: **tres bloques sincronizados en una sola pantalla**, pivotando sobre `event_date` (el día
del evento), no sobre `rental_start_date` (el día en que el material sale del almacén).

**Alquiler → Pedidos → Panel de eventos.**

```
┌──────────────┬────────────────────────────────┐
│ CALENDARIO   │ MATERIAL DEL DÍA               │
│ del mes,     │ artículos de todos los pedidos │
│ días         │ del día, agrupados por         │
│ coloreados   │ artículo y sumando unidades    │
├──────────────┴────────────────────────────────┤
│ PEDIDOS DEL DÍA                               │
│ nº · cliente · lugar · salida · estado · total│
└───────────────────────────────────────────────┘
```

## Relación con `enteza_calendario_eventos`

Son **módulos independientes que pueden convivir**: no comparten código ni se pisan.

| Módulo | Qué es |
|---|---|
| `enteza_calendario_eventos` | Una vista calendario nativa de Odoo, pivotada en `event_date` |
| `enteza_panel_eventos` (éste) | Una pantalla propia (acción cliente OWL) con los tres bloques |

## Cómo está hecho

**Backend** — `models/sale_order.py`, dos métodos `@api.model` que el JS llama por RPC:

- `enteza_panel_carga_mes(anio, mes)` → `{'2026-07-31': {'pedidos': 3, 'importe': 4520.5}}`,
  para colorear los días.
- `enteza_panel_dia(dia)` → pedidos, artículos y totales de ese día.

Las agregaciones se hacen **en Python sobre un `search_read`, no con `_read_group`**. Es
deliberado: el volumen es pequeño (1.153 pedidos de alquiler en total; un mes son decenas) y así
el código no depende de una firma de `_read_group` que en este entorno no se puede probar. Si el
volumen crece, se cambia ahí sin tocar el JS.

**Frontend** — acción cliente OWL registrada como `enteza_panel_eventos.panel` en
`registry.category("actions")`, con su plantilla y su SCSS en `static/src/`.

### Decisiones que conviene conocer

- **Se excluyen los pedidos cancelados** y los que no tienen `event_date`.
- **Los días se colorean por número de pedidos**, con cortes en 3 y 6 (`nivelCarga` en el JS).
  Son una primera aproximación: conviene ajustarlos cuando haya datos reales de carga.
- La escala de color es monocroma sobre el color de marca, no un semáforo rojo/amarillo:
  aquí «muchos pedidos» es un buen día de trabajo, no una alarma.
- **La columna «Lugar de entrega» sale vacía si coincide con el cliente.** Hoy en `enteza26`
  coinciden en los 1.153 pedidos, así que estará vacía hasta que se informen direcciones de
  entrega propias.
- **La columna «Existencias» saldrá a 0**: `stock.quant` está vacío en `enteza26`. No es un
  fallo del panel, es que el inventario aún no se ha cargado.
- Se excluyen las líneas de sección y de nota (`display_type`), que no son material.
- Las horas se muestran en la **zona horaria del usuario**, no en UTC
  (`fields.Datetime.context_timestamp`).
- En el JS, la conversión de fecha a clave **no usa `toISOString()`** a propósito: convierte a
  UTC y en zonas al este de Greenwich devuelve el día anterior a partir de cierta hora, que es
  justo el error que haría mostrar los pedidos del día equivocado.

## Multi-compañía

No hay filtro de compañía explícito: se confía en las reglas de registro de Odoo, que ya limitan
`sale.order` a las compañías activas del usuario. El panel muestra lo que el usuario podría ver
en cualquier lista de pedidos.

## Instalación

Despliegue por `git pull` (Xtendoo sincroniza la rama `19.0`):

1. Commit y push a `19.0`.
2. `git pull` de Xtendoo.
3. Odoo → Aplicaciones → **Actualizar lista de aplicaciones**.
4. Quitar el filtro «Aplicaciones», buscar `enteza_panel_eventos` e **Instalar**.
5. `Ctrl+F5` — imprescindible: el módulo trae JS y SCSS, y el navegador cachea el bundle.

## Estado

⚠️ **Primera entrega, validada por sintaxis y NO ejecutada.** No hay instancia de pruebas ni
acceso a `odoo-bin`, y esto incluye un componente JavaScript que no se ha podido cargar ni una
vez. Es esperable que la primera instalación necesite ajustes visuales.

Si el panel no carga, mirar la **consola del navegador**: un error de JS deja la pantalla en
blanco sin avisar en el servidor.

## Pendiente / posibles siguientes pasos

- Ajustar los cortes de color cuando se conozca la carga real.
- Filtro por compañía visible, si con las dos sociedades activas el panel resulta confuso.
- Impresión del parte del día (hoja de carga para el almacén).
