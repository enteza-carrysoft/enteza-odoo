{
    "name": "Enteza - Descuento en factura",
    "version": "19.0.1.0.0",
    "summary": "Botón para aplicar un descuento a todas las líneas de una factura de cliente",
    "category": "Accounting/Accounting",
    "author": "Enteza",
    "license": "LGPL-3",
    # Calca el wizard nativo "Descuento" de sale.order.discount (addons/sale/wizard), que
    # no tiene equivalente en account.move: aquí se reimplementa solo la variante "aplicar
    # a todas las líneas", que es la que ha pedido el cliente para facturas.
    "depends": ["account"],
    "data": [
        "security/ir.model.access.csv",
        "wizard/account_move_discount_views.xml",
        "views/account_move_views.xml",
    ],
    "installable": True,
    "application": False,
}
