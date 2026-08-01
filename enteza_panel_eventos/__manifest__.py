{
    'name': 'Enteza - Panel de eventos del día',
    'version': '19.0.1.0.0',
    'category': 'Sales/Rental',
    'summary': 'Panel con calendario, pedidos del día y material necesario en una sola pantalla',
    'description': """
Panel de eventos del día
========================

Reproduce en Odoo la pantalla de control diario de la aplicación de gestión que Enteza usaba
antes: tres bloques sincronizados en una sola pantalla.

- **Calendario mensual** a la izquierda, con los días coloreados según la carga de trabajo.
- **Material del día** a la derecha: los artículos de todos los pedidos de ese día, agrupados
  por artículo y sumando unidades.
- **Pedidos del día** abajo, con cliente, lugar de entrega, hora de salida e importe.

Pivota sobre `event_date` (día del evento), no sobre `rental_start_date` (día en que el
material sale del almacén).

Es independiente de `enteza_calendario_eventos`: aquel añade una vista calendario nativa, éste
es una pantalla propia. Pueden convivir y no comparten código.
""",
    'author': 'Enteza',
    'license': 'OPL-1',
    # `rental_custom` aporta `event_date` en sale.order (ir.model.fields id 11505).
    # `sale_renting` aporta `is_rental_order` y `rental_status`.
    'depends': ['sale_renting', 'rental_custom'],
    'data': [
        'views/panel_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'enteza_panel_eventos/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
