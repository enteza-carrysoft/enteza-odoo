"""Páginas HTML del portal de pedidos (PRP §8.1).

🔴 Ninguna ruta lleva `website=True`: este módulo no instala `website` ni `website_sale`
(PRP §2.1), solo `portal`, así que ese parámetro no se puede usar — sin él la ruta
sencillamente no se registraría.
"""
from odoo import _
from odoo.exceptions import MissingError
from odoo.http import request, route
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager

from .common import enteza_get_solicitud, enteza_partner_portal_ok


class PortalPedidos(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        """Añade el contador de solicitudes a la portada de `/my` (PRP §8.1).

        No se condiciona a que `'solicitud_count'` esté en `counters`: el mecanismo nativo
        para saber qué contadores hace falta calcular no está verificado contra `enteza26`
        en este módulo, y un `search_count` de más en `/my` es gratis comparado con arriesgar
        que la tarjeta salga sin número por una condición que nunca se cumple.
        """
        values = super()._prepare_home_portal_values(counters)
        partner = enteza_partner_portal_ok()
        values['enteza_portal_pedidos_ok'] = bool(partner)
        values['solicitud_count'] = (
            request.env['sale.order'].sudo().search_count([
                ('partner_id', '=', partner.id),
                ('enteza_portal_state', '!=', 'none'),
            ]) if partner else 0
        )
        return values

    def _enteza_estados_labels(self):
        """`{código: etiqueta}` de `enteza_portal_state`, para no hacer introspección de
        `_fields` dentro de QWeb: más simple de leer y no depende de qué permite el sandbox.
        """
        return dict(request.env['sale.order']._fields['enteza_portal_state'].selection)

    # ------------------------------------------------------------------
    # Lista (PRP §8.1)
    # ------------------------------------------------------------------

    @route(
        ['/my/solicitudes', '/my/solicitudes/page/<int:page>'],
        type='http', auth='user',
    )
    def portal_my_solicitudes(self, page=1, **kw):
        partner = enteza_partner_portal_ok()
        if not partner:
            return request.redirect('/my')

        SaleOrder = request.env['sale.order'].sudo()
        dominio = [
            ('partner_id', '=', partner.id),
            ('enteza_portal_state', '!=', 'none'),
        ]

        total = SaleOrder.search_count(dominio)
        pager_vals = portal_pager(url='/my/solicitudes', total=total, page=page, step=20)
        solicitudes = SaleOrder.search(
            dominio, order='id desc', limit=20, offset=pager_vals['offset'])

        # Pedidos de alquiler ya confirmados, para «Repetir un pedido anterior» (PRP §9.4).
        pedidos_repetibles = SaleOrder.search([
            ('partner_id', '=', partner.id),
            ('is_rental_order', '=', True),
            ('state', '=', 'sale'),
        ], order='rental_start_date desc', limit=10)

        values = self._prepare_portal_layout_values()
        values.update({
            'page_name': 'solicitudes',
            'solicitudes': solicitudes,
            'pager': pager_vals,
            'pedidos_repetibles': pedidos_repetibles,
            'estados_portal': self._enteza_estados_labels(),
            'default_url': '/my/solicitudes',
        })
        return request.render('enteza_portal_pedidos.portal_my_solicitudes', values)

    # ------------------------------------------------------------------
    # Nueva / editar (PRP §5, §8.1, §9)
    # ------------------------------------------------------------------

    @route('/my/solicitud/nueva', type='http', auth='user')
    def portal_solicitud_nueva(self, **kw):
        partner = enteza_partner_portal_ok()
        if not partner:
            return request.redirect('/my')
        # Una sola solicitud en composición por cliente (PRP §5): si ya existe, redirige a
        # la misma en vez de crear otra.
        pedido = request.env['sale.order']._enteza_portal_get_or_create(partner)
        return request.redirect('/my/solicitud/%d' % pedido.id)

    @route('/my/solicitud/<int:order_id>', type='http', auth='user')
    def portal_solicitud(self, order_id, **kw):
        if not enteza_partner_portal_ok():
            return request.redirect('/my')
        order = enteza_get_solicitud(order_id)

        # Fuera de composición, la pantalla editable no aplica: al resumen.
        if order.enteza_portal_state != 'composing':
            return request.redirect('/my/solicitud/%d/resumen' % order.id)

        values = self._prepare_portal_layout_values()
        values.update({
            'page_name': 'solicitud',
            'order': order,
        })
        return request.render('enteza_portal_pedidos.portal_solicitud_grid', values)

    # ------------------------------------------------------------------
    # Resumen + diff de contrapropuesta (PRP §8.1, §11)
    # ------------------------------------------------------------------

    @route('/my/solicitud/<int:order_id>/resumen', type='http', auth='user')
    def portal_solicitud_resumen(self, order_id, **kw):
        if not enteza_partner_portal_ok():
            return request.redirect('/my')
        order = enteza_get_solicitud(order_id)

        values = self._prepare_portal_layout_values()
        values.update({
            'page_name': 'solicitud_resumen',
            'order': order,
            'diff_rows': (
                order._enteza_portal_diff_contrapropuesta()
                if order.enteza_portal_state == 'counter' else []
            ),
            'timeline': order._enteza_portal_timeline(),
            'estados_portal': self._enteza_estados_labels(),
        })
        return request.render('enteza_portal_pedidos.portal_solicitud_resumen', values)

    # ------------------------------------------------------------------
    # Repetir un pedido anterior (PRP §9.4)
    # ------------------------------------------------------------------

    @route(
        '/my/solicitudes/<int:order_id>/repetir',
        type='http', auth='user', methods=['POST'], csrf=True,
    )
    def portal_solicitud_repetir(self, order_id, **kw):
        partner = enteza_partner_portal_ok()
        if not partner:
            return request.redirect('/my')

        origen = request.env['sale.order'].sudo().browse(order_id).exists()
        commercial = partner.commercial_partner_id
        valido = (
            origen
            and origen.partner_id.commercial_partner_id == commercial
            and origen.is_rental_order
            and origen.state == 'sale'
        )
        if not valido:
            raise MissingError(_("Este pedido no existe o no tienes acceso a él."))

        nueva = origen.action_enteza_portal_repetir()
        return request.redirect('/my/solicitud/%d' % nueva.id)
