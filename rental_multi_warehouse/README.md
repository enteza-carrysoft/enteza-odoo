# Alquiler Multi-Almacén — Módulo Odoo 19 Enterprise

## Instalación

1. Copiar la carpeta `rental_multi_warehouse` al directorio de addons de Odoo
2. Reiniciar el servidor: `odoo -u rental_multi_warehouse`
3. Activar en **Apps** → buscar "Alquiler Multi-Almacén" → Instalar

**Requisitos**: `sale_renting` (Enterprise), `stock`, `sale_stock`

## Configuración inicial

### 1. Prioridad de almacenes
**Alquiler → Configuración → Prioridad de almacenes**

Añadir todos los almacenes que participan en alquileres y ordenarlos arrastrando.
El almacén del pedido siempre se consulta primero; esta lista define el orden de los secundarios.

### 2. Ajustes generales
**Alquiler → Configuración → Ajustes → Multi-Almacén**

- **Día de traslado**: Día de la semana para los traslados (defecto: Martes)
- **Días mínimos de antelación**: Margen de seguridad (defecto: 2 días)
- **Retorno automático**: Crear traslados de vuelta al devolver material (defecto: Sí)

## Uso

### Al crear un pedido de alquiler
Al añadir productos y fechas, la columna **Disponibilidad** muestra:
- 🟢 **Verde**: Stock suficiente en el almacén del pedido
- 🔵 **Azul + camión**: Se necesita traslado desde otro almacén
- 🔴 **Rojo**: No hay stock suficiente en ningún almacén

Clic en el indicador para ver el **desglose por almacén** (stock, comprometido, disponible, asignado, fecha de traslado).

### Al confirmar el pedido
Si se necesitan unidades de almacenes secundarios:
1. Se crean registros de **asignación** (pestaña Multi-Almacén en la línea)
2. Se crean **traslados inter-almacén** automáticamente
3. Los traslados se programan para el día configurado anterior a la entrega

### Botón "Traslados" en el pedido
Muestra todos los traslados inter-almacén (ida y vuelta) vinculados al pedido.

### Al devolver el material
Si está habilitado el retorno automático, al completar la devolución se crean traslados para devolver el material a sus almacenes de origen.

### Consultar disponibilidad
**Alquiler → Informes → Consultar disponibilidad**

Wizard para verificar disponibilidad de cualquier producto en todos los almacenes para un rango de fechas, sin necesidad de crear un pedido.

## Estructura de archivos

```
rental_multi_warehouse/
├── __manifest__.py                    # Manifest del módulo
├── __init__.py
├── models/
│   ├── rental_warehouse_priority.py   # Modelo: lista de prioridad
│   ├── sale_order_line.py             # Motor de disponibilidad + asignaciones
│   ├── sale_order.py                  # Override confirmación + traslados
│   └── res_config_settings.py         # Configuración
├── views/
│   ├── rental_warehouse_priority_views.xml
│   ├── sale_order_views.xml           # Widget + pestaña multi-almacén
│   └── res_config_settings_views.xml
├── wizard/
│   ├── rental_availability_wizard.py  # Consulta de disponibilidad
│   └── rental_availability_wizard_views.xml
├── security/
│   └── ir.model.access.csv
├── data/
│   ├── ir_config_parameter_data.xml   # Parámetros por defecto
│   └── ir_cron_data.xml               # Cron: verificación diaria
└── static/src/
    ├── js/rental_multi_wh_widget.js   # Widget OWL
    └── xml/rental_multi_wh_widget.xml # Template OWL
```

## Flujo temporal (ejemplo)

```
Enero (hoy)         Martes 11/03        Sábado 15/03        Lunes 17/03
    │                    │                    │                    │
Confirmar SO        Traslado B→A         Entrega al           Devolución
Almacén A: 80       20 uds llegan       cliente: 100 uds     80→A, 20→B
Necesita: 100       a Almacén A         salen de A           (retorno auto)
Déficit: 20
→ Asigna 20 de B
```
