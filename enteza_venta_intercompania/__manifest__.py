{
    'name': 'Enteza - Venta intercompañía de material perdido',
    'version': '19.0.2.1.0',
    'category': 'Sales/Sales',
    'summary': 'Material cedido entre compañías: al facturar sus faltas al cliente, la '
               'compañía dueña factura esas unidades a coste a la receptora',
    'description': """
Venta intercompañía de material perdido
=======================================

Una compañía del grupo alquila material que es de otra (en Enteza, Stileum alquila el de
Vimaple). Cuando publica una factura de faltas a su cliente final, este módulo crea y publica
en la compañía dueña una factura a la receptora por las mismas unidades, a coste. Con
Inter-Company Transactions activado, esa factura crea la de proveedor en la receptora. Las
rectificativas de faltas se rectifican en espejo.

No depende de albaranes ni de existencias. El alquiler de «Cesión intercompañía» es
opcional: sólo pone el material a 0 € y prepara albaranes espejo. Ver README.
""",
    'author': 'Enteza',
    'license': 'OPL-1',
    'depends': [
        # `sale.order.rental_order_id`, que pone «Facturar las Faltas» y es lo que identifica
        # una factura de faltas.
        'rental_custom',
        # `res.company.rental_loc_id` y los albaranes de alquiler. Arrastra sale_renting,
        # sale_stock, stock y account.
        'sale_stock_renting',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/venta_intercompania_security.xml',
        'views/res_company_views.xml',
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
