# enteza-odoo

Directorio de **addons de Odoo 19 Enterprise** de Enteza. Cada carpeta de la raíz es un
módulo que se instala en la instancia `enteza`.

## Lo primero

Antes de tocar nada, cargar el skill **`odoo19-dev`**
(`.claude/skills/odoo19-dev/SKILL.md`). Concentra todo lo verificado sobre la instancia: cómo
consultarla, cómo funciona el alquiler nativo, las convenciones de la 19, el catálogo de
módulos con su estado real y dónde está el código fuente de Odoo.

## Contexto en tres líneas

Enteza alquila material para eventos (sillas, mesas, vajilla), con dos sociedades
independientes: **Visueña de Material Plegable ("Vimaple")** y **Stileum**. Migraron de Odoo
15 a Odoo 19 EE en agosto de 2026. **El almacén físico NO se gestiona en Odoo** (corregido el
2026-10-07: lo que se anotó el 2026-08-07 era falso). Siguen con la aplicación legacy y los
pedidos en papel. En Odoo las existencias solo se tocan con ajustes (altas por compra, bajas
por faltas), y desde el 2026-10-07 el ajuste **«Traslado de alquiler»
(`group_rental_stock_picking`) está desactivado**: los alquileres ya no generan albaranes.

Consecuencia para cualquier desarrollo: **nada se mueve sin aprobación humana**, y todo tiene
que ser reversible y trazable. Eso pesa más que la automatización.

## Restricciones que condicionan todo

1. **`enteza` es producción**, con la contabilidad migrada y cuadrada al céntimo. No hay
   staging. Confirmar con el usuario antes de cualquier escritura.
2. **El hosting es Doodba, no un `git pull` plano**: el addons path se rellena con
   `git-aggregate` a partir de `repos.yaml`, y ese paso **no se dispara solo con el push** —
   hay que invocar `invoke git-aggregate` en el servidor. Commit → push → `invoke
   git-aggregate` → Actualizar lista de aplicaciones → Instalar. Que un módulo **aparezca**
   en la lista no quiere decir que esté instalado: comprobar el `state` por RPC. Sigue sin
   haber acceso a `odoo -u` ni a `odoo-bin --test-enable`. El camino alternativo del zip por
   `base.import.module` tiene dos trampas con fallo silencioso — están documentadas en el
   skill, igual que el detalle completo de este fallo (medido el 2026-09-13).
3. **No se pueden ejecutar pruebas automatizadas.** Se escriben igualmente, pero al entregar
   hay que decir siempre que están validadas por sintaxis y **no ejecutadas**.
4. **Las existencias de Odoo no son fiables todavía.** Hay cantidades cargadas, pero con
   errores: 104.017 uds fantasma en `Customers/Alquiler`, más de 1.000 quants negativos y
   datos imposibles como 1.000.009 kg de mantelería en Jerez. El 2026-10-07 se cancelaron
   los 503 albaranes de alquileres pasados que nadie había validado. Retenían 631.545 uds
   reservadas y dejaban negativa la disponibilidad futura de casi todo. Falta el
   **inventario de partida** desde el Excel del legacy (plan aparcado en la memoria del
   proyecto). Antes de dar por rota una cifra de disponibilidad, comprobar por RPC
   `qty_available`, `virtual_available` y la reserva: el fallo suele estar en los datos,
   no en el código.
5. **Las faltas se registran desde el pedido.** Sin albaranes de alquiler, el camino es
   «Registrar faltas» del pedido (`rental_custom` ≥ 19.0.1.16.0). Al confirmar el pedido de
   faltas se valida sola su salida, y esa es la baja del material. El botón «Facturar las
   Faltas» del albarán sigue existiendo para los pedidos que todavía tengan albaranes.

## Antes de crear un módulo

**Comprobar si ya existe.** Hay 33 módulos en el repositorio y varios resuelven cosas que
parecen pendientes. Ver `references/catalogo-modulos.md` del skill.

Y no instalar nunca dos módulos que calculen disponibilidad de stock a la vez: se reparten el
mismo material sin saber uno del otro.

## Configuración local

Crear `.env.local` en la raíz (no se versiona) con `ODOO19_URL`, `ODOO19_DB`, `ODOO19_USER` y
`ODOO19_API_KEY`. Luego:

```bash
python .claude/skills/odoo19-dev/scripts/odoo19.py search res.company '[]' id,name
```

## Proyecto hermano

La **migración 15→19** vive aparte, en `E:\apps\AI\MigrarOdoo`, con su propio skill
`odoo-ops` (specs S1–S16, `id_map`, cuadre de facturas, delta, extractos, activos fijos). Si
la pregunta es "cómo migro este registro de la 15", es allí. Aquí solo se desarrolla sobre
la 19.
