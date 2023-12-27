# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) Sitaram Solutions (<https://sitaramsolutions.in/>).
#
#    For Module Support : info@sitaramsolutions.in  or Skype : contact.hiren1188
#
##############################################################################

from odoo import http
from odoo.http import request, content_disposition

try:
    import base64
except ImportError:
    _logger.debug('Cannot `import base64`.')


class Download_xls(http.Controller):
    @http.route('/web/binary/export/<int:attachment_id>', type='http', auth="public")
    def download_document(self, attachment_id, **kw):
        report_attchment_id = request.env['ir.attachment'].search([('id','=',attachment_id)])
        filename = report_attchment_id.name
        filecontent = base64.b64decode(report_attchment_id.datas)

        return request.make_response(filecontent,
            [('Content-Type', 'application/octet-stream'),
            ('Content-Disposition', content_disposition(filename))])

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: