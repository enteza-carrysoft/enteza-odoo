{
    "name": "Company Top Color",
    "version": "19.0.1.0.0",
    "summary": "Identifies the active company with a thin colored strip",
    "category": "Productivity",
    "author": "Custom",
    "license": "LGPL-3",
    "depends": ["web", "base"],
    "data": [
        "views/res_company_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "company_top_color/static/src/js/company_top_color_service.js",
            "company_top_color/static/src/scss/company_top_color.scss",
        ],
    },
    "installable": True,
    "application": False,
}
