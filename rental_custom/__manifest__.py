# Copyright 2019 NaN (http://www.nan-tic.com) - Àngel Àlvarez
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Rental Custom",
    "version": "15.0.1.0.1",
    "category": "Product",
    "summary": "This module rental custom",
    "website": "",
    "author": "Fco Jose Carrion",
    "maintainers": [],
    "license": "AGPL-3",
    "depends": ["sale",'sale_rental','rental_base'],
    "data": [
        'security/ir.model.access.csv',
        'views/sale_line_views.xml',
        'views/dashboard_rental_views.xml',
        'wizard/wizard_report_stock_views.xml',
        
    ],
    'assets': {
        'web.assets_backend': [
            'rental_custom/static/src/js/rental_dashboard.js',
            #'dashboard_pos/static/src/css/pos_dashboard.css',
            #'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/2.8.0/Chart.bundle.js',
        ],
        'web.assets_qweb': [
            'rental_custom/static/src/xml/rental_dashboard.xml',
        ],
    },
    "demo": [
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
