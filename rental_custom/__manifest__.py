{
    'name': 'Crear Orden de Venta desde Albarán',
    'version': '18.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Permite crear órdenes de venta a partir de albaranes',
    'author': 'Tu Nombre',
    'license': 'AGPL-3',
    'depends': [
        'sale_management',
        'stock',
        # Añade aquí 'sale_rental' si es necesario para tu caso
    ],
    'data': [
        'security/ir.model.access.csv',
#        'wizard/wizard_create_sale_view.xml',
        'views/stock_picking_view.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
