
{
    "name": "Rental Check Availability Lines",
    "version": "15.0.1.0.0",
    "category": "Sale order",
    "author": "Salvador Gonzalez,Manuel Calero,Abraham Carrasco, Xtendoo",
    "license": "LGPL-3",
    "application": True,
    "depends": [
        "rental_base",
        "rental_pricelist",
        "rental_check_availability",
        "stock",
    ],
    "data": [
        "wizards/sale_view.xml",
        "wizards/sale_order_line_concurrent_view.xml",
        "security/ir.model.access.csv",
    ],
    "installable": True,
}

