# enteza_portal_pedidos

Portal de pedidos de alquiler: el cliente, con sus credenciales del portal, monta su propia
solicitud de material para un evento en una rejilla tipo hoja de cálculo (pensada para
pedidos de 80-100 líneas), con filtros por categoría y por las dimensiones de búsqueda que el
propio negocio configure (marca, modelo, color...), semáforo de disponibilidad orientativo y
control de cajas cerradas.

Diseño completo, con el porqué de cada decisión: `PRP-PORTAL-PEDIDOS-CLIENTE.md` en la raíz
del repositorio. Este README es solo el resumen operativo.

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
`rental_custom` (aporta `event_date`, imprescindible para confirmar un alquiler en esta
instancia).

## Antes de que esto sirva de algo: prerequisitos de datos (PRP §12)

Instalar el módulo **no basta**. Sin estos tres pasos, la pantalla del cliente sale casi
vacía o con el semáforo mintiendo:

1. **Dar acceso al portal** a los clientes que vayan a usarlo (asistente nativo del
   contacto) y marcarles `enteza_portal_pedidos_ok` (pestaña «Portal de pedidos» de su
   ficha). A fecha del diseño, **0 usuarios de portal** en `enteza26`.
2. **Cargar las dimensiones de búsqueda**: Inventario → Configuración → Dimensiones de
   búsqueda → crear Marca/Modelo/Color/... con sus valores, marcados
   `visible_to_customers`, y asignarlos a los ~1.025 artículos alquilables desde
   Inventario → Configuración → Datos para el portal de clientes (o edición en masa /
   importación CSV). Sin esto, el único desplegable con contenido es «Categoría».
3. **Cargar los packagings** (cajas) que correspondan: crear las `uom.uom` de caja
   (`relative_uom_id` = unidad base, `relative_factor` = unidades por caja) y asignarlas en
   «Packagings» desde la misma pantalla de datos del portal. Sin packaging, un artículo se
   pide por unidades sueltas y no se le aplica ninguna restricción de múltiplo.

**El semáforo de disponibilidad arranca desactivado** (`res.company.enteza_portal_semaforo
= False`) a propósito: con el inventario a medio cargar, pintaría casi todo en rojo. Se
enciende en Ajustes → Ventas → Alquiler cuando el almacén esté cargado de verdad.

## Estado de verificación

- **Modelos, controladores y lógica de negocio (Python)**: validados por sintaxis, no
  ejecutados -este hosting no da acceso a `odoo-bin --test-enable`-. Los tests de
  `tests/` documentan el comportamiento esperado.
- **Vistas XML**: pasar `validar_vistas.py` antes de cada despliegue. Los `xpath` que
  reutilizan anclajes ya verificados en producción en este mismo repositorio
  (`enteza_prestamo_intercompania`) están señalados en los comentarios de cada fichero de
  vista; el resto (formulario de `sale.order`, ficha de `res.partner`) usa anclajes
  extremadamente estables (`//sheet`, `//header`, `//notebook`,
  `//field[@name='order_line']`, `//field[@name='state'][@widget='statusbar']`) pero **no
  se ha podido confirmar contra `enteza26` por RPC en esta sesión**.
- **Frontend OWL**: sigue el patrón documentado en
  `.claude/skills/odoo19-dev/references/owl-acciones-cliente.md` (componente público,
  `web.assets_frontend`, `public_components`). El paso del `orderId` al componente se hizo
  deliberadamente por un `<script type="application/json">` propio en vez del mecanismo de
  `props` de `<owl-component>`, cuyo contrato de serialización exacto no se pudo verificar
  contra esta instancia (ver comentario en `views/portal_templates.xml`). Un error de JS
  deja la pantalla en blanco sin nada en el log del servidor: la primera prueba real tras
  desplegar necesita la consola del navegador (F12) a mano.
- **La precarga de disponibilidad por scroll** (PRP §6.2) se implementó como una precarga
  de las primeras ~150 filas visibles tras cada cambio de filtro/fechas, no como un
  `IntersectionObserver` por fila -verificarlo en vivo habría hecho falta una instancia de
  pruebas que no hay-. Cubre el caso normal; si el catálogo filtrado supera con mucho esa
  cifra, las filas más allá no tienen semáforo hasta que se filtra más o se teclea su
  cantidad.

## Desplegar

```bash
python .claude/skills/odoo19-dev/scripts/validar_modulo.py enteza_portal_pedidos
python .claude/skills/odoo19-dev/scripts/validar_vistas.py enteza_portal_pedidos
```

`git push` a la rama `19.0` → `git pull` de Xtendoo → Aplicaciones → Actualizar lista de
aplicaciones → Instalar. Comprobar el `state` por RPC (que aparezca en la lista no significa
que esté instalado) y `Ctrl+F5` en el navegador para los assets nuevos.

```bash
python .claude/skills/odoo19-dev/scripts/odoo19.py search ir.module.module \
    '[["name","=","enteza_portal_pedidos"]]' name,state,latest_version
```

**`enteza26` es producción.** Confirmar con el usuario antes de cualquier escritura de
datos.
