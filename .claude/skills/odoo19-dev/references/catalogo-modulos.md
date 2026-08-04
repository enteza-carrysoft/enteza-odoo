# Catálogo de módulos del repositorio

Estado verificado contra `enteza26` el **2026-08-01**, y los tres módulos propios de Enteza
reverificados el **2026-08-04**. Para refrescarlo:

```bash
python .claude/skills/odoo19-dev/scripts/odoo19.py search ir.module.module \
    '[["state","=","installed"]]' name,state --limit 300
```

Qué significa cada estado:

- **installed** — activo en producción.
- **uninstalled** — Odoo lo ve y podría instalarse, pero no está.
- **uninstallable** — Odoo **no puede** instalarlo. Casi siempre código de Odoo 15 heredado
  que no carga en la 19, o dependencias que no existen. **Tratar como muerto** salvo que
  alguien lo porte.

## 🔴 Léelo antes de desarrollar nada de alquiler o stock

Estos son los que solapan con desarrollos nuevos. Aquí es donde se duplica trabajo.

| Módulo | Estado | Qué hace y por qué importa |
|---|---|---|
| `rental_custom` | **installed** | Módulo del cliente. Aporta **`event_date`** en `sale.order` y `sale.order.line`, y una `get_total_availability` propia. Cualquier módulo que use `event_date` **debe depender de él** |
| `rental_multi_warehouse` | uninstalled | ⚠️ **853 líneas + widget OWL + asistente + cron.** Reserva automática multi-almacén con traslados programados: motor de disponibilidad propio, prioridad de almacenes, asignaciones, traslados de ida y vuelta, cron de avisos. **Resuelve casi lo mismo que `enteza_prestamo_intercompania`**, pero entre almacenes de una misma compañía y **sin aprobación humana**. No instalar los dos a la vez |
| `sale_stock_renting_extension` | uninstalled | **Sobrescribe `_compute_qty_at_date`** para añadir cantidad global disponible y mostrarla en el widget. Si se instala, cualquier código que replique ese método deja de dar la misma cifra que la ficha del producto |
| `sale_rental_income_account` | **installed** | Cuenta de ingresos específica para alquiler |
| `bi_warehouse_product_availability_in_so` | uninstalled | Disponibilidad por almacén en el pedido de venta |
| `eg_warehouse_restriction` | uninstalled | Restricción de almacenes por usuario |
| `enteza_calendario_eventos` | **installed** (`19.0.1.2.0`) | Vista calendario nativa pivotada en `event_date`, con el nombre del cliente como etiqueta |
| `enteza_panel_eventos` | **installed** (`19.0.4.0.0`; hay `19.0.5.0.0` en el repo sin desplegar) | Panel OWL de tres bloques: calendario del mes, material del día (columna «Prestados», solo Bienes/alquilables) y pedidos del día. **Depende de** `enteza_prestamo_intercompania` desde su `19.0.4.0.0` |
| `enteza_prestamo_intercompania` | **installed** (`19.0.10.0.2`; hay `19.0.10.0.3` en el repo sin desplegar) | Préstamo de material entre Vimaple y Stileum: las cinco fases del PRP desplegadas — motor de disponibilidad, documento con ciclo de vida, widget de aviso + diálogo de confirmación, albaranes vía tránsito, devolución inteligente, casos límite. Día de traslado configurable por compañía en Ajustes → Ventas → Alquiler |

`enteza_calendario_eventos` y `enteza_panel_eventos` **conviven sin problema**: uno es una
vista calendario nativa y el otro una pantalla propia, no comparten código. `enteza_panel_eventos`
y `enteza_prestamo_intercompania` sí están enlazados: el primero depende del segundo desde su
`19.0.4.0.0` (lee `enteza.stock.loan.line` para la columna «Prestados»), así que no se puede
desinstalar `enteza_prestamo_intercompania` sin desinstalar también `enteza_panel_eventos`.

### Muertos, pero engañan por el nombre

Son de Odoo 15 y están `uninstallable`. Aparecen en búsquedas y hacen pensar que la
funcionalidad existe:

`rental_check_availability_lines` · `sale_order_line_multi_warehouse` · `sale_order_warehouse`
· `stock_missing_units` · `fs_stock_by_location` · `stock_split_picking_by_category`

## Resto del catálogo

### Instalados

| Módulo | Qué hace |
|---|---|
| `no_publisher_warranty_contract` | Quita el aviso de garantía del editor |
| `rental_custom` | Ver arriba |
| `sale_rental_income_account` | Ver arriba |

### Desinstalados (Odoo ve, no está activo)

`account_asset_depreciate` (amortización de activos) · `apg_user_login_details` (registro de
accesos) · `app_common` y `app_odoo_customize` (utilidades de personalización) ·
`eg_shopify_integration_lite` · `rental_portal_change_request` (cambios desde el portal) ·
`stock_picking_batch_report` · más los de alquiler/stock de la tabla de arriba.

### Uninstallable (heredados de la 15, no cargan)

`accounting_pdf_reports` · `auto_database_backup` · `calendar_count` · `eg_ecommerce_base` ·
`import_sale_order` · `om_account_bank_statement_import` · `sale_intervention_quote` ·
`sale_order_discount_all` · `sale_order_line_product_image` · `sales_report_product_image` ·
`sr_inventory_fns_analysis_report` · `sttl_report_lines` · `visuena_document_format` · más los
de la lista de "muertos que engañan".

## Reglas de convivencia

1. **Un solo motor de disponibilidad instalado a la vez.** `rental_multi_warehouse`,
   `sale_stock_renting_extension` y `enteza_prestamo_intercompania` traen cada uno el suyo.
   Conviviendo se reparten el mismo stock sin saber unos de otros y las cifras dejan de
   cuadrar, con un diagnóstico penoso.
2. **Antes de escribir, buscar.** `grep -rn "lo_que_busco" --include=*.py .` sobre el
   repositorio, antes de crear un módulo nuevo.
3. **Un `uninstallable` no es un hueco funcional.** Puede ser una funcionalidad que el cliente
   tenía en la 15 y perdió al pasar a la 19. Si alguien la echa en falta, la pregunta es si se
   porta ese módulo o se hace de nuevo — no darlo por inexistente.
