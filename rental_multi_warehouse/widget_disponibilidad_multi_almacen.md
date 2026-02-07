# Widget de Disponibilidad Multi-Almacén para Alquileres — Diseño Detallado

## 1. ¿Cómo funciona el widget actual de Odoo 19 Enterprise?

### 1.1 En la línea del pedido de alquiler (sale.order.line)

Odoo 19 Enterprise muestra la disponibilidad de alquiler de la siguiente forma:

- **Campo `forecast_availability`**: En las líneas del pedido de venta (heredado de `sale_stock`), Odoo muestra un indicador visual tipo semáforo junto a la cantidad. Este widget (`QtyAtDateWidget` / `stock_at_date`) consulta:
  - Stock disponible actual (`qty_available`)
  - Previsión a la fecha programada (`virtual_available`)
  - Movimientos de entrada/salida pendientes

- **En alquiler específicamente**: El módulo `sale_renting` extiende este comportamiento calculando la **cantidad no disponible** (`_get_unavailability_date_ranges`). Para un producto en un rango de fechas, busca todos los pedidos de alquiler confirmados que se solapan y calcula cuántas unidades están comprometidas. La diferencia `qty_on_hand - qty_comprometida` es la disponibilidad.

- **Limitación clave**: Todo este cálculo se hace **únicamente contra el `warehouse_id` del pedido de venta**. No consulta otros almacenes.

### 1.2 En el Kanban de productos (Rental app → Products)

Cada tarjeta Kanban muestra `qty_available` (unidades en mano) pero **sin contexto temporal**. Es decir, muestra cuántas hay ahora, no cuántas habrá disponibles para una fecha futura.

### 1.3 En la web (website_sale_renting)

El frontend muestra disponibilidad/no disponibilidad en el calendario de reserva, basado en el mismo cálculo de solapamientos contra un solo almacén.

---

## 2. Diseño propuesto: Widget de disponibilidad multi-almacén

### 2.1 Principio de diseño

> **El usuario ve UNA SOLA cifra de disponibilidad total** (suma de todos los almacenes participantes para el periodo solicitado), pero puede expandir el detalle para ver el desglose por almacén.

Esto responde directamente a tu pregunta: **sí, se usa el mismo concepto de widget, pero mostrando el total agregado**, con la posibilidad de ver el detalle.

### 2.2 Comportamiento en la línea del pedido

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Línea de pedido de alquiler                                                 │
├──────────┬──────────┬───────────┬──────────┬────────────────────────────────┤
│ Producto │ Periodo  │ Cantidad  │ Precio   │ Disponibilidad                 │
├──────────┼──────────┼───────────┼──────────┼────────────────────────────────┤
│ Mesa     │ 15-17    │    100    │  500 €   │ 🟢 120 disponibles            │
│ redonda  │ marzo    │           │          │    ▼ Ver detalle               │
│          │          │           │          │ ┌────────────────────────────┐ │
│          │          │           │          │ │ Almacén Sevilla:    80/120 │ │
│          │          │           │          │ │ Almacén Dos Hnas:   40/50  │ │
│          │          │           │          │ │ ─────────────────────────  │ │
│          │          │           │          │ │ TOTAL disponible:   120    │ │
│          │          │           │          │ └────────────────────────────┘ │
├──────────┼──────────┼───────────┼──────────┼────────────────────────────────┤
│ Silla    │ 15-17    │    200    │  400 €   │ 🟡 180 disponibles            │
│ plegable │ marzo    │           │          │ ⚠ Faltan 20 unidades          │
│          │          │           │          │    ▼ Ver detalle               │
│          │          │           │          │ ┌────────────────────────────┐ │
│          │          │           │          │ │ Almacén Sevilla:   120/150 │ │
│          │          │           │          │ │ Almacén Dos Hnas:   60/80  │ │
│          │          │           │          │ │ ─────────────────────────  │ │
│          │          │           │          │ │ TOTAL disponible:   180    │ │
│          │          │           │          │ │ NECESARIO:          200    │ │
│          │          │           │          │ │ DÉFICIT:             20 ❌ │ │
│          │          │           │          │ └────────────────────────────┘ │
└──────────┴──────────┴───────────┴──────────┴────────────────────────────────┘
```

### 2.3 Semáforo de colores

| Color | Significado |
|-------|-------------|
| 🟢 Verde | El almacén preferente tiene stock suficiente. No se necesita traslado. |
| 🔵 Azul | El almacén preferente + otros almacenes cubren el pedido. Se generará traslado inter-almacén. |
| 🟡 Amarillo | Hay stock sumando todos los almacenes, pero es justo o hay riesgo de conflicto con otros pedidos. |
| 🔴 Rojo | No hay stock suficiente ni sumando todos los almacenes. Déficit real. |

### 2.4 Información que muestra el widget expandido

Para cada almacén de la lista de prioridad:

```
Almacén [nombre]:  [disponible_para_periodo] / [stock_total_actual]
                   ├── Stock actual: X
                   ├── Comprometido en alquileres (solapados): -Y
                   ├── Devoluciones esperadas antes: +Z
                   └── Traslados entrantes programados: +W
```

---

## 3. Escalabilidad: N almacenes

### 3.1 Modelo de configuración escalable

En lugar de "almacén primario + almacén secundario", el diseño usa una **lista ordenada de prioridad de almacenes**:

```python
class RentalWarehousePriority(models.Model):
    _name = 'rental.warehouse.priority'
    _description = 'Prioridad de almacenes para alquiler'
    _order = 'sequence'

    sequence = fields.Integer(default=10)
    warehouse_id = fields.Many2one('stock.warehouse', required=True)
    is_active = fields.Boolean(default=True)
    name = fields.Char(related='warehouse_id.name')
```

### 3.2 Algoritmo de asignación con N almacenes

```python
def _compute_multi_warehouse_availability(self, line):
    """
    Calcula la disponibilidad a través de N almacenes
    priorizados, asignando stock en cascada.
    
    Retorna:
    {
        'total_available': int,
        'assignments': [
            {'warehouse': wh_obj, 'available': int, 'assigned': int},
            ...
        ],
        'deficit': int,
        'status': 'ok' | 'transfer_needed' | 'warning' | 'deficit'
    }
    """
    product = line.product_id
    start = line.start_date
    end = line.return_date
    qty_needed = line.product_uom_qty
    primary_wh = line.order_id.warehouse_id

    # Obtener lista de almacenes por prioridad
    priority_list = self.env['rental.warehouse.priority'].search([
        ('is_active', '=', True)
    ], order='sequence')

    # Reordenar: primero el almacén del pedido, luego el resto
    warehouses = [primary_wh]
    for p in priority_list:
        if p.warehouse_id.id != primary_wh.id:
            warehouses.append(p.warehouse_id)

    assignments = []
    remaining = qty_needed

    for wh in warehouses:
        if remaining <= 0:
            break

        available = self._compute_rental_availability(
            product, wh, start, end
        )
        assigned = min(available, remaining)

        assignments.append({
            'warehouse': wh,
            'available': available,
            'assigned': assigned,
            'is_primary': wh.id == primary_wh.id,
        })

        remaining -= assigned

    total_available = sum(a['available'] for a in assignments)
    needs_transfer = any(
        a['assigned'] > 0 and not a['is_primary'] 
        for a in assignments
    )

    if remaining > 0:
        status = 'deficit'
    elif needs_transfer:
        status = 'transfer_needed'
    else:
        status = 'ok'

    return {
        'total_available': total_available,
        'qty_needed': qty_needed,
        'assignments': assignments,
        'deficit': max(remaining, 0),
        'status': status,
    }
```

### 3.3 Creación de traslados desde N almacenes

Cuando se necesita material de varios almacenes secundarios:

```python
def _create_transfers_from_assignments(self, line, assignments):
    """
    Crea traslados desde cada almacén secundario que contribuye.
    Todos los traslados se programan para el martes anterior
    (o día configurado) a la fecha de inicio del alquiler.
    """
    primary_wh = line.order_id.warehouse_id
    transfer_date = self._get_transfer_date(line.start_date.date())
    pickings = self.env['stock.picking']

    for assignment in assignments:
        if assignment['is_primary'] or assignment['assigned'] <= 0:
            continue

        picking = self._create_inter_warehouse_transfer(
            line=line,
            source_wh=assignment['warehouse'],
            dest_wh=primary_wh,
            qty=assignment['assigned'],
            scheduled_date=transfer_date,
        )
        pickings |= picking

    return pickings
```

### 3.4 Ejemplo con 3 almacenes

```
Pedido: 200 sillas para el sábado 15 de marzo
Almacén preferente: Sevilla

Prioridad  │ Almacén          │ Disponible │ Asignado │ Traslado
───────────┼──────────────────┼────────────┼──────────┼──────────
    1      │ Sevilla (pref.)  │    120     │   120    │   No
    2      │ Dos Hermanas     │     50     │    50    │   Sí → martes 11/03
    3      │ Alcalá           │     40     │    30    │   Sí → martes 11/03
───────────┼──────────────────┼────────────┼──────────┼──────────
           │ TOTAL            │    210     │   200    │
           │ Sobrante         │            │    10    │
```

---

## 4. Implementación del widget OWL (frontend)

### 4.1 Componente OWL para Odoo 19

Odoo 19 usa el framework OWL 2 para los componentes de interfaz. El widget se implementa como extensión del `QtyAtDateWidget` existente:

```javascript
/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { QtyAtDateWidget } from "@sale_stock/widgets/qty_at_date_widget";
import { useService } from "@web/core/utils/hooks";

patch(QtyAtDateWidget.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.state.multiWarehouseData = null;
        this.state.showDetail = false;
    },

    get isRentalLine() {
        return this.props.record.data.is_rental;
    },

    get statusColor() {
        const data = this.state.multiWarehouseData;
        if (!data) return '';
        switch (data.status) {
            case 'ok': return 'text-success';           // 🟢
            case 'transfer_needed': return 'text-info';  // 🔵
            case 'warning': return 'text-warning';       // 🟡
            case 'deficit': return 'text-danger';        // 🔴
            default: return '';
        }
    },

    get statusIcon() {
        const data = this.state.multiWarehouseData;
        if (!data) return 'fa-circle-o';
        switch (data.status) {
            case 'ok': return 'fa-check-circle';
            case 'transfer_needed': return 'fa-truck';
            case 'warning': return 'fa-exclamation-triangle';
            case 'deficit': return 'fa-times-circle';
            default: return 'fa-circle-o';
        }
    },

    async onWillStart() {
        await super.onWillStart();
        if (this.isRentalLine) {
            await this._loadMultiWarehouseAvailability();
        }
    },

    async _loadMultiWarehouseAvailability() {
        const record = this.props.record.data;
        if (!record.product_id || !record.start_date || !record.return_date) {
            return;
        }
        this.state.multiWarehouseData = await this.orm.call(
            'sale.order.line',
            'get_multi_warehouse_availability',
            [[record.id]],
        );
    },

    toggleDetail() {
        this.state.showDetail = !this.state.showDetail;
    },
});
```

### 4.2 Template OWL

```xml
<t t-name="rental_multi_warehouse.QtyAtDateWidget" t-inherit="sale_stock.QtyAtDateWidget">
    <xpath expr="//div[hasclass('o_qty_at_date')]" position="after">
        <div t-if="isRentalLine and state.multiWarehouseData" 
             class="o_rental_multi_wh_availability mt-1">
            
            <!-- Indicador principal -->
            <div class="d-flex align-items-center gap-1 cursor-pointer"
                 t-on-click="toggleDetail">
                <i t-attf-class="fa #{statusIcon} #{statusColor}"/>
                <span t-attf-class="#{statusColor} fw-bold">
                    <t t-esc="state.multiWarehouseData.total_available"/> disponibles
                </span>
                <i t-attf-class="fa fa-caret-#{state.showDetail ? 'up' : 'down'} ms-1"/>
            </div>

            <!-- Aviso de traslado necesario -->
            <div t-if="state.multiWarehouseData.status === 'transfer_needed'"
                 class="text-info small">
                <i class="fa fa-truck"/> Requiere traslado inter-almacén
            </div>

            <!-- Aviso de déficit -->
            <div t-if="state.multiWarehouseData.status === 'deficit'"
                 class="text-danger small fw-bold">
                <i class="fa fa-exclamation-circle"/> 
                Faltan <t t-esc="state.multiWarehouseData.deficit"/> unidades
            </div>

            <!-- Detalle expandible por almacén -->
            <div t-if="state.showDetail" class="o_rental_wh_detail border rounded p-2 mt-1">
                <table class="table table-sm table-borderless mb-0">
                    <thead>
                        <tr class="small text-muted">
                            <th>Almacén</th>
                            <th class="text-end">Disponible</th>
                            <th class="text-end">Asignado</th>
                            <th class="text-center">Traslado</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr t-foreach="state.multiWarehouseData.assignments" 
                            t-as="a" t-key="a.warehouse_id">
                            <td>
                                <i t-if="a.is_primary" 
                                   class="fa fa-star text-warning me-1" 
                                   title="Almacén preferente"/>
                                <t t-esc="a.warehouse_name"/>
                            </td>
                            <td class="text-end">
                                <t t-esc="a.available"/>
                            </td>
                            <td class="text-end fw-bold">
                                <t t-esc="a.assigned"/>
                            </td>
                            <td class="text-center">
                                <i t-if="!a.is_primary and a.assigned > 0" 
                                   class="fa fa-truck text-info"
                                   t-att-title="'Traslado programado: ' + a.transfer_date"/>
                                <span t-if="a.is_primary" class="text-muted">—</span>
                            </td>
                        </tr>
                    </tbody>
                    <tfoot class="border-top">
                        <tr class="fw-bold">
                            <td>TOTAL</td>
                            <td class="text-end">
                                <t t-esc="state.multiWarehouseData.total_available"/>
                            </td>
                            <td class="text-end">
                                <t t-esc="state.multiWarehouseData.qty_needed"/>
                            </td>
                            <td></td>
                        </tr>
                    </tfoot>
                </table>
            </div>
        </div>
    </xpath>
</t>
```

---

## 5. Backend: Endpoint para el widget

```python
class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # Campos computados para la vista (no stored, se calculan al vuelo)
    rental_availability_status = fields.Selection([
        ('ok', 'Disponible'),
        ('transfer_needed', 'Necesita traslado'),
        ('warning', 'Stock justo'),
        ('deficit', 'Sin stock suficiente'),
    ], compute='_compute_rental_availability_status')

    rental_total_available = fields.Float(
        compute='_compute_rental_availability_status'
    )

    @api.depends('product_id', 'start_date', 'return_date', 
                 'product_uom_qty', 'order_id.warehouse_id')
    def _compute_rental_availability_status(self):
        for line in self:
            if not line.is_rental or not line.start_date:
                line.rental_availability_status = False
                line.rental_total_available = 0
                continue
            
            data = line._compute_multi_warehouse_availability(line)
            line.rental_availability_status = data['status']
            line.rental_total_available = data['total_available']

    def get_multi_warehouse_availability(self):
        """
        Endpoint llamado por el widget OWL.
        Retorna datos completos de disponibilidad para renderizar.
        """
        self.ensure_one()
        data = self._compute_multi_warehouse_availability(self)
        
        # Serializar para JSON
        result = {
            'total_available': data['total_available'],
            'qty_needed': data['qty_needed'],
            'deficit': data['deficit'],
            'status': data['status'],
            'assignments': [],
        }
        
        for a in data['assignments']:
            transfer_date = None
            if not a['is_primary'] and a['assigned'] > 0:
                transfer_date = str(self._get_transfer_date(
                    self.start_date.date()
                ))
            
            result['assignments'].append({
                'warehouse_id': a['warehouse'].id,
                'warehouse_name': a['warehouse'].name,
                'available': a['available'],
                'assigned': a['assigned'],
                'is_primary': a['is_primary'],
                'transfer_date': transfer_date,
            })
        
        return result
```

---

## 6. Recálculo automático

### 6.1 ¿Cuándo se recalcula la disponibilidad?

El widget se recalcula automáticamente cuando cambian:

| Evento | Trigger |
|--------|---------|
| Se cambia el producto en la línea | `@api.onchange('product_id')` |
| Se cambian las fechas del alquiler | `@api.onchange('start_date', 'return_date')` |
| Se cambia la cantidad | `@api.onchange('product_uom_qty')` |
| Se cambia el almacén del pedido | `@api.onchange('order_id.warehouse_id')` |
| Se confirma/cancela otro pedido | Cron de invalidación (cada 15 min) o signal |

### 6.2 Onchange para recálculo inmediato

```python
@api.onchange('product_id', 'start_date', 'return_date', 
              'product_uom_qty')
def _onchange_rental_availability(self):
    """Recalcula disponibilidad al cambiar datos relevantes."""
    if self.is_rental and self.product_id and self.start_date:
        # El campo computado se recalcula automáticamente
        # El widget OWL detectará el cambio y se actualizará
        pass
```

---

## 7. Resumen de respuestas a tus preguntas

### ¿Se usa el mismo widget actual?
**Sí**, se extiende el widget `QtyAtDateWidget` existente de `sale_stock` mediante un patch OWL. El usuario no nota un cambio de paradigma; simplemente ve más información.

### ¿Muestra el total de todos los almacenes?
**Sí**, la cifra principal que ve el usuario es el **total disponible sumando todos los almacenes** de la lista de prioridad. El detalle por almacén está disponible con un clic (expandir).

### ¿Funcionará si se incorpora algún almacén más?
**Sí, absolutamente.** El diseño está basado en una **lista ordenada de prioridad** (`rental.warehouse.priority`) donde se pueden añadir N almacenes con una secuencia de prioridad. El algoritmo de asignación itera por la lista en orden, asignando stock en cascada:

1. Primero intenta cubrir todo desde el almacén del pedido
2. Si no alcanza, busca en el 2º almacén de la lista
3. Si sigue sin alcanzar, busca en el 3º, 4º... etc.
4. Cada almacén secundario que contribuya genera su propio traslado

**Añadir un nuevo almacén** = crear un registro en `rental.warehouse.priority` con la secuencia deseada. Sin tocar código.
