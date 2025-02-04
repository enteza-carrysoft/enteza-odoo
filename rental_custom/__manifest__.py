# Copyright 2019 NaN (http://www.nan-tic.com) - Àngel Àlvarez
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Rental Custom",
    "version": "18.0.1.0.1",
    "category": "Product",
    "summary": "This module rental custom",
    "website": "",
    "author": "Fco Jose Carrion, Daniel Dominguez - Xtendoo (https://xtendoo.es)",
    "maintainers": [],
    "license": "AGPL-3",
    "depends": [
        'sale_renting',
    ],
    "data": [
        'views/sale_order_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'rental_custom/static/src/js/custom_qty_extension.js',
        ],
    },
    "installable": True,
    "auto_install": False,
    "application": False,
}
