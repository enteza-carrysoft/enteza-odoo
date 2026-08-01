{
    'name': 'Enteza - Préstamo de material entre compañías',
    'version': '19.0.1.1.0',
    'category': 'Inventory/Inventory',
    'summary': 'Préstamo de material de alquiler entre las compañías del grupo',
    'description': """
Préstamo de material entre compañías del grupo
==============================================

Detecta déficits de material de alquiler en una compañía, comprueba si la otra tiene
unidades libres en esas fechas y gestiona el traslado de ida y vuelta.

**Fase 1 (actual): motor de cálculo.** Disponibilidad, demanda comprometida y cantidad
prestable. Sin interfaz ni flujo de documentos todavía.

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
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
