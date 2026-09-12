# Enteza - Arrastrar socio en asientos varios — Odoo 19

Restablece un comportamiento que existía en Odoo 15 y que Odoo 19 no trae de fábrica: al
añadir una línea nueva en un **asiento manual** (Contabilidad → Asientos Contables →
Asientos varios, `move_type = 'entry'`), la línea nace con el **mismo socio que la línea
anterior**, en vez de en blanco.

## Por qué hacía falta

`account.move.line.partner_id` es un campo `compute='_compute_partner_id',
precompute=True`: al crear una línea, Odoo la rellena copiando el socio de la **cabecera**
del asiento (`move_id.partner_id`). En una factura eso funciona porque la cabecera ya tiene
el cliente/proveedor. En un asiento vario esa cabecera casi nunca lleva socio, así que cada
línea nace vacía y hay que escribirlo a mano en cada una.

## Funcionamiento

Se hereda `_compute_partner_id` en `account.move.line`: se llama primero al compute nativo
(sin tocarlo) y, solo si la línea sigue sin socio y pertenece a un asiento manual, se copia
el socio de la **última línea de datos anterior** del mismo asiento (se ignoran las líneas
de sección/nota). Es el mismo momento en el que Odoo ya autocompleta otros campos al añadir
una línea nueva (cantidad, unidad de medida…), así que no hace falta ningún ajuste en la
vista ni en JavaScript.

No toca facturas, abonos ni ningún otro tipo de asiento — solo `move_type = 'entry'`.

## Instalación

1. `git pull` y en el servidor **`invoke git-aggregate`** (Doodba: el `git pull` normal no
   basta, ver `.claude/skills/odoo19-dev/references/instancia-y-conexion.md`).
2. Aplicaciones → Actualizar lista de aplicaciones.
3. Instalar **Enteza - Arrastrar socio en asientos varios**.
4. Comprobar por RPC que `latest_version` queda en `19.0.1.0.0` antes de darla por
   instalada.

## Notas de mantenimiento

- Sin pruebas ejecutadas: no hay acceso a `odoo-bin --test-enable` en esta instancia. La
  lógica está verificada leyendo el código fuente de `account.move.line` en
  `odoo/odoo` rama `19.0` (el compute nativo y su comentario "Do not depend on
  move_id.partner_id"), pero el comportamiento exacto al pulsar Tabulador en la rejilla
  editable **no se ha probado en el navegador** — probarlo tras desplegar.
- "Línea anterior" es la última línea con socio del propio `move_id.line_ids`, no
  necesariamente la fila justo encima en pantalla si el orden se ha alterado a mano
  (cambiando `sequence`). Para el flujo normal de tabular hacia abajo añadiendo líneas,
  coincide.
