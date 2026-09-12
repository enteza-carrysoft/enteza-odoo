# enteza-odoo

Directorio de **addons de Odoo 19 Enterprise** de Enteza. Cada carpeta de la raíz es un
módulo que se instala en la instancia `enteza26`.

## Lo primero

Antes de tocar nada, cargar el skill **`odoo19-dev`**
(`.claude/skills/odoo19-dev/SKILL.md`). Concentra todo lo verificado sobre la instancia: cómo
consultarla, cómo funciona el alquiler nativo, las convenciones de la 19, el catálogo de
módulos con su estado real y dónde está el código fuente de Odoo.

## Contexto en tres líneas

Enteza alquila material para eventos (sillas, mesas, vajilla), con dos sociedades
independientes: **Visueña de Material Plegable ("Vimaple")** y **Stileum**. Migraron de Odoo
15 a Odoo 19 EE en agosto de 2026. Desde el 2026-08-07 **el stock se controla desde Odoo**:
ya no llevan el almacén en paralelo con la aplicación externa.

Consecuencia para cualquier desarrollo: **nada se mueve sin aprobación humana**, y todo tiene
que ser reversible y trazable. Eso pesa más que la automatización.

## Restricciones que condicionan todo

1. **`enteza26` es producción**, con la contabilidad migrada y cuadrada al céntimo. No hay
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
4. **Apenas hay existencias.** La carga de inventario empezó a primeros de agosto de 2026: el
   2026-08-01 había 4 `stock.quant` con cantidad. Cualquier cálculo de disponibilidad dirá
   "no hay stock" de casi todo, y **no es un fallo del código**. Comprobarlo por RPC antes de
   dar por rota una cifra.

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
