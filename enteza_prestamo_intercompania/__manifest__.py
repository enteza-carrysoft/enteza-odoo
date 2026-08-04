{
    'name': 'Enteza - Préstamo de material entre compañías',
    'version': '19.0.10.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Préstamo de material de alquiler entre las compañías del grupo',
    'description': """
Préstamo de material entre compañías del grupo
==============================================

Detecta déficits de material de alquiler en una compañía, comprueba si otra del grupo tiene
unidades libres en esas fechas y gestiona el traslado de ida y vuelta.

- Al montar el presupuesto, el widget de disponibilidad avisa de lo que falta y de quién
  puede prestarlo.
- Al confirmar, un diálogo propone el préstamo y solo reserva si el comercial acepta.
- Un préstamo es un viaje: las necesidades de la misma ruta y fecha se acumulan en un solo
  documento y un solo par de albaranes, programado para el día de la semana que cada
  compañía fija en Ajustes → Ventas → Alquiler.
- El traslado físico lo autoriza siempre una persona.
- Al volver el material, calcula cuánto conviene devolver y cuánto dejar donde está.
- Un cron nocturno recoge lo que se escapa del camino de la confirmación.

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
    #
    # `sale` explícito desde la `19.0.9.0.0`: la vista del buscador de producto hereda
    # `sale.view_order_form` directamente. Ya llegaba transitivo por `sale_renting`/
    # `sale_stock`, pero una vista que referencia su xml_id lo deja explícito.
    'depends': ['stock', 'sale', 'sale_renting', 'sale_stock', 'sale_stock_renting'],
    'data': [
        'security/prestamo_security.xml',
        'security/ir.model.access.csv',
        'data/prestamo_data.xml',
        'views/enteza_stock_loan_views.xml',
        'views/enteza_stock_deficit_views.xml',
        'views/sale_order_product_search_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/enteza_prestamo_confirm_views.xml',
        'wizard/enteza_prestamo_devolucion_views.xml',
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
