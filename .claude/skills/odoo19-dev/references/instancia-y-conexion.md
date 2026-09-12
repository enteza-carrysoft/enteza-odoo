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

### La vía real: es Doodba, no un `git pull` plano (corregido el 2026-09-13)

**El hosting es Doodba.** Lo que hasta ahora se documentaba aquí como "Xtendoo hace `git
pull`" es incompleto y llevó a dar por perdido un fix que en realidad solo estaba a un paso
de aplicarse: en Doodba los addons de este repositorio no se clonan sin más, se traen a
`odoo/custom/src/` a partir de `repos.yaml` mediante **`git-aggregate`**, y ese paso **no se
dispara solo con un `git pull`** al remoto — hace falta invocarlo, con `invoke
git-aggregate`. Medido el 2026-09-13 con `enteza_invoice_discount`: dos commits de fix se
subieron a `origin/19.0`, y por RPC `installed_version` (el manifiesto tal cual está en el
disco del servidor) siguió leyendo la versión vieja durante **dos rondas completas** de
"Actualizar lista de aplicaciones" + Actualizar módulo, porque el árbol que Doodba monta en
el contenedor no se había refrescado. Solo cambió al lanzar `invoke git-aggregate`.

El flujo real es:

1. Commit y push a la rama `19.0`.
2. En el servidor (Xtendoo o quien tenga acceso a ese panel): `invoke git-aggregate` — **no
   basta con que el repo remoto tenga los commits nuevos**, hace falta este paso para que
   Doodba los traiga al árbol que usa el contenedor.
3. En Odoo: Aplicaciones → **Actualizar lista de aplicaciones**, y luego Instalar o Actualizar.

Antes de dar por buena una actualización que no surtió efecto, comprobar primero si el
`invoke git-aggregate` se ha ejecutado de verdad — es la causa más probable, por delante de
cualquier sospecha sobre el código o sobre el botón Actualizar de Odoo.

Cómo distinguirlo por RPC: en `ir.module.module`, el campo **`imported`** vale `False` cuando
Odoo leyó el manifiesto **del filesystem** (llegó por `git pull`) y `True` cuando entró por
`base.import.module`. Es la comprobación que revela por qué vía llegó un módulo.

> Un módulo del repositorio puede aparecer en la lista de aplicaciones **sin estar instalado**:
> `git pull` solo pone los ficheros en el addons path. Y como casi todos llevan
> `application: False`, no salen en Aplicaciones con el filtro por defecto — hay que quitarlo.
> Es fácil creer que un módulo está instalado cuando solo está presente. Verificar siempre el
> `state` por RPC.

Seguir sin acceso a `odoo -u`: **no se pueden ejecutar pruebas** ni forzar actualizaciones
desde CLI. La actualización se pide por la interfaz o por
`ir.module.module.button_immediate_upgrade` por RPC.

### La otra vía: zip por `base.import.module`

Sigue disponible (Aplicaciones → Importar módulo, o por RPC) y es la que se usó en la
migración. Tiene dos trampas medidas en este proyecto, **las dos con fallo silencioso**:

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
python ... search ir.module.module '[["name","=","mi_modulo"]]' name,state,latest_version,imported
python ... count ir.model.data '[["module","=","mi_modulo"]]'
```

Cómo leer el resultado:

| `state` | `ir.model.data` | Qué pasó |
|---|---|---|
| `installed` | con registros | Instalado de verdad |
| `installed` | **vacío** | Fallo silencioso del zip (trampa 2) |
| `uninstalled` | vacío | **No está instalado**: o llegó por `git pull` y nadie pulsó Instalar, o la instalación hizo rollback |

Para saber si un `uninstalled` es "nunca se intentó" o "se intentó y falló", **lanzar la
instalación por RPC**: `button_immediate_install` devuelve el traceback completo, que la
interfaz a veces se traga.

### 🔴 El botón "Actualizar" también puede dar por buena una actualización que no aplicó nada

Medido el 2026-08-04 en `enteza26`, con un campo nuevo en `res.company`
(`enteza_prestamo_intercompania`). El botón dio dos errores reales (una lectura de
`res.company` que rompía por una columna que aún no existía, y un xpath con `@string` como
selector), se arreglaron los dos, y a la **tercera** el usuario pulsó Actualizar, no vio
ningún error... y por RPC la columna **seguía sin existir**, `latest_version` no se había
movido y ninguna vista nueva del módulo estaba en `ir.model.data`. Es decir: la interfaz dio
por buena una actualización que no había llegado a ejecutar `_auto_init()` ni `load_data()`.

**La única forma fiable de saber si de verdad se aplicó es no fiarse del aviso verde y
comprobarlo por RPC** (`latest_version` frente al `version` del manifiesto, o si las vistas
nuevas están en `ir.model.data`, como en la tabla de arriba). Si no se aplicó y la interfaz
no dice por qué, **lanzar la actualización directamente por RPC** resuelve las dos cosas a la
vez — la ejecuta de verdad y, si algo falla, da el traceback completo:

```bash
python ... exec ir.module.module button_immediate_upgrade '[[ID_DEL_MODULO]]' --execute
```

No hace falta pedirle al cliente que reintente el botón una cuarta vez a ciegas: esto es más
rápido y más informativo que cualquier número de clics en la interfaz.

## El otro proyecto

La migración 15→19 vive en `E:\apps\AI\MigrarOdoo`, con su propio skill `odoo-ops`: specs
S1–S16, `id_map` en SQLite, cuadre de facturas, delta, extractos bancarios y activos fijos.
Tiene además conectores TypeScript y `scripts/odoo-cli.ts`, que hacen lo mismo que `odoo19.py`
pero contra las dos instancias (la 15 en solo lectura).

Si la pregunta es de migración, es allí. Aquí solo se desarrolla sobre la 19.
