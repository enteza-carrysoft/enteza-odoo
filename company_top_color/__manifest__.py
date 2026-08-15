{
    "name": "Company Top Color",
    "version": "19.0.2.0.0",
    "summary": "Identifica la compañía activa con una franja de color en la parte superior",
    "category": "Productivity",
    "author": "Enteza",
    "license": "LGPL-3",
    # Sin modelos ni vistas propias: el color se lee del campo nativo `res.company.color`,
    # que ya trae su selector en el formulario estándar de la compañía.
    "depends": ["web"],
    "assets": {
        "web.assets_backend": [
            "company_top_color/static/src/js/company_top_color_service.js",
            "company_top_color/static/src/scss/company_top_color.scss",
        ],
    },
    "installable": True,
    "application": False,
}
