{
    # Module information
    'name': 'Report Lines',
    'version': '15.0.1.0',
    'author': 'Silver Touch Technologies Limited',
    'website': 'https://www.silvertouch.com',
    'license': 'LGPL-3',
    'support': 'service@silvertouch.com',
    'category': 'Analytic',
    'summary': 'This app provide shortcut of the website Report lines like SO Line, PO Line, Invoice Lines and Vendor Bill Lines.',
    'price': 00,
    'currency': 'EUR',
    "depends": [
        'product', 
        'base', 
        'sale', 
        'account', 
        'purchase', ], #'purchase_handloom_sttl'
    'data': [
        'security/ir.model.access.csv',
        'views/purchase_report_lines_views.xml',
        'views/invoice_lines.xml',
        'views/vendors_lines.xml',  
        'views/sale_report_lines_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'images': ['static/description/banner.png'],
}
