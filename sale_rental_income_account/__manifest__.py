{
    "name": "Cuentas e impuestos específicos para alquiler",
    "summary": (
        "Cuenta de ingresos e impuestos propios para las líneas de alquiler, "
        "con herencia desde la categoría del producto"
    ),
    "version": "19.0.2.0.0",
    "category": "Sales/Rental",
    "author": "Ayuntamiento de Mairena del Alcor",
    "license": "LGPL-3",
    "depends": [
        "account",
        "sale_management",
        "sale_renting",
    ],
    "data": [
        "views/product_category_views.xml",
        "views/product_template_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
