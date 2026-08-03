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
- **Pinchar un artículo filtra los pedidos de abajo** a los que lo llevan, y añade una columna
  con las unidades que lleva cada uno; volver a pincharlo quita el filtro. Se hace en el
  navegador, sin ir al servidor: cada pedido ya trae las cantidades de sus artículos.

### Las existencias son de un almacén, no de la empresa

Cada fila es **almacén + artículo**, no solo artículo. Una sobreventa en Jerez no se resuelve
con material que está en Sevilla, y contarlo junto no es un matiz: medido en `enteza26`, el
producto 972 (`VASO MACETA MAXI 50CL`) tiene **80 unidades en `SEV/Stock` y 20 en `JER/Stock`**,
y `qty_available` sin acotar devuelve **100**. Stileum vería 100 unidades de algo de lo que
tiene 20.

Dos cosas que hay que saber para no volver a romperlo:

- La clave de contexto en la 19 es **`warehouse_id`**. `warehouse` —la de versiones anteriores—
  se ignora **en silencio** y devuelve la suma de todos los almacenes. Verificado por RPC: sin
  contexto 100, con `warehouse_id=1` 80, con `warehouse_id=2` 20, con `warehouse=1` otra vez 100.
- Acotar al almacén también deja fuera **el material que está en un evento**. `Customers/Alquiler`
  (ubicaciones 16 y 17) tiene `usage='internal'`, así que contaba como existencias aunque el
  material estuviera en casa de un cliente. Esa ubicación cuelga de `Customers`, no de la vista
  del almacén, así que el mismo cambio arregla las dos cosas.

La columna «Almacén» **solo aparece si el día mezcla varios**: con uno repetiría el mismo valor
en todas las filas. Hoy solo el 2026-08-01 mezcla Sevilla y Jerez, pero el cliente ha confirmado
que habrá más almacenes.

⚠️ La regla de sobreventa es la misma que usaba la aplicación anterior — unidades del día
contra existencias — y por eso **no descuenta el material que está fuera por alquileres de días
contiguos**: un alquiler del día 1 al 3 no resta en el día 2. Con la temporada muy concentrada
en fines de semana, la diferencia importa poco; si algún día importa, el cálculo temporal
completo lo da `product._get_unavailable_qty` de `sale_stock_renting`.

## Presupuestos sin confirmar

Un pedido en `draft`/`sent` todavía puede no ocurrir, y hasta la `19.0.3.0.0` sumaba material
exactamente igual que uno vendido: entraba en *Consumos*, en *Sobre venta* y en el parte que
baja al almacén, sin nada que lo distinguiera.

Ahora sale **atenuado y con la etiqueta «Presupuesto»**, y el interruptor **Solo confirmados**
lo deja fuera de los tres bloques y del PDF. Por defecto se ve: hay que saber que está ahí. El
contador junto al interruptor dice cuántos hay.

Confirmado = `state == 'sale'`. En `enteza26` hay 3 presupuestos de alquiler y 1.156 vendidos.

## El parte del día

Botón **Parte del día** → PDF con el material agrupado (con casilla para ir marcando al
cargar) y los pedidos. **Sale lo que se está viendo**: si la vista activa es *Sobre venta*, el
papel es directamente la lista de compras; si está *Solo confirmados*, el papel no lleva
presupuestos. El PDF dice siempre cuál de los dos casos es, porque quien lo lee en el almacén
no tiene la pantalla delante para deducirlo, y los presupuestos van marcados con **(P)**.

## Cómo está hecho

**Backend** — `models/sale_order.py`, métodos `@api.model` que el JS llama por RPC:

Todos llevan `solo_confirmados` como último argumento.

| Método | Devuelve |
|---|---|
| `enteza_panel_carga_mes(anio, mes, modo, solo_confirmados)` | `{'2026-07-31': {'pedidos': 3, 'importe': '4.520,50 €'}}` para colorear y para el tooltip |
| `enteza_panel_dia(dia, modo, solo_confirmados)` | pedidos, artículos, almacenes del día, totales y los tres contadores |
| `enteza_panel_accion_lista(dia, modo, solo_confirmados)` | la acción de ventana con los mismos pedidos en lista |
| `enteza_panel_imprimir(dia, modo, solo_sobreventa, solo_confirmados)` | la acción de informe del parte |

Las agregaciones se hacen **en Python sobre un `search_read`, no con `_read_group`**. Es
deliberado: el volumen es pequeño (1.159 pedidos de alquiler en total; un mes son decenas) y así
el código no depende de una firma de `_read_group` que en este entorno no se puede probar. Si el
volumen crece, se cambia ahí sin tocar el JS.

Las **existencias sí se leen en bloque**, una llamada por almacén y no una por artículo: el día
más cargado de `enteza26` (2026-05-02, 57 pedidos) tiene **389 productos distintos**, y
`qty_available` es un campo calculado que consulta los `stock.quant`.

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
  coinciden en los 1.159 pedidos.
- **Las notas no tienen columna, tienen un icono.** El campo es `note`, que en Odoo es
  *Terms and conditions*, no una nota del evento: solo **2 de 1.159** pedidos lo tienen
  informado, y los dos con texto de dirección de entrega arrastrado de la migración. Una
  columna vacía en 1.157 filas estorbaba más de lo que aportaba; el icono enseña el texto al
  pasar por encima. En su sitio se ven el **comercial** y el **almacén**, que sí cambian.
- **La columna «Existencias» saldrá a 0** en casi todo: la carga de inventario acaba de empezar.
  Mientras siga así, *Sobre venta* marcará prácticamente todo el material. No es un fallo.
- Se excluyen las líneas de sección y de nota (`display_type`), que no son material.
- **Un error de RPC ya no deja la pantalla en blanco**: se recoge y se enseña en un aviso rojo.
  El panel se usa desde el almacén, donde nadie va a abrir la consola del navegador.
- **Mientras carga, los bloques se atenúan.** Antes se quedaban con los datos del día anterior
  sin avisar, y no se distinguía un día vacío de un día que aún no había llegado. El indicador
  lo lleva un solo envoltorio (`_conCarga`) y no cada carga por su cuenta: si `cargarMes` y
  `cargarDia` lo tocaran las dos, la primera en terminar lo apagaría con la otra aún en vuelo.
- En el JS, la conversión de fecha a clave **no usa `toISOString()`** a propósito: convierte a
  UTC y en zonas al este de Greenwich devuelve el día anterior a partir de cierta hora, que es
  justo el error que haría mostrar los pedidos del día equivocado. En Python, los límites del
  día se convierten a UTC con la zona del usuario por el mismo motivo.
- El dominio de la lista lo arma **Python y no el JS**: esa conversión a UTC no debe estar
  duplicada en dos sitios.

## Multi-compañía

No hay filtro de compañía explícito: se confía en las reglas de registro de Odoo, que ya limitan
`sale.order` a las compañías activas del usuario. Hoy aporta poco de todas formas — de los 1.159
pedidos, **1.157 son de Vimaple y 2 de Stileum**.

Lo que sí importa de la multi-compañía es que **las existencias van por almacén**, y cada
almacén es de una compañía (`SEV` de Vimaple, `JER` de Stileum). Ver el bloque de material.

## Instalación

Despliegue por `git pull` (Xtendoo sincroniza la rama `19.0`):

1. Commit y push a `19.0`.
2. `git pull` de Xtendoo.
3. Odoo → Aplicaciones → **Actualizar lista de aplicaciones**.
4. Buscar `enteza_panel_eventos` y **Actualizar** (ya está instalado).
5. `Ctrl+F5` — imprescindible: el módulo trae JS y SCSS, y el navegador cachea el bundle.

## Estado

⚠️ **Validado por sintaxis y NO ejecutado.** No hay instancia de pruebas ni acceso a `odoo-bin`.
La versión `19.0.1.0.0` sí está probada en pantalla; **nada de lo añadido después se ha podido
cargar ni una vez** — ni los tres modos, el filtro de material, la sobreventa y el parte en PDF
de la `19.0.2.0.0`, ni las existencias por almacén y los presupuestos de la `19.0.3.0.0`.

Lo que sí está **comprobado contra `enteza26` por RPC** son los datos en los que se apoyan las
decisiones: el reparto 80/20 del producto 972 entre `SEV/Stock` y `JER/Stock`, que la clave de
contexto es `warehouse_id` y no `warehouse`, que `Customers/Alquiler` es `usage='internal'`, que
`event_date` es un `date` y `rental_start_date`/`rental_return_date` `datetime`, los 3
presupuestos frente a 1.156 vendidos, los 389 productos distintos del 2026-05-02, y que `note`
solo está informado en 2 de 1.159 pedidos.

Si el panel no carga, mirar la **consola del navegador**: un error de JS deja la pantalla en
blanco sin avisar en el servidor. Un error de **RPC** ya no lo hace: sale un aviso rojo con el
mensaje del servidor.

## Pendiente / posibles siguientes pasos

- Revisar los cortes de color cuando haya una temporada entera cargada en Odoo.
- Sobreventa con disponibilidad temporal real (`_get_unavailable_qty`), si los alquileres de
  varios días acaban solapándose de verdad. Ahora que las existencias van por almacén, este es
  el único hueco que queda en el cálculo.
- Filtro por compañía visible, si Stileum llega a tener volumen.
