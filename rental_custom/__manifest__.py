{
    'name': 'Crear Orden de Venta desde Albarán',
    'version': '19.0.1.2.0',
    'category': 'Sales/Sales',
    'summary': 'Permite crear órdenes de venta a partir de albaranes',
    'author': 'Francisco Jose Carrion',
    'license': 'AGPL-3',
    'depends': [
        'sale_management',
        'sale_renting',
        'stock',
    ],
    'data': [
        'security/ir.model.access.csv',
#        'wizard/wizard_create_sale_view.xml',
        'views/sale_order_views.xml',
        'views/stock_picking_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
