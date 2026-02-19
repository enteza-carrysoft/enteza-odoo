# -*- coding: utf-8 -*-
{
    'name': 'Rental Portal Change Request',
    'version': '19.0.1.0.0',
    'category': 'Rental',
    'summary': 'Private rental portal with change request and review workflow',
    'description': """
        Rental Portal Change Request for Odoo 19 Enterprise
        =====================================================

        This module provides a private portal for rental customers to request
        changes to confirmed orders through a structured workflow with commercial
        approval.

        Key Features:
        * Private rental portal listing customer orders
        * Change request system with approval workflow
        * Edit order lines (add/update/remove products)
        * Quick add by SKU
        * Catalog search with pagination
        * Concurrent editing protection
        * Automatic picking recreation on approval
        * Complete audit trail

        Technical:
        * OWL components for reactive UI
        * JSON-RPC API endpoints
        * Atomic server-side methods
        * Optimistic locking with concurrency control
        * PostgreSQL pg_trgm for fast search
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'license': 'OPL-1',
    'depends': [
        'base',
        'sale_management',
        'sale_renting',
        'portal',
        'mail',
        'web',
    ],
    'data': [
        # Security
        'security/rental_change_request_security.xml',
        'security/ir.model.access.csv',
        'security/rental_portal_security.xml',

        # Data
        'data/sequence_data.xml',
        'data/mail_template_data.xml',

        # Views
        'views/rental_change_request_views.xml',
        'views/sale_order_views.xml',
        'views/rental_change_request_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'rental_portal_change_request/static/src/scss/rental_portal.scss',
            'rental_portal_change_request/static/src/js/rental_portal_owl_bundle.js',
        ],
    },
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': True,
}
