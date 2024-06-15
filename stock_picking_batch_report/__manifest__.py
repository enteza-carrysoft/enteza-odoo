# stock_picking_batch_report/__manifest__.py

{
    'name': 'Stock Picking Batch Report',
    'version': '1.0',
    'category': 'Inventory',
    'summary': 'Custom report for Stock Picking Batch with aggregated product quantities',
    'author': 'Tu Nombre',
    'depends': ['stock'],
    'data': [
        'reports/stock_picking_batch_report.xml',
        'views/stock_picking_batch_report_templates.xml',
    ],
    'installable': True,
    'application': False,
}

