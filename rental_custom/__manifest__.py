# Copyright 2019 NaN (http://www.nan-tic.com) - Àngel Àlvarez
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Rental Custom",
    "version": "15.0.1.0.1",
    "category": "Product",
    "summary": "This module rental custom",
    "website": "",
    "author": "Fco Jose Carrion, Daniel Dominguez - Xtendoo (https://xtendoo.es)",
    "maintainers": [],
    "license": "AGPL-3",
    "depends": [
        'sale',
        'sale_rental',
        'rental_base',
        'rental_product_set',
        'sale_product_set',
    ],
    "data": [
        'security/ir.model.access.csv',
        'views/sale_line_views.xml',
        'views/dashboard_rental_views.xml',
        'views/sale_order_views.xml',
        'wizard/wizard_report_stock_views.xml',
        'wizard/product_set_add.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'rental_custom/static/src/js/rental_dashboard.js',
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
