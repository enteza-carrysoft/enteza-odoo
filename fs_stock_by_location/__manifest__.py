# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) Fidobe Solutions LLC.
#
#    For Module Support : crp@fidobe.com
#
##############################################################################
{
    "name": "Product Stock By Location Report",
    "version": "15.0.1.0",
    "summary": "Product Stock By Location Report",
    "description": """Product Stock By Location Report""",
    "depends": ["base", "web", "stock"],
    "category": "Inventory",
    "author": "Fidobe Solutions LLC",
    "website": "https://fidobe.com",
    "data": [
        "security/ir.model.access.csv",
        "views/stock_summary_view.xml",
        "wizard/generate_stock_summary_view.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "fs_stock_by_location/static/src/js/stock_summary_list_controller.js",
            "fs_stock_by_location/static/src/js/stock_summary_list.js",
        ],
        "web.assets_qweb": [
            "fs_stock_by_location/static/src/xml/**/*",
        ],
    },
    "external_dependencies": {},
    "license": "LGPL-3",
    "installable": True,
    "auto_install": False,
    "images": ["static/description/banner.gif"],
    "price": 0,
    "currency": "EUR",
}
