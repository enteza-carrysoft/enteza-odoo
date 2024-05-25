# __manifest__.py
{
    'name': 'Stock Missing Units',
    'version': '15.0.1.0.0',
    'summary': 'Manage missing units in stock pickings via wizard',
    'description': """
        This module adds functionality to manage missing units in stock pickings via a wizard.
    """,
    'author': 'Francisco Jose Carrion',
    'depends': ['stock'],
    'data': [
        'views/stock_picking_views.xml',
        'views/stock_picking_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
}

