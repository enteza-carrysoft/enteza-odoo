# Enteza · Panel de eventos del día

Reproduce en Odoo la pantalla de control diario de la aplicación de gestión que Enteza usaba
antes: **tres bloques sincronizados en una sola pantalla**.

**Alquiler → Pedidos → Panel de eventos.**

La pantalla original que se reproduce está en **`.claude/PRPs/eventos.png`** («Eventos de
Alquileres y Banquetes», la aplicación que Enteza usaba antes). Es la referencia de diseño:
mirarla antes de cambiar la disposición de los bloques.

```
┌──────────────┬────────────────────────────────┐
│ CALENDARIO   │ MATERIAL DEL DÍA               │
│ del mes,     │ filtro por descripción ·       │
│ días         │ Consumos / Sobre venta         │
│ coloreados   │ artículos agrupados y sumados  │
├──────────────┴────────────────────────────────┤
│ PEDIDOS DEL DÍA                               │
│ nº · cliente · lugar · inicio · fin · estado  │
└───────────────────────────────────────────────┘
```

## Los tres días de un pedido

`rental_custom` deja la salida la **víspera** del evento y la devolución el **día siguiente**,
y los datos de `enteza26` lo confirman: de 1.156 pedidos, **1.090 salen el día antes** y 985
vuelven el día después. Así que "los eventos de hoy" y "el trabajo de hoy en el almacén" son
tres listas distintas, y el panel deja elegir cuál se mira:

| Modo | Campo | Pregunta que responde |
|---|---|---|
| **Eventos** | `event_date` | ¿Qué se celebra hoy? |
| **Sale hoy** | `rental_start_date` | ¿Qué hay que cargar hoy? |
| **Vuelve hoy** | `rental_return_date` | ¿Qué material entra hoy? |

Los tres contadores se ven siempre en la cabecera, aunque solo uno esté activo: es la forma
de que salte a la vista que hoy hay 2 eventos pero 47 pedidos que cargar.

## El bloque de material

Igual que el bloque DISPONIBILIDAD de la aplicación anterior:

- **Filtro por descripción**, que busca también en la clasificación y **no distingue tildes ni
  mayúsculas**: `mantel` encuentra `MANTELERÍA`.
- **Consumos**: todo el material comprometido ese día.
- **Sobre venta**: solo los artículos con **más unidades alquiladas que existencias**. Es la
  lista de lo que hay que comprar o subcontratar para cumplir con lo ya vendido.
- **Pinchar un artículo filtra los pedidos de abajo** a los que lo llevan; volver a pincharlo
  quita el filtro. Se hace en el navegador, sin ir al servidor: cada pedido ya trae la lista de
  sus artículos.

⚠️ La regla de sobreventa es la misma que usaba la aplicación anterior — unidades del día
contra existencias — y por eso **no descuenta el material que está fuera por alquileres de días
contiguos**: un alquiler del día 1 al 3 no resta en el día 2. Con la temporada muy concentrada
en fines de semana, la diferencia importa poco; si algún día importa, el cálculo temporal
completo lo da `product._get_unavailable_qty` de `sale_stock_renting`.

## El parte del día

Botón **Parte del día** → PDF con el material agrupado (con casilla para ir marcando al
cargar) y los pedidos. **Sale lo que se está viendo**: si la vista activa es *Sobre venta*, el
papel es directamente la lista de compras.

## Cómo está hecho

**Backend** — `models/sale_order.py`, métodos `@api.model` que el JS llama por RPC:

| Método | Devuelve |
|---|---|
| `enteza_panel_carga_mes(anio, mes, modo)` | `{'2026-07-31': {'pedidos': 3, 'importe': 4520.5}}` para colorear |
| `enteza_panel_dia(dia, modo)` | pedidos, artículos, totales y los tres contadores |
| `enteza_panel_accion_lista(dia, modo)` | la acción de ventana con los mismos pedidos en lista |
| `enteza_panel_imprimir(dia, modo, solo_sobreventa)` | la acción de informe del parte |

Las agregaciones se hacen **en Python sobre un `search_read`, no con `_read_group`**. Es
deliberado: el volumen es pequeño (1.156 pedidos de alquiler en total; un mes son decenas) y así
el código no depende de una firma de `_read_group` que en este entorno no se puede probar. Si el
volumen crece, se cambia ahí sin tocar el JS.

**Frontend** — acción cliente OWL registrada como `enteza_panel_eventos.panel` en
`registry.category("actions")`, con su plantilla y su SCSS en `static/src/`.

**Informe** — `report/parte_dia.py` + `report/parte_dia_templates.xml`, reutilizando los mismos
formateadores del panel para que el papel y la pantalla no puedan discrepar.

### Decisiones que conviene conocer

- **Se excluyen los pedidos cancelados.**
- **Los cortes de color están medidos**, no supuestos: 3, 10 y 30 pedidos/día, sobre los 150
  días con actividad de `enteza26` (mediana 3, p85 = 14, p90 = 23, p95 = 46, máximo 57). Los
  cortes anteriores (3 y 6) saturaban la escala y todos los sábados de temporada pintaban igual.
- La escala de color es monocroma sobre el color de marca, no un semáforo: aquí «muchos
  pedidos» es un buen día de trabajo, no una alarma. El **rojo se reserva para la sobreventa**,
  que es lo único del panel que obliga a hacer algo.
- **Se muestran las fechas de inicio y fin, no la hora.** Los 1.156 pedidos migrados tienen la
  hora a 00:00 **sin excepción**, así que una columna de horas repetía el mismo valor en todas
  las filas. La fecha sí informa, porque la salida suele ser la víspera del evento.
- **La columna «Lugar de entrega» sale vacía si coincide con el cliente.** Hoy en `enteza26`
  coinciden en los 1.156 pedidos.
- **La columna «Existencias» saldrá a 0** en casi todo: la carga de inventario acaba de empezar.
  Mientras siga así, *Sobre venta* marcará prácticamente todo el material. No es un fallo.
- Se excluyen las líneas de sección y de nota (`display_type`), que no son material.
- En el JS, la conversión de fecha a clave **no usa `toISOString()`** a propósito: convierte a
  UTC y en zonas al este de Greenwich devuelve el día anterior a partir de cierta hora, que es
  justo el error que haría mostrar los pedidos del día equivocado. En Python, los límites del
  día se convierten a UTC con la zona del usuario por el mismo motivo.
- El dominio de la lista lo arma **Python y no el JS**: esa conversión a UTC no debe estar
  duplicada en dos sitios.

## Multi-compañía

No hay filtro de compañía explícito: se confía en las reglas de registro de Odoo, que ya limitan
`sale.order` a las compañías activas del usuario. Hoy aporta poco de todas formas — de los 1.156
pedidos, **1.155 son de Vimaple y 1 de Stileum**.

## Instalación

Despliegue por `git pull` (Xtendoo sincroniza la rama `19.0`):

1. Commit y push a `19.0`.
2. `git pull` de Xtendoo.
3. Odoo → Aplicaciones → **Actualizar lista de aplicaciones**.
4. Buscar `enteza_panel_eventos` y **Actualizar** (ya está instalado).
5. `Ctrl+F5` — imprescindible: el módulo trae JS y SCSS, y el navegador cachea el bundle.

## Estado

⚠️ **Validado por sintaxis y NO ejecutado.** No hay instancia de pruebas ni acceso a `odoo-bin`.
La versión `19.0.1.0.0` sí está probada en pantalla; todo lo añadido en la `19.0.2.0.0` (los tres
modos, el filtro de material, la sobreventa y el parte en PDF) no se ha podido cargar ni una vez.

Si el panel no carga, mirar la **consola del navegador**: un error de JS deja la pantalla en
blanco sin avisar en el servidor.

## Pendiente / posibles siguientes pasos

- Revisar los cortes de color cuando haya una temporada entera cargada en Odoo.
- Sobreventa con disponibilidad temporal real (`_get_unavailable_qty`), si los alquileres de
  varios días acaban solapándose de verdad.
- Filtro por compañía visible, si Stileum llega a tener volumen.
