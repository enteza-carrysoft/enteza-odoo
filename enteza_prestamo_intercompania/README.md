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
