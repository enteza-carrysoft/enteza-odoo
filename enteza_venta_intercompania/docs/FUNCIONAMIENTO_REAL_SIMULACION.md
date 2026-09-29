# Funcionamiento real de la venta intercompañía: simulación de un proceso completo

**Módulos:** `rental_custom` 19.0.1.14.0 y `enteza_venta_intercompania` 19.0.1.1.0, instalados en la instancia `enteza`.
**Fecha del documento:** 29 de septiembre de 2026.
**Para:** quien vaya a probar el circuito y quien lo vaya a mantener.

> **Cómo leer este documento y qué valor tiene.** Está escrito leyendo el código del módulo (modelos, vistas y seguridad), no ejecutándolo. Los documentos, cantidades e importes de la simulación son ficticios y sirven para seguir el rastro; los nombres reales (números de pedido, de albarán y de factura) los asigna Odoo. Las pruebas automáticas del módulo están validadas por sintaxis y **no ejecutadas**, porque el hosting no permite `--test-enable`. Este documento no sustituye a la prueba real con una cesión de un artículo: al final (apartado 10) están los puntos exactos que esa prueba tiene que confirmar.

---

## 1. Resumen en una página

Vimaple deja material a Stileum con un **alquiler de cesión**. Cuando un cliente de Stileum pierde unidades y Stileum se las factura, esas unidades eran de Vimaple, así que Vimaple se las tiene que vender a Stileum.

El módulo hace tres cosas, todas **preparadas y nunca cerradas** (ninguna factura se publica sola, ningún albarán se valida solo):

- **Al validar la entrega de la cesión** en Vimaple: crea en Stileum una **recepción** del mismo material, con propietario Vimaple.
- **Al publicar la factura de faltas** de Stileum: crea en Vimaple una **venta a Stileum**, la confirma, deja su **factura en borrador** y descuenta esas unidades de lo que Vimaple espera recibir de vuelta.
- **Al validar una devolución de la cesión** en Vimaple: crea en Stileum una **salida** de las unidades devueltas.

Lo único que se confirma sin intervención humana es la venta de Vimaple a Stileum, y solo para poder crear su factura.

| Qué se ve | Dónde |
|---|---|
| Casilla «Cesión intercompañía» y tres campos nuevos | Pedido de alquiler, debajo del cliente |
| Aviso amarillo y botón «Procesar venta intercompañía» | Factura de cliente, solo si quedó «Pendiente» |
| Botón inteligente «Factura intercompañía» | Factura de cliente de Stileum, cuando existe la de Vimaple |
| Recepciones y salidas nuevas | Inventario de Stileum, con el historial diciendo de qué cesión vienen |

---

## 2. Datos de la simulación

| Elemento | Valor |
|---|---|
| Compañía dueña | Vimaple (almacén Sevilla, `SEV`) |
| Compañía receptora | Stileum (almacén Jerez, `JER`) |
| Artículo | Silla plegable (bien almacenable, alquilable) |
| Existencias iniciales | 100 sillas en Stock de Sevilla |
| Cuota de cesión | 50 € (línea de servicio «Cuota de cesión») |
| Tarifa «Intercompañía Stileum» | 60 € por silla perdida |
| Precio de la silla perdida al cliente final | 100 € |
| Cliente final de Stileum | «Cliente Boda» |
| Diario de faltas intercompañía | «Facturas STILEUM» (compañía Vimaple) |

Documentos que aparecen a lo largo del proceso, con el nombre con el que se les llama aquí:

| Nombre en este documento | Qué es | Compañía |
|---|---|---|
| **Cesión A** | Alquiler de Vimaple a Stileum, marcado como cesión | Vimaple |
| **Entrega A** | Albarán de salida de la cesión (Stock → Alquiler) | Vimaple |
| **Devolución A** | Albarán de vuelta de la cesión (Alquiler → Stock), que se crea con la cesión | Vimaple |
| **Recepción E1** | Albarán espejo de la entrega (Proveedores → Jerez) | Stileum |
| **Alquiler B** | Alquiler de Stileum a «Cliente Boda» | Stileum |
| **Venta F** | Venta de faltas de Stileum al cliente (la crea «Facturar las Faltas») | Stileum |
| **Factura F1** | Factura de esa venta al cliente | Stileum |
| **Venta IC** | Venta de Vimaple a Stileum por las mismas unidades | Vimaple |
| **Factura IC** | Factura de la Venta IC, en borrador | Vimaple |
| **Salida S1** | Albarán espejo de la devolución (Jerez → Clientes) | Stileum |

---

## 3. Simulación paso a paso

### Paso 1. Vimaple crea y confirma la cesión

Con la compañía Vimaple activa, en Alquiler, pedido nuevo con cliente **STILEUM, S.L.** y 100 sillas.

Al marcar **«Cesión intercompañía»** ocurre esto en la pantalla:

- **Compañía receptora** se rellena sola con Stileum. Odoo la busca entre las compañías cuyo contacto es el cliente del pedido. Si el cliente no es ninguna compañía del grupo, el campo queda vacío y al guardar sale el error: «En una cesión intercompañía el cliente tiene que ser otra compañía del grupo».
- **Almacén receptor** propone el primer almacén de Stileum (en este caso Jerez). Si Stileum tuviera varios, se elige a mano.
- **Diario de faltas intercompañía** hay que elegirlo: solo ofrece diarios de venta de Vimaple.
- Las 100 sillas quedan a **0 €**, porque el módulo fuerza ese precio en las líneas de material de una cesión.
- Se añade a mano la línea de servicio **«Cuota de cesión»**: 50 €.

Al pulsar **Confirmar**, Odoo comprueba que hay almacén receptor y diario. Si falta alguno, no deja confirmar: «Falta el almacén receptor de la cesión…» o «Falta el diario de faltas intercompañía de la cesión…».

Confirmada la cesión, el alquiler de Odoo crea sus albaranes de alquiler: la **Entrega A** (Stock → Alquiler) y la **Devolución A** (Alquiler → Stock), esta última a la espera. **El módulo depende de que la Devolución A exista desde este momento**: es donde se descuentan las faltas más adelante.

| Después del paso 1 | Cantidad |
|---|---|
| Stock de Sevilla (Vimaple) | 100 |
| Entrega A | 100, lista para validar |
| Devolución A | 100, a la espera |
| Nada en Stileum todavía | |

### Paso 2. Vimaple valida la Entrega A

El almacén de Vimaple valida la entrega. En ese instante, sin que nadie pulse nada más, el módulo:

1. Comprueba que el albarán es de una cesión y que va **hacia** la ubicación Alquiler de Vimaple: eso significa «entrega».
2. Comprueba que ese albarán no tenga ya su espejo (hay un índice único, no puede duplicarse).
3. Crea en Stileum la **Recepción E1**, con estos datos:
   - tipo de operación: recepción del almacén receptor (Jerez);
   - origen: Proveedores; destino: Stock de Jerez;
   - contacto y **propietario: Vimaple**;
   - las líneas son las cantidades **realmente entregadas** (no las previstas);
   - origen del documento: «número de la cesión - número de la entrega».
4. La **confirma**, sin validarla. Viniendo de Proveedores queda lista para validar.
5. Escribe una nota en el historial de los dos albaranes:
   - en la Recepción E1: «Preparado al validar (Entrega A) de la cesión (Cesión A) (Vimaple).»
   - en la Entrega A: «Preparado (Recepción E1) en Stileum para validarlo allí.»

No se usa la ubicación de tránsito intercompañía a propósito: en la 19 exige existencias para reservar y Vimaple no deja nada allí, porque su material pasa a su propia ubicación Alquiler.

| Después del paso 2 | Cantidad |
|---|---|
| Stock de Sevilla | 0 |
| Alquiler de Vimaple | 100 (sigue siendo inventario de Vimaple) |
| Recepción E1 | 100, lista, sin validar |

### Paso 3. Stileum valida la Recepción E1

El almacén de Stileum abre Inventario → Recepciones, comprueba lo que llegó y valida. El módulo no interviene.

| Después del paso 3 | Cantidad |
|---|---|
| Stock de Jerez | 100, con propietario Vimaple |
| Alquiler de Vimaple | 100 |

El **propietario Vimaple** (función Consigna, que hay que tener activada) hace que Stileum no valore esas sillas como existencia suya.

### Paso 4. Stileum alquila a «Cliente Boda»

Nada cambia respecto a un alquiler normal. Alquiler B: 80 sillas, entrega a cliente y devolución prevista. Al validar la entrega, 80 sillas pasan de Stock de Jerez a la ubicación Alquiler de Stileum.

| Después del paso 4 | Cantidad |
|---|---|
| Stock de Jerez | 20 |
| Alquiler de Stileum | 80 |

Esta entrega **no** genera espejo: el módulo solo actúa en albaranes cuyo pedido es una cesión.

### Paso 5. El cliente devuelve 75 y Stileum factura las 5 faltas

Es la parte del alquiler normal, la que aporta `rental_custom`:

1. En la recogida del Alquiler B, Stileum escribe **5** en la columna **«Faltas»** de la línea de sillas. La cantidad pasa a 75.
2. Pulsa **«Facturar las Faltas»**. Se crea la **Venta F** (Stileum → «Cliente Boda», 5 sillas). Va enlazada al Alquiler B mediante `rental_order_id`.
3. Valida la recogida con las 75 sillas.
4. Confirma la Venta F y crea la **Factura F1**: 5 × 100 € = **500 €**.
5. La salida de la Venta F sale de Alquiler (donde siguen las 5 sillas) y hay que **validarla**, no cancelarla.

| Después del paso 5 | Cantidad |
|---|---|
| Stock de Jerez | 95 |
| Alquiler de Stileum | 5 (hasta validar la salida de la Venta F) |

### Paso 6. Stileum publica la Factura F1: aquí actúa el módulo

Al pulsar **Publicar**, Odoo hace primero todo lo normal. Después el módulo, en este orden:

**6.1. Selecciona las líneas.** Solo cuentan las líneas que cumplan las tres condiciones: producto almacenable, línea de pedido que no es de alquiler, y pedido con enlace a un alquiler (`rental_order_id`). La Factura F1 tiene una línea (5 sillas) y entra. Una factura con solo servicios, o con faltas del importador de hoja de cálculo, no entra y no pasa nada.

**6.2. Bloquea la factura** para que no la procesen dos veces a la vez (publicación y botón simultáneos) y comprueba que no exista ya un enlace.

**6.3. Busca a qué cesión pertenecen esas sillas.** Mira, en Vimaple, los movimientos de devolución pendientes de alquileres de cesión hacia Stileum, del mismo artículo. Los ordena por fecha, del más antiguo al más nuevo. Aquí solo hay uno: el de la **Devolución A** (100 sillas).

**6.4. Comprueba y reparte.**
- Si algún movimiento tiene faltas anotadas a mano sin facturar, para con error (apartado 7).
- Reparte las 5 unidades: toma 5 del movimiento de la Devolución A.
- Si sobraran unidades sin cesión donde ponerlas, para con error «Se facturan X de … más de las que quedan pendientes en los alquileres de cesión».

**6.5. Todo lo que sigue va dentro de una transacción parcial: se hace entero o no se hace nada.**
- Anota **5** en «Faltas» del movimiento de la Devolución A.
- Llama a «Facturar las Faltas» sobre la Devolución A, en la compañía Vimaple. Crea la **Venta IC** (Vimaple → Stileum, 5 sillas), con el **precio de la tarifa que Vimaple tenga para Stileum**: 60 €. La Devolución A pasa a esperar **95**.
- Escribe en la Venta IC: «Generado automáticamente al publicar (Factura F1), factura de faltas de Stileum.»
- Le pone como diario el de la cesión («Facturas STILEUM»).
- **Confirma la Venta IC.** Esto crea su albarán de salida desde Alquiler de Vimaple hacia Clientes, sin validar. Si tras confirmar la venta no queda en estado «Pedido de venta» (por ejemplo, por un diálogo de otro módulo), para con error y no crea la factura.
- **Crea la Factura IC** en borrador: 5 × 60 € = **300 €** más impuestos, en «Facturas STILEUM». No se publica. En su historial: «Factura intercompañía por el material perdido facturado en (Factura F1) (Stileum). Revisarla y publicarla.»
- Guarda un **enlace** que une línea de factura → cesión → movimiento de la devolución → venta → factura, con la cantidad.

**6.6. En la Factura F1** queda el campo «Venta intercompañía» = **Generada**, una nota «Preparada en borrador la factura intercompañía del material perdido: (Factura IC)» y el botón inteligente **«Factura intercompañía»**.

| Después del paso 6 | Estado |
|---|---|
| Factura F1 (Stileum) | Publicada, «Venta intercompañía: Generada» |
| Venta IC (Vimaple) | Confirmada; salida de Alquiler a Clientes por 5, sin validar |
| Factura IC (Vimaple) | Borrador, 300 € + impuestos |
| Devolución A (Vimaple) | Espera 95 (antes 100) |
| Inventario físico | Sin cambios todavía |

### Paso 7. Vimaple revisa y publica; los dos almacenes validan sus salidas

Con **las dos compañías activas** en el selector:

1. Contabilidad de Stileum abre la Factura F1 y pulsa **«Factura intercompañía»**. Si hay una sola factura, abre directamente su ficha; si hay varias, abre una lista.
2. Contabilidad de Vimaple revisa que artículo, cantidad (5), precio (60 €), impuestos y cliente son correctos, y **publica** la Factura IC.
3. **Inter-Company Transactions** (módulo estándar de Odoo, no de este) crea en Stileum la **factura de proveedor** de 300 €, en borrador según la configuración. Contabilidad de Stileum la revisa y publica.
4. El almacén de Vimaple **valida la salida de la Venta IC**: las 5 sillas dejan de figurar en su ubicación Alquiler.
5. El almacén de Stileum **valida la salida de la Venta F**: las 5 sillas dejan de figurar en su ubicación Alquiler.

| Después del paso 7 | Cantidad |
|---|---|
| Stock de Jerez | 95, propietario Vimaple |
| Alquiler de Vimaple | 95 |
| Alquiler de Stileum | 0 |

### Paso 8. Fin de la cesión: Stileum devuelve las 95 sillas

1. El material vuelve físicamente de Jerez a Sevilla.
2. El almacén de Vimaple valida la **Devolución A** con 95 sillas (Alquiler → Stock). La cesión queda cerrada, porque las 5 perdidas ya se habían descontado.
3. Al validarla, el módulo comprueba que el albarán sale **desde** Alquiler de Vimaple: eso significa «devolución». Crea en Stileum la **Salida S1**: Stock de Jerez → Clientes, 95 sillas, confirmada y sin validar. Esta salida **no lleva propietario** a propósito: así no reescribe el de las líneas ya reservadas.
4. Anota en los historiales: «Preparado (Salida S1) en Stileum para validarlo allí.» y, en S1, «Preparado al validar (Devolución A) de la cesión (Cesión A) (Vimaple).»
5. El almacén de Stileum **valida la Salida S1**.

Si la devolución es parcial y se acepta el pedido pendiente, el espejo se crea solo por lo que se validó y el resto sigue esperando.

| Estado final | Cantidad |
|---|---|
| Stock de Sevilla | 95 |
| Stock de Jerez | 0 |
| Alquiler de Vimaple y de Stileum | 0 |
| Sillas vendidas a Stileum | 5 |

### Balance de la simulación

| | Vimaple | Stileum |
|---|---|---|
| Cuota de cesión | +50 € (factura del alquiler de cesión) | −50 € |
| Faltas al cliente final | | +500 € |
| Material perdido | +300 € (5 × 60 €) | −300 € |
| Resultado del material perdido | 5 sillas vendidas a 60 € | 200 € de margen (500 − 300) |
| Inventario | Recupera 95 sillas | Se queda con 0 |

---

## 4. Estado de cada campo a lo largo del proceso

**Campo «Venta intercompañía» de la factura de cliente (`enteza_ic_estado`):**

| Valor | Cuándo | Qué se ve |
|---|---|---|
| Vacío | La factura no tiene material cedido, o todavía no se ha intentado | Nada |
| **Pendiente** | Se intentó y algo falló (apartado 7) | Aviso amarillo y botón «Procesar venta intercompañía» |
| **Generada** | Se creó la venta y su factura | Botón inteligente «Factura intercompañía» |

**Campos de la cesión (`sale.order`):**

| Campo | Se rellena | Obligatorio |
|---|---|---|
| Cesión intercompañía | A mano | No |
| Compañía receptora | Sola, según el cliente | Sí, calculado |
| Almacén receptor | Propuesto el primero de la receptora | Al confirmar |
| Diario de faltas intercompañía | A mano | Al confirmar |

La casilla no se puede cambiar en un pedido cancelado, y el almacén receptor queda de solo lectura una vez confirmado el pedido.

---

## 5. Otros escenarios

### 5.1. Faltas repartidas entre dos cesiones abiertas

Cesión A: 60 sillas (más antigua). Cesión B: 40 sillas. «Cliente Boda» pierde **70**.

- Las 70 se reparten por fecha del movimiento: **60 a la Cesión A y 10 a la Cesión B**.
- Se crean **dos ventas y dos facturas** en borrador, una por cada devolución afectada, en el mismo diario de la cesión.
- La Factura F1 guarda dos enlaces (uno por tramo) y su botón inteligente abre una **lista** de dos facturas, no una ficha.
- La Devolución A pasa a esperar 0 y la B a esperar 30.

### 5.2. Se facturan más unidades de las que quedan en las cesiones

Quedan 5 sillas pendientes en las cesiones, pero Stileum factura 8.

- La Factura F1 **se publica igualmente**: el problema es interno y no puede impedir facturar al cliente.
- No se crea **nada** en Vimaple (todo va dentro de la transacción parcial, que se deshace).
- La factura queda **Pendiente**, con el aviso amarillo y esta nota en el historial: «No se ha podido preparar la venta intercompañía del material perdido: Se facturan 3.0 unidades de Silla plegable más de las que quedan pendientes en los alquileres de cesión.»
- Se corrige la causa (una cesión que falta, una cantidad mal puesta) y se pulsa **«Procesar venta intercompañía»**. Se puede pulsar cuantas veces haga falta.

### 5.3. Producto que Stileum no recibió de Vimaple

La factura de faltas tiene una mesa que no está en ninguna cesión. El módulo no encuentra movimientos de devolución para ese artículo y **lo ignora**: se considera material propio de Stileum. No hay aviso, no hay estado y no se crea nada.

### 5.4. Faltas anotadas a mano en la devolución de la cesión

Alguien escribió un número en «Faltas» en la Devolución A de Vimaple sin facturar. Al publicar una factura de faltas de Stileum, el módulo lo detecta y la factura queda **Pendiente**: «El albarán (Devolución A) de la cesión tiene faltas anotadas a mano sin facturar. Hay que facturarlas o borrarlas antes.» Se resuelve y se reprocesa.

### 5.5. Doble clic o reproceso

- Si se publica y a la vez alguien pulsa el botón, el bloqueo hace que solo uno cree documentos; el otro ve que ya hay enlace y marca «Generada».
- Un índice único impide que una misma línea de factura se atribuya dos veces a la misma cesión.
- Un índice único impide que un albarán de cesión tenga dos espejos.

### 5.6. Lo que no es automático

| Situación | Qué pasa |
|---|---|
| Nota de crédito al cliente final | Nada. Si hay que abonar a Stileum, se hace a mano. |
| El cliente devuelve después material dado por perdido | Nada. La cesión ya descontó esas unidades. |
| Cancelar la Venta IC | No se puede borrar mientras esté enlazada: se cancela. Consultarlo antes, porque el descuento en la cesión no se revierte solo. |
| Faltas del importador de hoja de cálculo | No llevan enlace al alquiler y no generan nada |

---

## 6. Permisos y compañías

- El módulo **no añade grupos nuevos**. Usa los de facturación, ventas e inventario de siempre. El botón «Procesar venta intercompañía» exige el grupo de facturación (`account.group_account_invoice`).
- El módulo trabaja con permisos elevados (`sudo`) en los puntos en que un usuario de una compañía tiene que crear o leer documentos de la otra: buscar la compañía receptora, crear el espejo, buscar las devoluciones de la cesión, crear los enlaces. Un usuario de Stileum que publica una factura no necesita acceso a Vimaple para que el proceso funcione.
- Los enlaces son de solo lectura para los usuarios, y una regla los hace visibles tanto a la compañía receptora como a la dueña.
- **Para abrir desde Stileum la factura de Vimaple**, el usuario necesita tener las dos compañías activas en el selector.

---

## 7. Cómo sabe el módulo qué hacer: reglas exactas

| Decisión | Regla en el código |
|---|---|
| ¿Es entrega o devolución? | Si el albarán acaba en la ubicación Alquiler de su compañía, es entrega; si sale de ella, devolución; si ninguna, no hace nada |
| ¿Qué cantidad va al espejo? | La cantidad realmente hecha de cada movimiento validado |
| ¿Qué líneas de factura cuentan? | Producto almacenable + línea de pedido que no es de alquiler + pedido con `rental_order_id` |
| ¿A qué cesión se atribuyen? | Movimientos de alquiler de cesión hacia esa compañía, del mismo artículo, aún no hechos ni cancelados y que salen de Alquiler; del más antiguo al más nuevo |
| ¿Qué precio lleva la Venta IC? | El de la tarifa que la compañía dueña tenga asignada a la receptora |
| ¿Qué diario lleva? | El elegido en la cesión |
| ¿Cuándo se para? | Faltas manuales sin facturar en la cesión, o más unidades facturadas que pendientes: la factura queda «Pendiente» |
| ¿Se procesan las facturas rectificativas? | No: solo facturas de cliente (`out_invoice`) |

---

## 8. Configuración mínima para que la simulación funcione tal cual

1. `rental_custom` en 19.0.1.14.0 y `enteza_venta_intercompania` instalado.
2. **Inter-Company Transactions** activo, con «Generar facturas de proveedor» en borrador en las dos compañías. Sin esto no aparece la factura de proveedor en Stileum (paso 7).
3. **Tarifas:** «Tarifa general» primero, luego activar Tarifas, luego «Intercompañía Stileum» asignada al contacto Stileum con la compañía Vimaple activa. Sin tarifa, la Venta IC saldría al precio de venta normal del artículo.
4. **Consigna** activada en Inventario, o la recepción no admitirá propietario.
5. Servicio **«Cuota de cesión»** creado.
6. Diario **«Facturas STILEUM»** de tipo venta en Vimaple.
7. Contacto de cada compañía enlazado a su compañía (es lo que permite deducir la compañía receptora).

---

## 9. Qué se ha leído y qué no

| Cosa | Fuente |
|---|---|
| Modelos, vistas, seguridad y flujo del módulo | Código de `enteza_venta_intercompania`, leído entero |
| «Facturar las Faltas», columna «Faltas» y salida de Alquiler | Descrito según el README y el manual; su código está en `rental_custom` y no se ha vuelto a leer para este documento |
| Motor de alquiler (albaranes de entrega y devolución, `qty_returned`) | Solo legible en la 18 Enterprise; no verificado en la 19 |
| Campos de Inter-Company Transactions | No verificados; el módulo no depende de ellos |
| Ejecución real | **Ninguna.** Las pruebas están validadas por sintaxis y no ejecutadas |

---

## 10. Qué tiene que confirmar la prueba real

Con una cesión de **un solo artículo** y una unidad de falta, comprobar por este orden:

1. **Al confirmar la cesión**, existe la Devolución A (Alquiler → Stock) con la cantidad pedida. Todo el reparto de faltas depende de ese movimiento.
2. **Al validar la Entrega A**, aparece la Recepción E1 en Stileum, lista, con propietario Vimaple y sin validar.
3. **Al publicar la factura de faltas**, aparece la Factura IC en borrador con el **precio de la tarifa**, no el de venta general.
4. La Devolución A pasa a esperar una unidad menos.
5. El botón «Factura intercompañía» abre la factura de Vimaple (con las dos compañías activas).
6. Al publicar la Factura IC, aparece la **factura de proveedor** en Stileum.
7. Al validar la Devolución A, aparece la Salida S1 en Stileum.
8. Forzar un exceso (facturar una unidad más de la cuenta) y comprobar que queda «Pendiente», que no se crea nada en Vimaple y que «Procesar venta intercompañía» lo resuelve al corregir la cantidad.
9. Pulsar «Procesar venta intercompañía» dos veces y comprobar que no duplica.

**Puntos de diseño que conviene tener presentes:**

- El módulo da por hecho que Stileum **no tiene material propio** de los artículos cedidos. Si Stileum pierde sillas propias y cedidas a la vez, todo lo perdido se atribuye primero a la cesión y, si se pasa de lo pendiente, la factura queda «Pendiente» aunque una parte fuera realmente suya.
- Se crea **una venta y una factura por cada devolución de cesión afectada**, no una por factura de faltas.
- El motor de alquiler de la 19 no se ha podido leer. Si en la 19 la Devolución A no existe desde la confirmación, o no sale de Alquiler, el paso 6 fallará con «Pendiente» y habrá que ajustar el módulo.
