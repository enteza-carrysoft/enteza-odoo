# -*- coding: utf-8 -*-
{
    "name": "Enteza - Factura agrupada por familias",
    "summary": "Informe de factura agrupado por familia de producto, sin repetir el periodo de alquiler en cada línea",
    "version": "19.0.2.0.0",
    "category": "Accounting",
    "author": "Enteza",
    "license": "OPL-1",
    "depends": ["account", "sale_renting"],
    "data": [
        "views/report_factura_agrupada.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
