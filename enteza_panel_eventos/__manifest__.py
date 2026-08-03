{
    'name': 'Enteza - Panel de eventos del día',
    'version': '19.0.2.0.0',
    'category': 'Sales/Rental',
    'summary': 'Panel con calendario, pedidos del día y material necesario en una sola pantalla',
    'description': """
Panel de eventos del día
========================

Reproduce en Odoo la pantalla de control diario de la aplicación de gestión que Enteza usaba
antes: tres bloques sincronizados en una sola pantalla.

- **Calendario mensual** a la izquierda, con los días coloreados según la carga de trabajo.
- **Material del día** a la derecha: los artículos de todos los pedidos de ese día, agrupados
  por artículo y sumando unidades, con filtro por descripción y dos vistas — *Consumos* (todo)
  y *Sobre venta* (solo el material del que hay comprometido más de lo que hay en el almacén,
  es decir, lo que habría que comprar o subcontratar). Al pinchar un artículo, los pedidos de
  abajo se filtran a los que lo llevan.
- **Pedidos del día** abajo, con cliente, lugar de entrega, fechas de inicio y fin del
  alquiler, estado e importe.

Se puede mirar el día desde tres ángulos, porque un pedido toca tres días distintos: el del
**evento** (`event_date`), el de **salida** del almacén (`rental_start_date`, normalmente la
víspera) y el de **devolución** (`rental_return_date`, normalmente el día siguiente).

Y se puede imprimir el **parte del día**: la hoja de carga para el almacén.

Es independiente de `enteza_calendario_eventos`: aquel añade una vista calendario nativa, éste
es una pantalla propia. Pueden convivir y no comparten código.
""",
    'author': 'Enteza',
    'license': 'OPL-1',
    # `rental_custom` aporta `event_date` en sale.order (ir.model.fields id 11505).
    # `sale_renting` aporta `is_rental_order` y `rental_status`.
    'depends': ['sale_renting', 'rental_custom'],
    'data': [
        'report/parte_dia_templates.xml',
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
