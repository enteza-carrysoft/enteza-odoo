# Instancia, conexión y despliegue

## La instancia

| Dato | Valor |
|---|---|
| Nombre | `enteza26` |
| Versión | Odoo 19 **Enterprise** |
| Hosting | Xtendoo (`enteza19.xtendoo.es`) |
| Entorno | **Producción**, con la contabilidad migrada desde Odoo 15 y cuadrada al céntimo |
| Compañías | `1` Visueña de Material Plegable, S.L. ("Vimaple") · `2` Stileum |
| Jerarquía | **Ninguna**: las dos compañías son independientes, sin `parent_id` |

No hay instancia de staging ni de desarrollo. No hay acceso al filesystem del servidor ni a
`odoo-bin`. Todo se hace por RPC.

**Consecuencia que hay que decir en cada entrega:** no se pueden ejecutar pruebas
automatizadas (`--test-enable`). Lo que se entrega está validado por sintaxis, no ejecutado.

## Credenciales

En `.env.local` en la raíz del repositorio, **nunca versionado ni impreso**:

```
ODOO19_URL=https://enteza19.xtendoo.es
ODOO19_DB=enteza26
ODOO19_USER=...
ODOO19_API_KEY=...
```

Si el fichero no existe, el cliente RPC dice exactamente qué variables faltan.

## El cliente RPC

`.claude/skills/odoo19-dev/scripts/odoo19.py`. Solo biblioteca estándar de Python: no hay que
instalar nada ni existe proyecto Node en este repositorio.

```bash
python .claude/skills/odoo19-dev/scripts/odoo19.py <acción> ...
```

| Acción | Uso |
|---|---|
| `fields <modelo> [--filtro txt]` | Campos del modelo con tipo, `store`, relación y obligatoriedad |
| `search <modelo> <dominio> [campos]` | `search_read` |
| `read <modelo> <ids> [campos]` | Lectura por id |
| `count <modelo> [dominio]` | `search_count` |
| `exec <modelo> <método> <args>` | Ejecuta un método |
| `create` / `write` | Altas y cambios |

**Las tres últimas no hacen nada sin `--execute`**: sin el flag muestran lo que harían. La
base es producción y el freno es deliberado.

Flags: `--limit N`, `--order "campo asc"`, `--company N`, `--filtro txt`.

`--company` es **obligatorio** al leer o escribir campos company-dependent. El caso más
habitual es el código de `account.account`, que es distinto en cada compañía.

Los dominios van en JSON, con comillas simples por fuera para el shell:

```bash
python ... search sale.order '[["is_rental_order","=",true],["state","=","sale"]]' name,rental_start_date --limit 20
```

Ante un error de Odoo, el cliente saca el mensaje y el `debug`: **casi siempre nombra el
campo exacto que falla**. Merece la pena leerlo antes de suponer nada.

## Cómo se instala un módulo

🔴 **No hay acceso al filesystem del servidor**, así que no hay `odoo -u`. La única vía es
empaquetar el módulo en un zip e importarlo con `base.import.module` (Aplicaciones → Importar
módulo, o por RPC).

Ese camino tiene dos trampas medidas en este proyecto, **las dos con fallo silencioso**:

### 1. Una vista que falla tira el módulo entero

La importación en caliente valida las vistas dentro de la misma transacción en la que se crean
los campos. Un campo nuevo del propio módulo **puede no estar listo en el registro ORM** en
ese momento, así que una vista que lo referencia falla — y Odoo hace **rollback de todo el
módulo**, no solo de la vista.

Mitigaciones:
- Entregar módulos **pequeños y con pocas vistas**.
- Si solo hace falta el campo (por ejemplo para poder escribirlo por RPC), **entregarlo sin
  vista** y añadirla después.
- Probar la instalación y **comprobar que el menú o el campo aparecen de verdad** antes de
  darla por buena.

### 2. El zip tiene que llevar separadores `/`

`Compress-Archive` de PowerShell genera rutas con `\` dentro del zip. Odoo **no las reconoce
como estructura de directorios**: el módulo queda "importado" sin registrar ni un fichero y
**sin dar error**.

Hay que generar el zip con separadores `/` explícitos. En el repositorio de la migración
(`MigrarOdoo`) existe `scripts/build-target-module.ts`, que trae un escritor ZIP mínimo hecho
justo por este motivo y sirve de referencia.

## Comprobar el resultado de una instalación

```bash
python ... search ir.module.module '[["name","=","mi_modulo"]]' name,state,latest_version
python ... count ir.model.data '[["module","=","mi_modulo"]]'
```

Si el estado es `installed` pero `ir.model.data` no tiene registros, se ha dado el fallo
silencioso del zip.

## El otro proyecto

La migración 15→19 vive en `E:\apps\AI\MigrarOdoo`, con su propio skill `odoo-ops`: specs
S1–S16, `id_map` en SQLite, cuadre de facturas, delta, extractos bancarios y activos fijos.
Tiene además conectores TypeScript y `scripts/odoo-cli.ts`, que hacen lo mismo que `odoo19.py`
pero contra las dos instancias (la 15 en solo lectura).

Si la pregunta es de migración, es allí. Aquí solo se desarrolla sobre la 19.
