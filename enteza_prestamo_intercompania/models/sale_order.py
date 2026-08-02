"""Aviso de déficit en la cabecera del pedido (PRP §10.3).

Por qué además del widget
-------------------------
El widget de la línea solo se lee **pinchando su icono**, uno por uno. En un pedido de treinta
líneas eso no sirve: el comercial no va a ir picando iconos para descubrir si alguna no se
puede servir. El aviso de cabecera resume todas las líneas con déficit y está siempre a la
vista sin interrumpir a nadie (decisión del cliente, 2026-08-02).

El icono de la línea se pone rojo con el mismo dato, así que desde el aviso se localiza de un
vistazo qué línea es.
"""

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.tools import formatLang


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    enteza_aviso_deficit = fields.Html(
        string='Aviso de material', compute='_compute_enteza_aviso_deficit',
        help='Resumen de las líneas que este almacén no puede servir en las fechas del '
             'alquiler, y de quién puede prestar lo que falta.',
    )

    @api.depends(
        'order_line.enteza_falta',
        'order_line.enteza_prestable_otra',
        'order_line.enteza_origen_prestamo',
    )
    def _compute_enteza_aviso_deficit(self):
        # No añade consultas: reaprovecha lo que ya calculan las líneas para el widget.
        for pedido in self:
            lineas = pedido.order_line.filtered(lambda linea: linea.enteza_falta > 0)
            if not lineas:
                pedido.enteza_aviso_deficit = False
                continue
            detalle = Markup().join(linea._enteza_detalle_aviso() for linea in lineas)
            pedido.enteza_aviso_deficit = Markup(
                '<strong>%s</strong><ul class="mb-0 mt-1">%s</ul>'
            ) % (_('Falta material para servir este pedido'), detalle)
