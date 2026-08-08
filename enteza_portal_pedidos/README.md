# enteza_portal_pedidos

Portal de pedidos de alquiler: el cliente, con sus credenciales del portal, monta su propia
solicitud de material para un evento en una rejilla tipo hoja de cálculo (pensada para
pedidos de 80-100 líneas), con filtros por categoría y por las dimensiones de búsqueda que el
propio negocio configure (marca, modelo, color...), semáforo de disponibilidad orientativo y
control de cajas cerradas.

Diseño completo, con el porqué de cada decisión:
- `PRP-PORTAL-PEDIDOS-CLIENTE.md` — diseño original (2026-08-08).
- `PRP-PORTAL-PEDIDOS-V2-REPARACION.md` — reparación de rendimiento/robustez y diálogo
  cliente-comercial (2026-08-08, versión `19.0.2.0.0`). **Vigente**: donde discrepe con el
  original, manda este.

Este README es solo el resumen operativo.

## Qué NO es

- No es eCommerce: no instala `website` ni `website_sale`. Solo `portal`.
- No hay pago online: el cobro llega por transferencia, fuera de este flujo.
- No es un modelo paralelo: la solicitud **es** un `sale.order` de alquiler en borrador.
- No reimplementa disponibilidad de alquiler: delega en `sale_stock_renting`.
- No es el módulo de cambios sobre pedidos ya confirmados (eso es otro problema, el que
  intentaba resolver `rental_portal_change_request` -que no se instala ni se usa de base
  aquí, ver PRP §3).

## Dependencias

`portal`, `mail`, `sale_management`, `sale_renting`, `sale_stock_renting`, `stock`,
`rental_custom` (aporta `event_date` y `rental_billable_days`, imprescindible para confirmar
un alquiler en esta instancia; desde `19.0.1.10.0` también aporta la disponibilidad del
widget `QtyAtDate` delegada en el motor nativo — ver PRP v2 §D4).

## Decisiones de negocio (PRP v2, 2026-08-08)

Cuatro decisiones que cambian el comportamiento respecto al diseño original:

| # | Decisión |
|---|---|
| D1 | Sin comercial propio en la ficha del cliente, se asigna el de `res.company.enteza_portal_user_id` (Ajustes → Ventas → Alquiler). |
| D2 | El cliente indica solo la **fecha del evento**. Entrega/retirada se derivan (±1 día, 08:00/20:00 hora local) — ajustables a mano con «ajustar» en la interfaz. |
| D3 | El **almacén no se elige desde el portal**: es siempre `res.partner.enteza_portal_warehouse_id`. Sin él, la pantalla no se monta. |
| D4 | La disponibilidad, tanto en el portal como en `rental_custom`, la calcula siempre el motor nativo de `sale_stock_renting`. |

## Antes de que esto sirva de algo: prerequisitos de datos (PRP §12)

Instalar el módulo **no basta**. Sin estos pasos, la pantalla del cliente sale casi vacía,
con el semáforo mintiendo, o ni siquiera se monta:

1. **Dar acceso al portal** a los clientes que vayan a usarlo (asistente nativo del
   contacto), marcarles `enteza_portal_pedidos_ok`, y asignarles su
   **`enteza_portal_warehouse_id`** (pestaña «Portal de pedidos» de su ficha) — 🔴 desde
   D3, sin este campo el cliente no puede montar ninguna solicitud.
2. **Cargar las dimensiones de búsqueda**: Inventario → Configuración → Dimensiones de
   búsqueda → crear Marca/Modelo/Color/... con sus valores, marcados
   `visible_to_customers`, y asignarlos a los ~1.025 artículos alquilables desde
   Inventario → Configuración → Datos para el portal de clientes. Sin esto, el único
   desplegable con contenido es «Categoría» (verificado por RPC el 2026-08-08: 0 facetas
   configuradas en `enteza26`).
3. **Cargar los packagings** (cajas): `uom.uom` de caja (`relative_uom_id` = unidad base,
   `relative_factor` = unidades por caja) en «Packagings». Sin packaging, cualquier
   cantidad es válida (verificado por RPC: 0 productos con caja configurada hoy).
4. **Comercial por defecto** (opcional pero recomendado): Ajustes → Ventas → Alquiler →
   «Comercial por defecto del portal», para los clientes sin comercial propio en su ficha.

**El semáforo de disponibilidad arranca desactivado** (`res.company.enteza_portal_semaforo
= False`) a propósito. Se enciende en Ajustes → Ventas → Alquiler cuando el almacén esté
cargado de verdad.

## Contrato de la API (PRP v2 §F1, §9)

Todas las rutas son `type='jsonrpc', auth='user'`, y ninguna lanza hacia el transporte:
siempre devuelven `{ok: true, ...}` o `{error, error_code}` con HTTP 200 — el decorador
`enteza_json_endpoint` (`controllers/common.py`) envuelve el cuerpo entero de cada una.

| Ruta | Params | Devuelve |
|---|---|---|
| `/enteza_portal/solicitud/catalogo` | `order_id` | catálogo completo |
| `/enteza_portal/solicitud/guardar` | `order_id`, `header?`, `lines?`, `customer_note?` | estado autoritativo: `{order, lines, totals, warnings, box_warnings}` |
| `/enteza_portal/solicitud/disponibilidad` | `order_id`, `items: [{product_id, qty}]` (máx. 50) | `{colors: {product_id: color}}` |
| `/enteza_portal/solicitud/enviar` | `order_id`, `header?`, `lines?`, `customer_note?` | guarda + envía en la misma transacción: `{ok, ref, redirect}` |
| `/enteza_portal/solicitud/cancelar` | `order_id` | `{ok}` |

🔴 **`lines` es el estado COMPLETO del cesto, no un delta.** Toda línea existente cuyo
`product_id` no aparezca en `lines` se borra. Repetir la misma llamada dos veces dos deja el
mismo resultado (idempotente) — es lo que hace segura la reconexión tras un fallo de red o
un doble clic, y sustituye al bloqueo optimista por `write_date` del diseño original (que la
propia maquinaria de alquiler invalidaba sola: crear una línea puede escribir en la cabecera
vía `rental_custom._get_pricelist_price` → `order_id._rental_set_dates()`).

Rutas HTTP del diálogo cliente-comercial (formularios POST clásicos, no JSON):
`/my/solicitud/<id>/mensaje`, `/my/solicitud/<id>/aceptar`, `/my/solicitud/<id>/cambios`.

## Estado de verificación

- **Modelos, controladores y lógica de negocio (Python)**: validados por sintaxis
  (`py_compile` + `validar_modulo.py`), no ejecutados -este hosting no da acceso a
  `odoo-bin --test-enable`-. Los tests de `tests/` documentan el comportamiento esperado.
- **Vistas XML**: pasadas por `validar_vistas.py` sin fallos de esquema (2026-08-08). Los
  `xpath` que reutilizan anclajes ya verificados en producción en este mismo repositorio
  (`enteza_prestamo_intercompania`) están señalados en los comentarios de cada vista; el
  resto usa anclajes extremadamente estables (`//sheet`, `//header`, `//notebook`,
  `//field[@name='order_line']`, `//field[@name='state'][@widget='statusbar']`) pero **no
  se ha podido confirmar contra `enteza26` por RPC en esta sesión**.
- **Frontend OWL**: sintaxis JS comprobada con `node --check` en los ocho ficheros (no
  ejecuta OWL, solo detecta errores de sintaxis puros). Sigue el patrón documentado en
  `.claude/skills/odoo19-dev/references/owl-acciones-cliente.md`. Un error de JS deja la
  pantalla en blanco sin nada en el log del servidor: la primera prueba real tras desplegar
  necesita la consola del navegador (F12) a mano.
- **Disponibilidad de `rental_custom`** (PRP v2 D4): delega en `_get_unavailable_qty` /
  `_get_virtual_unavailable_qty_in_rent` de `sale_stock_renting`, métodos privados de
  Enterprise que no se pueden llamar por RPC. Verificados solo por lectura del código de
  Enterprise 18 (repositorio del cliente) — **no confirmados contra el comportamiento real
  de la 19**, al igual que el resto de este módulo que se apoya en ese motor.
- **Hora de negocio de las fechas derivadas** (D2, 08:00/20:00 locales): la conversión usa
  `pytz` sobre `self.env.user.tz or 'Europe/Madrid'`. No se ha podido probar con un usuario
  de zona horaria distinta contra la instancia real.

## Desplegar

```bash
python .claude/skills/odoo19-dev/scripts/validar_modulo.py enteza_portal_pedidos
python .claude/skills/odoo19-dev/scripts/validar_vistas.py enteza_portal_pedidos
python .claude/skills/odoo19-dev/scripts/validar_modulo.py rental_custom
```

`git push` a la rama `19.0` → `git pull` de Xtendoo → Aplicaciones → Actualizar lista de
aplicaciones → **Actualizar** ambos módulos (`enteza_portal_pedidos` y `rental_custom`,
tocado por D4). Comprobar el `state` por RPC (que aparezca en la lista no significa que esté
instalado) y `Ctrl+F5` en el navegador para los assets nuevos.

```bash
python .claude/skills/odoo19-dev/scripts/odoo19.py search ir.module.module \
    '[["name","in",["enteza_portal_pedidos","rental_custom"]]]' \
    name,state,latest_version,installed_version
```

🔴 Los dos campos están al revés de lo intuitivo: `latest_version` es la **instalada**,
`installed_version` es la del **manifiesto en disco**. No fiarse del aviso verde de
«Actualizado correctamente» sin confirmar por RPC.

**`enteza26` es producción.** Confirmar con el usuario antes de cualquier escritura de
datos.
