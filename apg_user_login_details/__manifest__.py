# -*- coding: utf-8 -*-

{
    'name': 'User Login Details',
    'version': '19.0.0.0',
    'category': 'Extra Tools',
    'summary': 'This module provides real-time visibility into which users have logged into a newly created or '
               'cloned database. It helps administrators track login activity for better security, transparency,'
               ' and audit readiness across multiple environments.',
    'description': """This module provides real-time visibility into which users have logged into a newly created
     or cloned database. It helps administrators track login activity for better security, transparency, 
     and audit readiness across multiple environments.""",
    'author': 'Apagen Solutions Pvt Ltd',
    'company': 'Apagen Solutions Pvt Ltd',
    'maintainer': 'Apagen Solutions Pvt Ltd',
    'website': "https://www.apagen.com",
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/login_detail_views.xml'
    ],
    'images': ['static/description/banner.jpg'],
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
