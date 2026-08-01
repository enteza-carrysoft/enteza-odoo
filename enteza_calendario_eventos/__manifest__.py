{
    'name': 'Enteza - Calendario de eventos de alquiler',
    'version': '19.0.1.2.0',
    'category': 'Sales/Rental',
    'summary': 'Calendario de pedidos de alquiler pivotado en la fecha del evento',
    'description': """
Calendario de eventos de alquiler
=================================

El calendario nativo de alquiler pivota sobre `rental_start_date`, que es el día en que el
material SALE del almacén — normalmente la víspera del evento. El negocio necesita ver el
día del EVENTO (`event_date`).

Este módulo añade un calendario propio pivotado en `event_date`, con el lugar de entrega
(`partner_shipping_id`) en la ventana flotante. **No sustituye al calendario nativo**:
conviven, porque responden a preguntas distintas ("qué sale hoy del almacén" frente a
"qué eventos hay el sábado").
""",
    'author': 'Enteza',
    'license': 'OPL-1',
    # `rental_custom` es quien aporta `event_date` en sale.order (verificado por RPC en
    # enteza26: ir.model.fields id 11505, modules='rental_custom'). Sin esta dependencia el
    # orden de carga no está garantizado y la vista falla al validar en la instalación.
    'depends': ['sale_renting', 'rental_custom'],
    'data': [
        'views/sale_order_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
