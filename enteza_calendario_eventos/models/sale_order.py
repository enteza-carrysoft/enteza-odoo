from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    event_calendar_label = fields.Char(
        string='Etiqueta del calendario de eventos',
        compute='_compute_event_calendar_label',
        help='Texto que se muestra en cada evento del calendario de eventos de alquiler. '
             'No se guarda en base de datos: se calcula al vuelo.',
    )

    @api.depends('name', 'partner_id.display_name', 'partner_shipping_id.display_name')
    def _compute_event_calendar_label(self):
        """Cliente y, si es distinto, lugar de entrega.

        El calendario nativo etiqueta cada evento con el `display_name` del registro, que en
        `sale.order` es el número de pedido. El cliente lo quiere por nombre de cliente.

        No se puede apuntar `create_name_field` directamente a `partner_id`: el título se usa
        tal cual, sin procesar (`calendar_model.js`, `normalizeRecord`), y un many2one llega
        al cliente web como `[id, nombre]`. Saldría el array entero. De ahí este Char.

        Se compara por `display_name` y no por id a propósito: lo que hay que evitar es ver el
        mismo texto dos veces, y dos contactos distintos pueden mostrarse igual. Hoy en
        `enteza26` los 1.153 pedidos de alquiler tienen el mismo contacto en los dos campos,
        así que en la práctica se verá solo el cliente hasta que empiecen a informar
        direcciones de entrega propias.
        """
        for order in self:
            cliente = order.partner_id.display_name or ''
            entrega = order.partner_shipping_id.display_name or ''
            if entrega and entrega != cliente:
                order.event_calendar_label = '%s · %s' % (cliente, entrega)
            else:
                # Sin cliente (presupuesto recién creado) queda el número de pedido, que es
                # lo que mostraba antes: mejor eso que un evento sin etiqueta.
                order.event_calendar_label = cliente or order.name
