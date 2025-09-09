{
    "name": "Sale Intervention Quote",
    "version": "18.0.1.0.0",
    "summary": "Wizard para presupuestos paramétricos de intervención (desplazamiento, mano de obra, unidad móvil, materiales y consumibles).",
    "author": "Tu Org",
    "license": "LGPL-3",
    "depends": ["sale_management", "product"],
    "data": [
        "security/ir.model.access.csv",
        "views/res_config_settings_views.xml",
        "views/sale_order_views.xml",
        "views/intervention_quote_wizard_views.xml",
    ],
    "application": False,
}
