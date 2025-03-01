# stock_missing_units/__manifest__.py
{
    'name': 'Stock Missing Units',
    'version': '18.0.1.0.0',
    'summary': 'Manage missing units in stock pickings',
    'description': """
        This module adds functionality to manage missing units in stock pickings.
    """,
    'author': 'Tu Nombre',
    'depends': ['stock'],
    'data': [
        'views/stock_picking_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
