{
    'name': 'Enteza - Portal de pedidos de alquiler',
    'version': '19.0.2.0.0',
    'category': 'Sales/Rental',
    'summary': "Solicitudes de alquiler hechas por el cliente desde el portal",
    'description': """
Portal de pedidos de alquiler
==============================

Permite a los clientes de alquiler, con sus credenciales del portal, montar su propia
solicitud de material para un evento: una rejilla densa tipo hoja de cálculo (pensada para
pedidos de 80-100 líneas), con filtros por categoría y por las dimensiones de búsqueda que el
propio negocio configure (marca, modelo, color...), disponibilidad orientativa por semáforo de
color y control de cajas cerradas (múltiplos de unidades por caja).

La solicitud es un `sale.order` de alquiler en borrador: al enviarla, el comercial asignado
recibe un aviso (chatter + actividad) y decide si confirma o contrapropone. El cliente sigue
toda la traza -solicitud, presupuesto, pedido, factura, cobro- con las páginas nativas del
portal de Odoo 19.

No instala `website` ni `website_sale`: usa exclusivamente `portal`. No hay pago online.

Ver `PRP-PORTAL-PEDIDOS-CLIENTE.md` en la raíz del repositorio para el diseño completo.
""",
    'author': 'Enteza',
    'license': 'OPL-1',
    'depends': [
        'portal',
        'mail',
        'sale_management',
        'sale_renting',
        'sale_stock_renting',   # el motor de disponibilidad vive aquí, no en sale_renting
        'stock',
        'rental_custom',        # aporta event_date y rental_billable_days
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/mail_template_data.xml',
        'views/sale_order_views.xml',
        'views/product_facet_views.xml',
        'views/product_template_views.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'views/portal_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'enteza_portal_pedidos/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
