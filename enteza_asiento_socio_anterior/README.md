# Enteza - Arrastrar socio en asientos varios — Odoo 19

Restablece un comportamiento que existía en Odoo 15 y que Odoo 19 no trae de fábrica: al
añadir una línea nueva en un **asiento manual** (Contabilidad → Asientos Contables →
Asientos varios, `move_type = 'entry'`), la línea se rellena con el **mismo socio que la
línea anterior** en cuanto se elige la cuenta contable, en vez de nacer en blanco.

## Por qué hacía falta

`account.move.line.partner_id` es un campo `compute='_compute_partner_id',
precompute=True`: al crear una línea, Odoo la rellena copiando el socio de la **cabecera**
del asiento (`move_id.partner_id`). En una factura eso funciona porque la cabecera ya tiene
el cliente/proveedor. En un asiento vario esa cabecera casi nunca lleva socio, así que cada
línea nace vacía y hay que escribirlo a mano en cada una.

## Funcionamiento

Un `@api.onchange("account_id")` en `account.move.line`: en cuanto se rellena la cuenta de
una línea nueva de un asiento manual, si esa línea todavía no tiene socio, se copia el de la
**última línea de datos anterior** del mismo asiento (se ignoran las líneas de
sección/nota). Se dispara al elegir la cuenta porque es la primera columna editable de la
rejilla — el usuario la rellena y, al tabular hacia el socio, ya lo encuentra puesto.

🔴 **Por qué no es un `compute`/`precompute` como el campo nativo que se hereda:** un campo
`precompute=True` sin `@api.depends` solo tiene garantizado ejecutarse en `create()` (al
guardar), no según se va tabulando por una rejilla editable todavía sin guardar — la primera
versión de este módulo usaba ese enfoque y no llegaba a dispararse nunca en el uso real. El
`onchange` sí está garantizado por Odoo para ver las líneas hermanas ya escritas en pantalla
aunque el asiento no se haya guardado, que es exactamente lo que hace falta aquí.

No toca facturas, abonos ni ningún otro tipo de asiento — solo `move_type = 'entry'`.

## Instalación

1. `git pull` y en el servidor **`invoke git-aggregate`** (Doodba: el `git pull` normal no
   basta, ver `.claude/skills/odoo19-dev/references/instancia-y-conexion.md`).
2. Aplicaciones → Actualizar lista de aplicaciones.
3. Actualizar **Enteza - Arrastrar socio en asientos varios**.
4. Comprobar por RPC que `latest_version` queda en `19.0.1.1.0` antes de darla por
   instalada.

## Notas de mantenimiento

- Sin pruebas ejecutadas: no hay acceso a `odoo-bin --test-enable` en esta instancia.
- "Línea anterior" es la última línea con socio del propio `move_id.line_ids`, no
  necesariamente la fila justo encima en pantalla si el orden se ha alterado a mano
  (cambiando `sequence`). Para el flujo normal de tabular hacia abajo añadiendo líneas,
  coincide.
- Si el usuario deja la cuenta de la primera línea para el final (rellena antes el socio a
  mano, por ejemplo), el onchange no tiene nada de donde copiar todavía — solo actúa sobre
  líneas *posteriores* a la primera que ya tiene socio.
