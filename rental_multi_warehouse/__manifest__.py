# -*- coding: utf-8 -*-
{
    'name': 'Alquiler Multi-Almacén',
    'version': '19.0.1.0.0',
    'category': 'Sales/Rental',
    'summary': 'Reserva automática multi-almacén con traslados programados para alquileres',
    'description': """
Alquiler Multi-Almacén
======================
Extiende el módulo de alquiler de Odoo Enterprise (sale_renting) para:

* Reserva de stock distribuida en múltiples almacenes con orden de prioridad
* Detección automática de déficit en el almacén preferente
* Asignación en cascada del stock desde almacenes secundarios
* Creación automática de traslados inter-almacén programados
* Widget de disponibilidad agregada con desglose por almacén
* Gestión de devoluciones con retorno a almacén de origen
* Escalable a N almacenes sin modificar código
    """,
    'author': 'Diputación de Sevilla',
    'license': 'LGPL-3',
    'depends': [
        'sale_renting',
        'stock',
        'sale_stock',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_config_parameter_data.xml',
        'data/ir_cron_data.xml',
        'views/rental_warehouse_priority_views.xml',
        'views/res_config_settings_views.xml',
        'views/sale_order_views.xml',
        'wizard/rental_availability_wizard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'rental_multi_warehouse/static/src/js/rental_multi_wh_widget.js',
            'rental_multi_warehouse/static/src/xml/rental_multi_wh_widget.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
