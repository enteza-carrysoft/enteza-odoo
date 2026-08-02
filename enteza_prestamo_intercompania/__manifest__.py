{
    'name': 'Enteza - Préstamo de material entre compañías',
    'version': '19.0.2.3.0',
    'category': 'Inventory/Inventory',
    'summary': 'Préstamo de material de alquiler entre las compañías del grupo',
    'description': """
Préstamo de material entre compañías del grupo
==============================================

Detecta déficits de material de alquiler en una compañía, comprueba si la otra tiene
unidades libres en esas fechas y gestiona el traslado de ida y vuelta.

**Fase 2 en curso.** El motor de cálculo (fase 1) y el documento de préstamo con su ciclo
de vida: numeración, estados, reserva en firme, aprobación e interfaz.

Todavía **no** engancha en la confirmación de pedidos ni genera albaranes: eso llega en las
dos entregas siguientes de esta misma fase.

No factura ni genera asientos contables (ver README, «Punto de enganche para facturación»).
""",
    'author': 'Enteza',
    'license': 'OPL-1',
    # `sale_stock_renting` es imprescindible y el PRP §13 no lo listaba porque el §2.1 no
    # detectó que estuviera instalado: es quien aporta `_get_unavailable_qty`,
    # `_get_virtual_unavailable_qty_in_rent` y `res.company.rental_loc_id`, sobre los que
    # se apoya todo el motor de disponibilidad. Arrastra `stock`, `sale_renting` y
    # `sale_stock`, que se dejan explícitos por legibilidad.
    #
    # Sin `account` a propósito: la facturación va desacoplada (PRP D4). El campo `move_id`
    # apunta a `account.move`, que está garantizado porque `sale` depende de él vía
    # `account_payment`.
    'depends': ['stock', 'sale_renting', 'sale_stock', 'sale_stock_renting'],
    'data': [
        'security/prestamo_security.xml',
        'security/ir.model.access.csv',
        'data/prestamo_data.xml',
        'views/enteza_stock_loan_views.xml',
    ],
    # Extiende el widget nativo de disponibilidad de la línea de pedido (§10.3). Va al mismo
    # bundle que `sale_stock_renting`, y el orden de carga lo da la dependencia: estos
    # ficheros se cargan después de los suyos, que es lo que permite arrastrar sus
    # `fieldDependencies` y encontrar su bloque en la plantilla.
    'assets': {
        'web.assets_backend': [
            'enteza_prestamo_intercompania/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
