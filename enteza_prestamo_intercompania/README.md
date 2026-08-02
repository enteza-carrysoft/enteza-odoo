# Enteza · Préstamo de material entre compañías

Implementa el PRP `.claude/PRPs/prp-modulo-prestamo-intercompania.md`.

**Estado: fase 2, primera entrega.** El motor de disponibilidad (fase 1) y el documento de
préstamo con su ciclo de vida: numeración, estados, reserva en firme, aprobación, menú y
vistas.

Todavía **no** engancha en la confirmación de pedidos ni genera albaranes. Van en las dos
entregas siguientes de esta misma fase, en este orden:

1. ✅ **Documento vivo** — lo que hay ahora: se puede crear un préstamo a mano, reservarlo
   (y entonces resta de verdad en la disponibilidad de la prestamista), aprobarlo, cancelarlo.
2. ✅ **Widget de disponibilidad + enganche en `action_confirm`** — el camino principal
   (D5/D5.1). Al montar el presupuesto, el icono de la línea se pone rojo y dice cuánto falta
   y quién puede prestarlo. Al confirmar, un diálogo propone el préstamo y **solo si el
   comercial acepta** se reserva en firme, con el recálculo y el bloqueo del §5.6.
3. ✅ **Albaranes** — ubicación de tránsito, tipos de operación y el doble albarán al aprobar.

Con esto la **fase 2 está completa**: el material se mueve de verdad de una sociedad a otra.

## El aviso de préstamo (`19.0.2.3.0`)

Primera mitad de la entrega 2. Cuando el almacén propio no llega, **el icono de
disponibilidad de la línea se pone rojo**, y al pincharlo la ventana flotante dice cuánto
falta y quién puede prestarlo:

```
Producto                  Cantidad   Disp.
VASO MACETA MAXI 50CL        95       📉  ← en rojo
                                       │
                     ┌─────────────────┴──────────────────┐
                     │ Disponible para alquilar   80 Uds  │
                     │ 15/08/2026 a 17/08/2026            │
                     │                                    │
                     │ ⚠ Faltan 15 Uds                    │
                     │ Stileum · Jerez las presta.        │
                     │ Se reservan al confirmar.          │
                     └────────────────────────────────────┘
```

Con material de sobra no aparece nada: el icono queda como el nativo y la ventana tampoco
dice nada. Si la otra compañía solo cubre una parte, se dice lo que cubre **y lo que queda
suelto**.

El rojo del icono cuelga de **nuestro** campo y no del `forecasted_issue` nativo: ese depende
de `qty_to_deliver`, y en alquiler `sale_stock_renting` pone el método de entrega en manual,
así que no es de fiar aquí. Colgándolo de `enteza_falta`, el icono se pone rojo exactamente
cuando hay mensaje que leer.

> **Hubo un aviso en la cabecera del pedido y se quitó** (`19.0.2.3.0`, decisión del cliente
> del 2026-08-02). Resumía las líneas con déficit sin tener que pinchar nada, pero en pedidos
> de muchas líneas se convertía en ruido. El icono rojo es ahora **la única señal en
> pantalla**: si algún día deja de pintarse, el déficit se vuelve invisible hasta la
> confirmación. Está en el historial de git por si se quiere recuperar.

## El diálogo de confirmación (`19.0.3.0.0`)

Segunda mitad de la entrega 2, y el camino principal del módulo. Al confirmar un pedido que
el almacén propio no puede servir, **se para la confirmación** y se enseña la propuesta:

```
┌ Falta material para este pedido ───────────────────────────────────┐
│ Este pedido no se puede servir con el material propio.             │
│ Se puede cubrir con material de otra compañía del grupo. Si        │
│ aceptas, ese material queda reservado en firme.                    │
│                                                                    │
│ Producto      Pedidas  Faltan  Se presta desde  Se prestan  Sin    │
│ VASO MACETA        95      15  Jerez                    15    0    │
│                                                                    │
│      [ Confirmar y reservar ]  [ Cancelar ]                        │
└────────────────────────────────────────────────────────────────────┘
```

Cancelar deja el pedido **sin confirmar y sin ningún préstamo**. Aceptar crea el préstamo en
`reserved`, lo enlaza con la línea de pedido y confirma. El traslado físico sigue exigiendo
que un responsable pulse **Aprobar**: lo que se automatiza es la reserva, no el movimiento.

Si **nadie** puede prestar, el diálogo lo dice y deja confirmar igualmente (`[PENDIENTE-8]`):
el comercial tiene que poder cerrar la venta y buscar la solución por otra vía. El déficit se
queda a la vista en el icono rojo de la línea, que es lo único que impide perderlo de vista.

### 🔴 Por qué son dos transacciones

El bloqueo de concurrencia **no puede sostenerse mientras el diálogo está abierto**: sería una
transacción abierta durante minutos bloqueando a todos los demás comerciales sobre esos
productos — un cuelgue justo en temporada alta, que es cuando hay cola. Así que:

| Paso | Qué hace | Bloqueo |
|---|---|---|
| 1 · `action_confirm` | Calcula, propone y abre el diálogo. **No escribe nada** | No |
| 2 · `action_confirmar` del asistente | Bloquea, **recalcula desde cero** y reserva | Sí |

**El diálogo es una propuesta, no una reserva.** Si mientras el comercial decide otro pedido
se lleva el material, al aceptar no se reserva nada, el pedido se queda sin confirmar y se le
dice qué ha cambiado. Cubierto por `test_si_desaparece_el_material_no_se_reserva_nada`.

El criterio de «ha empeorado» es **lo que queda sin cubrir**, no lo que se presta: si el
déficit baja porque se canceló otro pedido, la propuesta sigue valiendo y se reserva menos.

El bloqueo es un *advisory lock* de PostgreSQL acotado a la transacción, no un
`SELECT ... FOR UPDATE` sobre el producto: se libera solo, no deja filas bloqueadas para
escrituras que no tienen nada que ver, y no depende de qué tablas toque el cálculo. Los
productos se bloquean **ordenados por id**, o dos confirmaciones que compartan varios
artículos se abrazan.

### Detalles que costará recordar

- **Flag de contexto `enteza_prestamo_aceptado`.** Sin él, el asistente vuelve a abrir el
  diálogo al reconfirmar: bucle infinito. Es también la vía de escape para cualquier
  integración que necesite confirmar sin pasar por el diálogo.
- **`action_confirm` devuelve una acción** en vez de `True` cuando abre el diálogo. Es el
  idioma de Odoo para los botones que preguntan algo —`stock.picking.button_validate` hace lo
  mismo—, pero ⚠️ **un llamador que espere un booleano no confirmará el pedido**. Si algún día
  se activa el pago por portal o una confirmación automática, hay que pasarles el flag de
  contexto de arriba.
- **Confirmar varios pedidos a la vez se para** con un aviso que los lista. No se puede
  preguntar por uno dejando los demás a medias, y confirmarlos en silencio se saltaría el
  permiso que D5.1 existe para pedir.
- **El préstamo se crea con `sudo()`.** Quien confirma es un comercial y no tiene por qué
  estar en los grupos de préstamos —hoy solo `admin` lo está—. No es un agujero: el usuario ya
  ha dado el permiso en el diálogo y lo único que se crea es un documento en `reserved`, que
  no mueve material. Pero ojo: **para ver el préstamo en el menú sí hace falta el grupo**.
- **`_revalidar_disponibilidad` calcula con `sudo()` y `with_company()` de la prestamista.**
  Quien reserva es de la compañía receptora y no tiene acceso a los quants de la otra: sin
  esto la reserva fallaría siempre con un «no hay libre» falso, y de los difíciles de
  diagnosticar, porque el mismo préstamo sí se reserva bien desde la otra compañía.

## Fase 3 · La devolución inteligente (`19.0.5.0.0`)

El punto que el cliente pidió por su nombre. Cuando el material vuelve del evento, el
responsable pulsa **Proponer devolución** y el módulo calcula cuánto conviene devolver:

```
ventana  = hoy .. hoy + 7 días          (parámetro `ventana_retencion`)
necesita = pico de demanda de la receptora en la ventana
propio   = lo que tiene en almacén MENOS lo que tiene prestado sin devolver
retener  = min(pendiente, max(0, necesita - propio))
devolver = pendiente - retener
```

**El ejemplo del cliente**: prestadas 100, necesita 30 en la ventana y no le llega con lo
suyo → retiene 30, devuelve 70. La idea es no devolver material que va a hacer falta en unos
días: sería un viaje de ida y otro de vuelta para nada.

🔴 **Si la prestamista también lo necesita, su necesidad manda** (`[PENDIENTE-5]`): es su
material. La retención se recorta en lo que le falte a ella, y **las dos cifras se enseñan en
la propuesta**, porque si no parecería que el cálculo se ha equivocado.

Es una **propuesta, no una ejecución** (D2): el responsable puede cambiar las cantidades antes
de aceptar. Al aceptar se genera el par de albaranes de vuelta —receptora → tránsito →
prestamista—, reutilizando los mismos tipos de operación cambiados de bando.

- **Devoluciones parciales sucesivas**: cada una genera su propio par de albaranes. Son viajes
  distintos y mezclarlos haría imposible saber qué salió cada día.
- `qty_returned` se anota cuando la **prestamista recibe** el material, no cuando la receptora
  lo despacha: entre una cosa y la otra va por la carretera.
- Cuando no queda nada pendiente → `returned`. Si queda algo → `partially_returned`.

### Vista de control (§7.6)

La lista de préstamos responde de un vistazo qué hay prestado y cuánto falta por volver:
columna **Sin devolver** con suma, y filtros **Pendientes de devolver** y **Necesitan
revisión**.

## Cancelar o reducir un pedido libera su parte (`19.0.4.1.0`)

Contrapartida obligatoria de haber juntado varios pedidos en un mismo viaje. Sin esto,
cancelar un evento dejaba su material comprometido para siempre y, si el traslado ya estaba
aprobado, **viajaba igualmente**.

| Estado del préstamo | Al cancelar el pedido |
|---|---|
| `reserved` | Se retira su línea. Si el préstamo se queda vacío, se cancela |
| `approved` | Ídem, y **se ajusta el albarán existente** (§7.0.2). Si queda vacío, se cancelan los dos albaranes |
| `in_transit` en adelante | 🔴 **No se toca nada.** El material ya salió: se marca el préstamo con «Necesita revisión» y el motivo |

Reducir la cantidad de una línea confirmada libera la parte proporcional. **Ampliarla no hace
nada todavía**: eso necesita volver a pasar por el cálculo de déficit y por el diálogo de
D5.1. Por ahora el icono de la línea se pondrá rojo y hay que resolverlo a mano.

Detalles que conviene no deshacer:

- Se libera **antes** de `super()._action_cancel()`, mientras las líneas siguen en `sale`: es
  el único momento en que se sabe con certeza qué aportaba cada una.
- Los movimientos de stock se **cancelan antes** de borrar la línea de préstamo. El enlace es
  `ondelete='set null'`, así que borrarla a secas dejaría un movimiento huérfano que seguiría
  sacando material del almacén sin que nada lo relacionara con nada.
- Vaciar un préstamo lo cancela **sin pasar por `action_cancelar`**, que exige el grupo de
  responsable. Aquí no hay decisión que tomar —el motivo del préstamo ha desaparecido— y
  exigir una firma solo dejaría viajes vivos sin carga.
- Todo queda anotado con fecha en las notas del préstamo.

Los préstamos marcados salen con el filtro **«Necesitan revisión»** de la lista.

## El traslado de ida: dos albaranes vía tránsito (`19.0.4.0.0`)

Al **aprobar**, el préstamo deja de ser papel: se generan los dos albaranes y el material
empieza a moverse de verdad.

```
Jerez/Stock  ──[ Préstamo · salida ]──▶  Inter-company transit  ──[ Préstamo · entrada ]──▶  Sevilla/Stock
  (Stileum)                                (sin compañía)                                      (Vimaple)
     │                                                                                            │
     └─ al validar: préstamo → in_transit                        al validar: préstamo → lent ─────┘
```

Dos albaranes y no uno porque el movimiento cruza dos sociedades: cada almacén valida el suyo
y ve solo su mitad. El material vive en la ubicación de tránsito entre una validación y la
otra. **El estado del préstamo lo mueve el hecho físico**, no un botón: si dice `in_transit`
es porque el material ha salido de las estanterías.

### 🔴 La ubicación de tránsito ya existe en Odoo 19: no hay que crearla

Esto **corrige el §6.1 del PRP en dos puntos**, y los dos habrían costado un despliegue:

| El PRP decía | La realidad de la 19 |
|---|---|
| Crear una `stock.location` de tránsito propia | **Ya existe**: `stock.stock_location_inter_company`, `usage='transit'` y `company_id` vacío. Crear otra sería duplicar la que usan los flujos intercompañía del propio Odoo |
| Colgarla de `stock.stock_location_locations_virtual` | Ese external id **no existe en la 19**. El XML del PRP habría reventado la instalación |

Viene **archivada**, y por eso una búsqueda de ubicaciones de tránsito no la encuentra y
parece que no hay ninguna — el §2 del PRP llegó a anotar «0 ubicaciones de tránsito en toda la
base», que era cierto y engañoso a la vez. El módulo la reactiva desde `data/`, **fuera** del
bloque `noupdate`, para que si alguien la archiva la siguiente actualización la deje usable.

`_ubicacion_transito()` comprueba las tres condiciones y da un error claro si falla alguna. Sin
`company_id` vacío la mitad del flujo se rompe con un error de acceso poco descriptivo, que es
la causa número uno de problemas en este tipo de módulo.

### Tipos de operación: uno por almacén, creados solos

`Préstamo · salida` y `Préstamo · entrada`, con su propia secuencia (`PREOUT` / `PREIN`). **No
se reutilizan los `OUT`/`IN` de cliente**: el operario vería traslados entre sociedades
mezclados con las entregas a clientes, y no son lo mismo ni los prepara la misma persona.

Se crean **la primera vez que hacen falta**, no como datos del módulo: los almacenes no existen
al instalar y sus ids no se pueden poner en un XML. Así tampoco hay que acordarse de configurar
nada cuando el cliente abra el tercer almacén. Quedan guardados en dos campos del propio
almacén, así que se pueden ver y cambiar.

⚠️ En la 19, `default_location_src_id` y `default_location_dest_id` son **obligatorios** en el
tipo de operación; no lo eran antes.

### Ampliar, nunca rehacer

Si al préstamo se le acumula material después de aprobarlo (§7.2), la segunda aprobación
**añade los movimientos al albarán que ya existe**. Cancelar y crear otro dejaría al almacén
con documentos anulados que quizá ya había impreso, y el §7.0.2 pide expresamente lo
contrario.

El emparejamiento entre movimiento y línea de préstamo es explícito
(`stock.move.enteza_loan_line_id`) y no por producto: un mismo préstamo puede llevar el mismo
artículo dos veces para intervalos distintos, y emparejar por producto mezclaría las
cantidades.

**Solo se mueve lo que tiene `qty_approved`.** Es la traducción física de la regla de siempre:
lo reservado protege el material, lo aprobado lo mueve.

### Un préstamo es un VIAJE, no un pedido (`19.0.3.1.0`)

**Petición del cliente, 2026-08-02**, y un hueco real: la versión anterior creaba un préstamo
por cada confirmación. Dos eventos del mismo día que necesitaran material de la otra compañía
generaban dos documentos y, con la entrega 3, **dos pares de albaranes** para el mismo porte.

Ahora, antes de crear, se busca un préstamo vivo para la misma **ruta** y la misma **fecha de
traslado exacta**. Si existe, el material se le añade.

- La agrupación es por fecha de traslado exacta, que es lo que dice el §7.2 del PRP. Un evento
  del sábado y otro del domingo dan fechas distintas: **son dos viajes**, y así se quedan.
- Solo se reutilizan préstamos en `reserved` o `approved`. Un `draft` es trabajo a medias de
  otra persona; desde `in_transit` el camión ya salió y lo que llegue después necesita un
  viaje nuevo por fuerza.
- `_fecha_traslado_de()` es `@api.model` justamente para esto: quien decide si una necesidad
  cabe en un préstamo abierto necesita la fecha **antes** de tener el préstamo. Calcularla en
  otro sitio con otra fórmula rompería el criterio de agrupación sin que se note.

#### Cómo convive con la aprobación

Decisión del cliente: **no se reabre lo ya firmado.**

| Estado | Al llegar material nuevo |
|---|---|
| `reserved` | Se añade y ya está. No hay nada que refirmar |
| `approved` | Se añade con `qty_approved = 0`. El préstamo **sigue aprobado** y avisa de que tiene material pendiente. El responsable pulsa **«Aprobar lo añadido»** y firma solo el incremento |
| `in_transit` en adelante | No se toca. Viaje nuevo |

🔴 **El material acumulado queda comprometido en el acto**, sin esperar a la firma:
`_qty_comprometida()` devuelve `qty_reserved` mientras `qty_approved` esté a cero. No hay ni
un instante en el que otro comercial pueda vender esas unidades. La firma hace falta para
**mover** el material, no para reservarlo.

`action_aprobar` solo rellena las líneas **sin firmar**. Es lo que distingue «material nuevo
que nadie ha visto» de «el responsable decidió aprobar menos»: igualar `qty_approved` a
`qty_reserved` sin mirar desharía en silencio el recorte de la aprobación anterior. Cubierto
por `test_aprobar_lo_añadido_firma_solo_el_incremento`.

De paso se corrigió que las líneas quedaban **de solo lectura en cuanto el préstamo estaba
aprobado**, así que el ajuste de `qty_approved` que pide el §7.3 no se podía hacer desde
ninguna pantalla. Ahora se pueden editar hasta `in_transit`.

#### Lo que esto deja pendiente

Al juntar varios pedidos en un préstamo, **cancelar uno solo tiene que retirar su parte y
dejar el resto**. Se puede hacer porque cada línea lleva su `sale_line_id`, pero hoy **no está
implementado**: cancelar un pedido no toca el préstamo. Es trabajo de la fase 4 (§7.1, las
reservas sobrantes).

### Dos fallos que costó una prueba real (`19.0.3.0.1`)

Al probar el diálogo **no apareció nada**. Las dos causas eran independientes y ninguna daba
un error:

| Qué | Por qué no se veía |
|---|---|
| **`models/sale_order.py` no estaba importado** en `models/__init__.py` | Se borró el fichero del aviso de cabecera junto con su import, y al crear otro con el mismo nombre para el diálogo no se volvió a añadir. **El módulo instala igual y el `action_confirm` nunca se registra.** Ahora lo caza `scripts/validar_modulo.py` antes de desplegar |
| **`_rentable` restaba dos veces la línea confirmada** | Ignoraba la propia línea en `_get_virtual_unavailable_qty_in_rent` siempre, y el nativo solo lo hace si el pedido está en **borrador**. Confirmado el pedido, el movimiento de stock existe y `virtual_available` ya lo descontó: ese método está para volver a sumarlo. Un pedido de 95 sobre 80 en almacén daba un déficit de **110 en vez de 15** |

El segundo es el peligroso: **antes de confirmar el número era correcto**, así que el widget
se veía bien y el fallo solo aparecía después, que es cuando ya nadie está mirando. Cubierto
por `test_la_propia_linea_confirmada_no_se_resta_dos_veces`.

### Limitación heredada del nativo

**Dos líneas del mismo presupuesto no compiten entre sí.** Solo cuenta como demanda lo
confirmado (`state = 'sale'`, ver `_get_active_rental_lines`), así que dos líneas de 95 y 10
del mismo producto ven las dos las mismas 80 libres, aunque entre ambas pidan 105. El reparto
real lo decide la confirmación, que es donde se reserva. Cubierto por
`test_cada_linea_se_evalua_por_su_cuenta`.

### Un préstamo ya reservado deja de contar como déficit

`_enteza_cubierto_por_prestamo` resta lo que un préstamo vivo aporta a esa línea de pedido.
Hoy no hay ninguno —los crea el enganche de `action_confirm`, que aún no está—, pero sin esa
resta el aviso **seguiría diciendo que faltan 15 cuando ya estuvieran resueltas**: el material
lo pone la otra compañía, así que la disponibilidad del almacén propio no se entera. Se cuenta
desde `reserved`; un préstamo en borrador es una propuesta y no tapa nada.

### Por qué hacía falta

El widget nativo **oculta justo eso**. El campo que enseña está acotado a cero en el propio
Odoo (`sale_stock_renting`, `_compute_qty_at_date`):

```python
virtual_available_at_date = max(rentable_qty - rented_qty_during_period, 0)
```

Quien pide 95 teniendo 80 lee «Disponible para alquilar: 80» y se queda igual.

### Cómo está hecho

Se **extiende** el widget nativo, no se escribe uno nuevo: tres campos calculados no
almacenados en `sale.order.line`, declarados en `fieldDependencies`, y un `t-inherit` sobre
`sale_stock.QtyAtDatePopover`. Tres decisiones que conviene no deshacer:

- **La cifra sale del mismo motor que decide la reserva** (`enteza.disponibilidad`). Si el
  widget y la confirmación dieran números distintos, el comercial dejaría de fiarse de los dos.
- **No se usa `virtual_available_at_date` como atajo** para saber si hay déficit, aunque sería
  gratis: el nativo no descuenta los préstamos ya comprometidos, así que diría que hay 80
  libres cuando 30 están reservadas para la otra compañía. Un prefiltro optimista esconde
  déficits reales. Lo cubre `test_un_prestamo_comprometido_genera_deficit_que_el_nativo_no_ve`.
- **La consulta a la otra compañía solo se hace si la propia se queda corta**, que es lo que
  mantiene el coste a raya: el motor hace una búsqueda por producto.

`sudo()` acotado a esa lectura, porque un comercial de Vimaple no tiene acceso a los quants de
Stileum. Se expone la cifra agregada, nunca los registros. **Implica que los comerciales de
cada sociedad ven el nivel de existencias de la otra**, que es deliberado.

### Lo que sí está verificado de esta parte

Las **dos** herencias de plantilla, ejecutadas: resuelven su `xpath`, caen donde deben y el
componente conserva la raíz única que exige OWL. Reproducible:

```bash
W=enteza_prestamo_intercompania/static/src/widgets/qty_at_date_widget.xml

python .claude/skills/odoo19-dev/scripts/simular_herencia_owl.py \
    --base sale_stock.QtyAtDatePopover --del-bundle sale_stock_renting.QtyAtDatePopover \
    "$W#enteza_prestamo_intercompania.QtyAtDatePopover"

python .claude/skills/odoo19-dev/scripts/simular_herencia_owl.py \
    --base sale_stock.QtyAtDate --del-bundle sale_stock_renting.QtyAtDate \
    "$W#enteza_prestamo_intercompania.QtyAtDate"
```

La plantilla de la 19 EE se lee del bundle de assets de la propia `enteza26` — el código de
Enterprise no es público, pero la instancia lo sirve. Frente a la 18 solo cambia
`product_uom` → `product_uom_id`.

Los campos usados (`start_date`, `return_date`, `is_rental`, `product_uom_qty`,
`order_id.warehouse_id`, `uom.uom.rounding`) están comprobados por RPC contra `enteza26`.
**El cálculo en sí no está ejecutado**: las pruebas de `test_widget_prestamo.py` están
escritas y validadas por sintaxis, no corridas.

Lo que sí está probado a mano en `enteza26` (2026-08-02): con 80 unidades en Sevilla y una
línea de 95, la ventana flotante muestra el aviso con las cifras correctas.

🔴 **Si el backend se queda en blanco tras actualizar**, empezar por el `t-inherit`: cuando no
encuentra su `xpath` se cae el bundle entero y no queda nada en el log del servidor. Y probar
antes con `Ctrl+F5`, que el navegador cachea el bundle anterior.

## Decisiones tomadas el 2026-08-01, que corrigen el PRP

Las cuatro que el §16 dejaba abiertas para la fase 2:

| | Decisión | Efecto |
|---|---|---|
| `[PENDIENTE-1]` Almacenes | **Habrá más** de uno por compañía | Origen y destino son **seleccionables**, no deducidos de la compañía |
| `[PENDIENTE-3]` Antelación | **Fija y configurable**, 3 días para todas las rutas | Un solo parámetro. `_fecha_traslado()` es el único sitio que la calcula |
| `[PENDIENTE-8]` Confirmar sin stock | **Puede cualquiera**, con aviso | 🔴 **Diverge del PRP §7.0.1**, que lo reservaba al responsable. Como cualquiera puede confirmar, la **marca de déficit no cubierto** en el pedido pasa a ser lo único que evita perder de vista un pedido imposible |
| `[PENDIENTE-9]` Prioridad | **Quien reserva primero** (`date_reserved`) | Por eso `date_reserved` no se toca al modificar un préstamo: perderlo es perder el criterio |

## Correcciones al PRP aplicadas en esta fase

El PRP se redactó sin detectar que **`sale_stock_renting` está instalado** en `enteza26`
(§2.1 no lo lista). Ese módulo aporta el motor de disponibilidad completo, y su análisis
—sobre el código de la 18 EE— corrige varias premisas del documento:

| PRP | Realidad verificada en el código |
|---|---|
| §5: hay que escribir un motor propio con SQL agrupado | Odoo ya lo trae: `product._get_unavailable_qty()` hace el barrido por eventos con máximo del intervalo, y además ajusta por recogidas y devoluciones tempranas |
| §5.2: el padding es `res.company.padding_time` | Es **`product.template.preparation_time`**, por producto y `company_dependent`. El de compañía solo es el valor por defecto que se copia a un `ir.default` al instalar |
| §2.3: `return_date` de línea no sirve en un `search` | Es un `related` a un campo almacenado: **sí es buscable**. Cierto solo para `read_group` y SQL |
| §5.1: `prestado_a_terceros` cuenta hasta `partially_returned` | Solo puede contar `reserved` y `approved`. Desde `in_transit` el material ya salió y el stock ya lo refleja: contarlo restaría dos veces |
| §13: dependencias `stock`, `sale_renting`, `sale_stock` | Falta **`sale_stock_renting`**, sin el cual el módulo no instala |
| Todo el cálculo por compañía | El nativo se scopea **por almacén** (`warehouse_id`). Este módulo hace lo mismo |

## Correcciones de la 19 aplicadas en `19.0.1.0.1`

La primera instalación en `enteza26` (2026-08-01) falló. Al revisar por qué, aparecieron tres
usos de API de la 18 que en la 19 ya no valen, **dos de ellos con fallo silencioso**, y un
error de cálculo propio.

| Qué | Síntoma | Cómo se comporta la 19 |
|---|---|---|
| `res.groups.category_id` | 🔴 **Rompe la instalación.** `ValueError: Invalid field 'category_id' in 'res.groups'` al cargar `security/prestamo_security.xml` | Se ha intercalado `res.groups.privilege`: el grupo tiene `privilege_id` y es el privilegio el que apunta a la `ir.module.category` |
| `_sql_constraints` | **Silencioso.** El módulo instala, se registra un aviso en el log y **la restricción no se crea**: se podían grabar préstamos de una compañía consigo misma | `models.Constraint('CHECK (...)', 'mensaje')` como atributo de clase (ver `sale.order._date_order_conditional_required`) |
| `_auto_init` + `tools.create_index` | Funcionaba, pero `odoo.tools` se ha reorganizado en la 19 y no está claro que `create_index` siga expuesto ahí | `models.Index('(campo1, campo2)')` declarativo (ver `stock.move.line._free_reservation_index`) |
| `<field name="global" eval="True"/>` en `ir.rule` | Redundante | `global` es calculado y almacenado (`_compute_global` = `not groups`). Una regla sin grupos ya es global |

### Y un error del barrido de `prestado_a_terceros` 🔴

El máximo se medía solo en los **eventos interiores** del intervalo consultado. Un préstamo
que empieza antes de `desde` y acaba después de `hasta` no aporta ningún evento dentro, así
que **contaba como cero**: la prestamista habría vuelto a vender material ya comprometido,
que es exactamente lo que ese método existe para impedir.

Se da en cuanto se presta para un fin de semana largo y luego se consulta un día suelto de
dentro — es decir, en el uso normal. Ahora el barrido arrastra primero el nivel ya vigente en
`desde` y solo después mide los cambios interiores. Cubierto por
`test_prestamo_que_envuelve_el_intervalo_resta`.

## Corrección de la 19 aplicada en `19.0.2.0.1`

La actualización a `19.0.2.0.0` **falló al cargar la vista de búsqueda**, con el mismo patrón
que la vez anterior: un idioma de vistas que era correcto hasta la 18 y que en la 19 ya no se
admite.

| Qué | Síntoma | Cómo se comporta la 19 |
|---|---|---|
| `<group expand="0" string="Agrupar por">` en la vista de búsqueda | 🔴 **Rompe la actualización.** `ParseError: Vista no disponible enteza.stock.loan.search definición en …`, **sin decir qué atributo sobra**: el detalle solo va al log del servidor | `<group>` a secas. El cliente web rotula el bloque por su cuenta, igual que en la vista de búsqueda nativa de `stock.picking` |

Lo que despista es que **la vista formulario de este mismo fichero lleva
`<group string="Quién presta a quién">` y es correcta**. No es incoherencia: Odoo valida
contra un esquema RELAX NG solo algunos tipos de vista —`view_validation.schema_valid` lleva
`@validate('calendar', 'graph', 'pivot', 'search', 'list', 'activity')`— y **los formularios
no están en la lista**. La definición de `<group>` de `base/rng/common.rng` no admite ni
`expand` ni `string`.

Se descartaron por el camino los tres candidatos que más lo parecían, todos válidos:
`context_today().strftime(...)` y `allowed_company_ids` en dominios de filtro (están en la
lista blanca `IGNORED_IN_EXPRESSION` de `view_validation.py`, y 6 y 5 vistas del núcleo de
`enteza26` los usan respectivamente), y `filter_domain` sobre un one2many (mismo patrón que
`stock.picking` con `move_line_ids`).

**Esta clase de fallo ya no debería repetirse**: se ha añadido
`.claude/skills/odoo19-dev/scripts/validar_vistas.py`, que reproduce en local esa misma
validación por esquema y señala el atributo y la línea. Es lo único de la instalación que se
puede comprobar aquí sin gastar un ciclo de `git pull` + Actualizar.

```bash
python .claude/skills/odoo19-dev/scripts/validar_vistas.py enteza_prestamo_intercompania
```

Las vistas de este módulo pasan esa validación (comprobado el 2026-08-02, ejecutándolo).

### Alcance de lo verificado

Lo de la tabla está comprobado **contra el código de Odoo 19 Community** (`odoo/orm`,
`ir.rule`, `stock`, `sale`) y **por RPC contra `enteza26`**, que es donde vive.

**El motor de alquiler, solo contra la 18.** `sale_renting` y `sale_stock_renting` son
**Enterprise**: su código de la 19 no es accesible y sus métodos son privados, así que
tampoco se pueden llamar por RPC. La fuente es el repositorio del cliente
`enteza-carrysoft/odoo_enterprise_18` (rama `18.0`), y contra él se ha cotejado línea a línea:

- `_get_unavailable_qty(from_date, to_date=None, **kwargs)` con `ignored_soline_id` y
  `warehouse_id` — coincide con cómo lo llama el módulo.
- `_compute_qty_at_date` — `_rentable()` sigue siendo una réplica fiel, incluida la renuncia
  deliberada al mínimo del periodo.

Sigue siendo **la 18**: si la 19 cambió algo ahí, no hay forma de saberlo desde aquí. Es la
deuda de la que avisa el apartado siguiente.

## Cómo se le pregunta desde fuera (`19.0.1.1.0`)

El resto de la API trabaja con recordsets y `datetime`. Eso **no atraviesa una llamada RPC**,
y como aquí no hay interfaz ni `--test-enable`, la fase 1 se quedó con un motor que **no se
podía ejercitar de ninguna forma**. `consultar()` es la entrada que lo arregla, y es también
la que necesitará el cliente web en la fase 2:

```bash
python .claude/skills/odoo19-dev/scripts/odoo19.py exec enteza.disponibilidad consultar \
    '[[1637], 1, "2026-08-15 08:00:00", "2026-08-17 20:00:00"]' --execute
```

```json
[{"product_id": 1637, "producto": "...", "disponible": 900.0, "prestable": 900.0}]
```

Acepta además `cantidades` (`{product_id: necesaria}`, y entonces cada fila trae `necesita` y
`falta`), `ignorar_linea_id` e `ignorar_prestamo_ids`. Devuelve **lista y no diccionario**
porque al serializar a JSON las claves numéricas se vuelven cadenas y quien llama tendría que
deshacer la conversión. Descarta los productos no almacenables, que es lo que hace el nativo
en `_compute_qty_at_date`, y lo registra en el log.

## Cómo calcula la disponibilidad

```
disponible = rentable − alquilado − prestado_a_terceros
```

- **`rentable`** y **`alquilado`** son nativos. `_rentable()` replica
  `RentalOrderLine._compute_qty_at_date` porque el original es un `compute` que necesita
  líneas existentes, y aquí se pregunta por un alquiler que todavía no existe.
  **Si Odoo cambia ese compute, hay que revisar ese método**: es la única deuda que deja
  delegar en el nativo.
- **`prestado_a_terceros`** es lo único propio: el nativo no sabe nada de préstamos. Sin
  esa resta, la prestamista volvería a vender el material que ya tiene comprometido.

### Limitación de rendimiento conocida

`_get_unavailable_qty` hace `ensure_one()` y una búsqueda por producto. Para el camino de
confirmación (decenas de líneas) va sobrado. Para el análisis por lotes de ~1.000 productos
del §7.1 **no se espera cumplir los 30 s de la prueba 7 del §15**.

Es una limitación **aceptada a cambio de coherencia con el nativo**: si el módulo diera una
cifra distinta a la de la ficha del producto, el comercial no sabría a cuál hacer caso. Si
llega a molestar, la vía es añadir una implementación agrupada **detrás de estos mismos
métodos**, sin tocar a quien los llama.

### Divergencia deliberada con el nativo

Para stock futuro, Odoo **no** busca el mínimo de todo el periodo: usa el previsto del
primer día, por rendimiento y con comentario explícito en su código. El PRP §5.3 sí exige
el mínimo. Hoy se hereda el comportamiento nativo; en escenarios con entradas y salidas
previstas dentro del periodo el número puede ser optimista. Está anotado en el código.

## 🔴 Convivencia con `rental_multi_warehouse`

En este mismo repositorio existe **`rental_multi_warehouse`** (hoy desinstalado en
`enteza26`), que resuelve el mismo problema **entre almacenes de una misma compañía**:
reserva al confirmar el pedido, traslados programados con días de antelación, prioridad de
almacenes, cron de avisos y widget de disponibilidad.

Se ha decidido (2026-08-01) desarrollar este módulo **de forma independiente**, siguiendo
el PRP.

**Consecuencia operativa: no instalar los dos a la vez.** Cada uno trae su propio motor de
disponibilidad y su propio circuito de traslados. Conviviendo se repartirían el mismo stock
sin saber el uno del otro, y las cifras dejarían de cuadrar. Hay que elegir cuál se instala.

Diferencias que justifican que este módulo exista aparte:

- `rental_multi_warehouse` **traslada automáticamente**; aquí el movimiento físico exige
  aprobación humana (PRP D2), que es requisito del arranque en Odoo 19.
- No contempla dos compañías: faltan la ubicación de tránsito sin compañía, el doble
  albarán, `with_company()` y las reglas de registro del §11.
- Su devolución es automática al almacén de origen; aquí se calcula cuánto retener (§7.5).

### Otro aviso del mismo repositorio

**`sale_stock_renting_extension`** (desinstalado) sobrescribe `_compute_qty_at_date`, que es
justo el método que replica `_rentable()`. Si se instala, este módulo dejará de dar la misma
cifra que la ficha del producto y habrá que adaptar la réplica.

## Punto de enganche para la facturación (D4)

El módulo **no factura ni genera asientos**. Deja preparados `_post_loan_hook()` y
`_post_return_hook()` en `enteza.stock.loan`, y los campos `move_id` y `amount_total` sin
usar, para no tener que migrar el modelo si la asesoría fiscal decide que el préstamo
genera documento.

La vía prevista es instalar **`sale_purchase_stock_inter_company_rules`** (disponible en la
instancia, sin instalar) y engancharlo en `_post_loan_hook`, **no reescribir el módulo**.

## Pruebas

`tests/test_disponibilidad.py` cubre la parte propia (resta del material prestado, estados
que comprometen, ámbito por almacén, déficit) y que la delegación está bien enganchada. La
aritmética de `_get_unavailable_qty` ya la prueba Odoo y no se duplica.

⚠️ **Sin ejecutar.** No hay instancia de pruebas ni acceso a `odoo-bin --test-enable`. Están
validadas por sintaxis, no por ejecución.

## Decisiones del 2026-08-02, para la entrega 2

Las dos que faltaban para poder escribir el camino de la confirmación:

| | Decisión | Efecto |
|---|---|---|
| Préstamo automático | **Pregunta antes de reservar** (PRP D5.1) | `action_confirm` abre un diálogo con la propuesta y **no escribe nada** hasta que el comercial acepta. Corrige el §7.0 anterior, que reservaba y avisaba después |
| Widget | **Solo avisa cuando falta** (PRP §10.3) | Con material de sobra se comporta como el nativo. La sección de préstamo aparece únicamente si la compañía propia se queda corta |

Consecuencia técnica de la primera, y es el punto delicado de la entrega: **el bloqueo de
concurrencia no puede mantenerse mientras el diálogo está abierto** —sería una transacción
abierta durante minutos bloqueando a los demás comerciales—, así que el diálogo es una
**propuesta** y la verdad se **recalcula al aceptar**. Si entretanto otro pedido se llevó el
material, no se reserva nada y se dice qué ha cambiado.

Sigue pendiente del §16 del PRP, y no bloquea:

- `[PENDIENTE-1]` a qué almacén se le pide cuando la otra compañía tenga varios. Por defecto,
  el de más prestable; a igualdad, el de menor id.
- `[PENDIENTE-5]`, `[PENDIENTE-6]`, `[PENDIENTE-7]`, para fases posteriores.
