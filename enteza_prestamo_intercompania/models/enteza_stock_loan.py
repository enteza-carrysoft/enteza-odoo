from odoo import api, fields, models

# Estados en los que el préstamo COMPROMETE material en la compañía prestamista, es decir,
# los que alimentan `prestado_a_terceros` en el cálculo de disponibilidad.
#
# 🔴 Corrección deliberada respecto al PRP §5.1, que además incluía `in_transit`, `lent` y
# `partially_returned`. En esos estados la salida del almacén YA está validada: el material
# ha salido de las ubicaciones internas de la prestamista y su `parque` ya ha bajado por el
# movimiento de stock real. Contarlo también como comprometido lo restaría dos veces y
# dejaría a la prestamista con disponibilidad falsamente baja, bloqueando ventas legítimas.
#
# En `reserved` no hay nada físico y en `approved` los albaranes existen pero no están
# validados: en ambos el material sigue en casa y hay que reservarlo lógicamente.
ESTADOS_COMPROMETEN = ('reserved', 'approved')

ESTADOS = [
    ('draft', 'Borrador'),
    ('reserved', 'Reservado'),
    ('approved', 'Aprobado'),
    ('in_transit', 'En tránsito'),
    ('lent', 'Prestado'),
    ('partially_returned', 'Devuelto parcialmente'),
    ('returned', 'Devuelto'),
    ('cancelled', 'Cancelado'),
]


class EntezaStockLoan(models.Model):
    _name = 'enteza.stock.loan'
    _description = 'Préstamo de material entre compañías'
    _order = 'date_transfer desc, id desc'

    name = fields.Char(
        string='Referencia', required=True, copy=False, readonly=True, default='Nuevo',
    )

    # `company_id` es la compañía que PRESTA y dueña del documento; `company_dest_id` la que
    # recibe. La regla de registro contempla las dos (ver security/prestamo_security.xml).
    company_id = fields.Many2one(
        'res.company', string='Compañía prestamista', required=True, index=True,
        default=lambda self: self.env.company,
    )
    company_dest_id = fields.Many2one(
        'res.company', string='Compañía receptora', required=True, index=True,
    )
    warehouse_src_id = fields.Many2one('stock.warehouse', string='Almacén de origen')
    warehouse_dest_id = fields.Many2one('stock.warehouse', string='Almacén de destino')

    date_transfer = fields.Date(string='Fecha de traslado')
    date_expected_return = fields.Date(string='Fecha prevista de devolución')
    date_reserved = fields.Datetime(
        string='Reservado el', readonly=True, copy=False,
        help='Momento en que se reservó en firme. Determina quién comprometió el material '
             'primero cuando las dos compañías lo necesitan a la vez.',
    )

    state = fields.Selection(
        ESTADOS, string='Estado', default='draft', required=True, index=True, copy=False,
    )
    origin = fields.Selection(
        [('confirmation', 'Confirmación de pedido'), ('batch', 'Análisis por lotes')],
        string='Origen', default='batch',
    )

    line_ids = fields.One2many(
        'enteza.stock.loan.line', 'loan_id', string='Líneas', copy=True,
    )
    origin_order_ids = fields.Many2many(
        'sale.order', string='Pedidos de origen',
        help='Pedidos de alquiler que motivaron el préstamo.',
    )

    picking_out_id = fields.Many2one(
        'stock.picking', string='Albarán de salida', copy=False, readonly=True,
    )
    picking_in_id = fields.Many2one(
        'stock.picking', string='Albarán de entrada', copy=False, readonly=True,
    )

    notes = fields.Html(string='Notas')

    # Campos reservados para la facturación entre compañías (PRP D4/§9). No se usan en la
    # versión base; existen para no tener que migrar el modelo si la asesoría fiscal decide
    # que el préstamo genera documento.
    move_id = fields.Many2one(
        'account.move', string='Documento entre compañías', copy=False, readonly=True,
        help='Sin uso en la versión base. Ver README, punto de enganche para facturación.',
    )
    amount_total = fields.Monetary(
        string='Importe total', compute='_compute_amount_total', currency_field='currency_id',
    )
    currency_id = fields.Many2one(related='company_id.currency_id', readonly=True)

    _sql_constraints = [
        (
            'companias_distintas',
            'CHECK (company_id != company_dest_id)',
            'Un préstamo tiene que ser entre dos compañías distintas.',
        ),
    ]

    @api.depends('line_ids')
    def _compute_amount_total(self):
        # El préstamo no se valora en la versión base (D4). Se calcula a 0 y se deja el
        # campo definido para que activar la valoración más adelante no exija migrar datos.
        for prestamo in self:
            prestamo.amount_total = 0.0

    # ------------------------------------------------------------------
    # Puntos de enganche para la facturación (PRP §9)
    # ------------------------------------------------------------------

    def _post_loan_hook(self):
        """Se llama tras validar la entrada del traslado de ida (estado -> lent).

        Punto de extensión para generar el documento entre compañías que decida la
        asesoría fiscal. En la versión base no hace nada.

        La vía prevista es instalar `sale_purchase_stock_inter_company_rules` (disponible
        en la instancia, sin instalar) y engancharlo aquí, NO reescribir este módulo.
        """
        return

    def _post_return_hook(self, lineas_devueltas):
        """Ídem tras cada devolución, total o parcial."""
        return
