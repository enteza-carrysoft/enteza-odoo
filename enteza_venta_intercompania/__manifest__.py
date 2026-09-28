{
    'name': 'Enteza - Venta intercompañía de material perdido',
    'version': '19.0.1.1.0',
    'category': 'Sales/Sales',
    'summary': 'Material cedido entre compañías: al facturar sus faltas al cliente, la '
               'compañía dueña le vende esas unidades a la receptora',
    'description': """
Venta intercompañía de material perdido
=======================================

Una compañía del grupo cede material a otra con un pedido de alquiler marcado como
«Cesión intercompañía». Cuando la receptora publica la factura de faltas a su cliente final,
este módulo crea en la compañía dueña una venta a la receptora por las mismas
unidades, con el precio de su tarifa, su factura en borrador, y las descuenta del alquiler
de cesión.

Ninguna factura se publica sola ni se valida ningún albarán: lo revisa una persona. Ver README.
""",
    'author': 'Enteza',
    'license': 'OPL-1',
    'depends': [
        # «Facturar las Faltas» parcial (`_create_missing_sale_order`), `rental_order_id` y
        # `qty_missing`. Necesita rental_custom 19.0.1.14.0 o posterior.
        'rental_custom',
        # `res.company.rental_loc_id` y los albaranes de alquiler. Arrastra sale_renting,
        # sale_stock, stock y account.
        'sale_stock_renting',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/venta_intercompania_security.xml',
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
