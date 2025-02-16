{
    'name': "Sale Stock Renting Extension",
    'version': '1.0',
    'summary': "Extiende sale_stock_renting para incluir cantidad global disponible y mostrarla en el widget",
    'description': """
        Este módulo extiende el módulo sale_stock_renting para:
          - Calcular y almacenar la cantidad disponible globalmente (entre todos los almacenes)
            en el campo 'virtual_available_total_at_date' de las líneas de pedido.
          - Modificar el widget para mostrar, en la ventana modal, tanto la cantidad disponible
            en el almacén asignado como la cantidad global.
    """,
    'author': "Francisco Jose Carrion",
    'website': "http://www.carrysoft.com",
    'category': 'Sales',
    'depends': ['sale_stock_renting', 'web'],
    'data': [
        'report/rental_schedule_gantt_view.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sale_stock_renting_extension/static/src/widgets/qty_at_date_widget.js',
            'sale_stock_renting_extension/static/src/widgets/qty_at_date_widget.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}

