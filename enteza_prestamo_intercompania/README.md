# Enteza · Préstamo de material entre compañías

Implementa el PRP `.claude/PRPs/prp-modulo-prestamo-intercompania.md`.

**Estado: fase 1 (motor de cálculo).** Modelos, seguridad y motor de disponibilidad. Sin
interfaz, sin flujo de documentos y sin enganche en la confirmación de pedidos todavía.

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

## Pendiente antes de la fase 2

Del §16 del PRP, necesarios para el flujo de documentos:

- `[PENDIENTE-1]` almacenes reales por compañía
- `[PENDIENTE-3]` si los 3 días de antelación dependen del par de almacenes
- `[PENDIENTE-8]` si se puede confirmar un pedido que no se puede servir
- `[PENDIENTE-9]` quién manda si las dos compañías necesitan el material a la vez
