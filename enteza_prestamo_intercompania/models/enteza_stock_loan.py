from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

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
    # Origen y destino son seleccionables, no deducidos de la compañía. Hoy hay un almacén
    # por sociedad (Sevilla / Jerez) y se podrían deducir, pero el cliente ha confirmado
    # (2026-08-01, `[PENDIENTE-1]`) que habrá más: modelarlo ahora evita rehacer el flujo
    # entero cuando lleguen. El dominio los ata a su compañía para que no se crucen.
    warehouse_src_id = fields.Many2one(
        'stock.warehouse', string='Almacén de origen', index=True,
        domain="[('company_id', '=', company_id)]",
    )
    warehouse_dest_id = fields.Many2one(
        'stock.warehouse', string='Almacén de destino',
        domain="[('company_id', '=', company_dest_id)]",
    )

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

    # ⚠️ `_sql_constraints` **ya no se soporta en Odoo 19**: `add_to_registry()` avisa por log
    # («Model attribute '_sql_constraints' is no longer supported») y **no crea la
    # restricción**. El fallo es silencioso: el módulo instala igual y la comprobación
    # simplemente no existe. La forma de la 19 es `models.Constraint`, como en
    # `sale.order._date_order_conditional_required`.
    _companias_distintas = models.Constraint(
        'CHECK (company_id != company_dest_id)',
        'Un préstamo tiene que ser entre dos compañías distintas.',
    )

    qty_total = fields.Float(
        string='Unidades comprometidas', compute='_compute_qty_total',
        digits='Product Unit of Measure',
        help='Suma de lo que este préstamo compromete hoy en la compañía prestamista.',
    )
    traslado_retrasado = fields.Boolean(
        string='Traslado retrasado', compute='_compute_traslado_retrasado',
        help='Reservado, con la fecha de traslado ya pasada y sin aprobar: el evento se '
             'acerca y el material no se ha movido.',
    )

    @api.depends('line_ids')
    def _compute_amount_total(self):
        # El préstamo no se valora en la versión base (D4). Se calcula a 0 y se deja el
        # campo definido para que activar la valoración más adelante no exija migrar datos.
        for prestamo in self:
            prestamo.amount_total = 0.0

    @api.depends('line_ids.qty_reserved', 'line_ids.qty_approved', 'state')
    def _compute_qty_total(self):
        for prestamo in self:
            prestamo.qty_total = sum(
                linea._qty_comprometida() for linea in prestamo.line_ids
            )

    @api.depends('state', 'date_transfer')
    def _compute_traslado_retrasado(self):
        # No almacenado: depende de la fecha de hoy, y un campo almacenado que envejece
        # solo sería mentira hasta que algo lo recalculara. La vista de control lo filtra
        # por dominio (§7.6), que no necesita que esté en la tabla.
        hoy = fields.Date.context_today(self)
        for prestamo in self:
            prestamo.traslado_retrasado = bool(
                prestamo.state == 'reserved'
                and prestamo.date_transfer
                and prestamo.date_transfer < hoy
            )

    # ------------------------------------------------------------------
    # Parámetros (PRP §8)
    # ------------------------------------------------------------------

    @api.model
    def _parametro(self, clave, defecto):
        """Lee un parámetro de `ir.config_parameter` con valor por defecto.

        Se lee siempre así y nunca se cachea en el código: los valores de `data/` existen
        para que el cliente pueda cambiarlos, y borrar el registro no debe romper nada.
        """
        valor = self.env['ir.config_parameter'].sudo().get_param(
            'enteza_prestamo.%s' % clave,
        )
        try:
            return int(valor)
        except (TypeError, ValueError):
            return defecto

    # ------------------------------------------------------------------
    # Numeración
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                # `sudo()`: la secuencia no tiene compañía y un usuario de la receptora
                # tiene que poder numerar un préstamo cuya compañía dueña es la otra.
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code(
                    'enteza.stock.loan',
                ) or 'Nuevo'
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Ciclo de vida (PRP §6.4)
    # ------------------------------------------------------------------

    def action_reservar(self):
        """`draft` → `reserved`: compromete el material en la prestamista.

        A partir de aquí el préstamo pesa en la disponibilidad de la compañía que presta
        (`_prestado_a_terceros`), aunque no se haya movido nada físicamente.
        """
        for prestamo in self:
            prestamo._comprobar_estado('draft')
            prestamo._comprobar_completo()
            prestamo._revalidar_disponibilidad()
            for linea in prestamo.line_ids:
                if not linea.qty_reserved:
                    linea.qty_reserved = linea.qty_proposed
            prestamo.write({
                'state': 'reserved',
                # 🔴 Marca de tiempo de la reserva. Es lo que decide quién comprometió el
                # material primero cuando las dos compañías lo necesitan a la vez
                # (`[PENDIENTE-9]`, resuelto el 2026-08-01: vence quien reserva antes).
                # Por eso NO se toca al modificar el préstamo después: perder este dato es
                # perder el criterio de prioridad.
                'date_reserved': fields.Datetime.now(),
                'date_transfer': prestamo.date_transfer or prestamo._fecha_traslado(),
            })
        return True

    def action_aprobar(self):
        """`reserved` → `approved`: un responsable autoriza el traslado físico (D2)."""
        for prestamo in self:
            prestamo._comprobar_estado('reserved')
            prestamo._comprobar_responsable()
            # Se revalida aunque venga de `reserved` y el material «ya estuviera
            # comprometido»: si aquí falta stock, no es un contratiempo sino un fallo del
            # cálculo de reservas, y el PRP §7.3 pide que se vea, no que se tape.
            prestamo._revalidar_disponibilidad()
            for linea in prestamo.line_ids:
                if not linea.qty_approved:
                    linea.qty_approved = linea.qty_reserved
            prestamo.state = 'approved'
        return True

    def action_cancelar(self):
        """Libera la reserva. No se puede cancelar lo que ya está cerrado."""
        for prestamo in self:
            prestamo._comprobar_responsable()
            if prestamo.state == 'returned':
                raise UserError(_(
                    'El préstamo %s ya está devuelto y cerrado: no se puede cancelar.',
                    prestamo.name,
                ))
            if prestamo.state in ('in_transit', 'lent', 'partially_returned'):
                # El material ya salió del almacén. Cancelar aquí dejaría existencias
                # descuadradas en las dos compañías: la salida hay que deshacerla con un
                # movimiento en sentido contrario, por el circuito de devolución (§12.11).
                raise UserError(_(
                    'El préstamo %s ya se ha trasladado físicamente. Hay que devolver el '
                    'material por el circuito de devolución, no cancelar el documento.',
                    prestamo.name,
                ))
            prestamo.state = 'cancelled'
        return True

    def action_volver_borrador(self):
        """Vuelve a `draft` liberando la reserva.

        Solo desde `reserved` o `cancelled`: en cuanto hay albaranes (`approved`) volver
        atrás dejaría documentos huérfanos.
        """
        for prestamo in self:
            prestamo._comprobar_responsable()
            prestamo._comprobar_estado('reserved', 'cancelled')
            prestamo.write({'state': 'draft', 'date_reserved': False})
        return True

    # ------------------------------------------------------------------
    # Comprobaciones
    # ------------------------------------------------------------------

    def _comprobar_estado(self, *estados):
        self.ensure_one()
        if self.state not in estados:
            raise UserError(_(
                'El préstamo %(nombre)s está en estado «%(estado)s» y esta acción no '
                'se puede hacer desde ahí.',
                nombre=self.name,
                estado=dict(ESTADOS).get(self.state, self.state),
            ))

    def _comprobar_responsable(self):
        self.ensure_one()
        if not self.env.user.has_group(
            'enteza_prestamo_intercompania.group_prestamo_responsable'
        ):
            raise UserError(_(
                'Solo un responsable de préstamos puede hacer esto. Nada sale de un '
                'almacén sin que lo autorice una persona.'
            ))

    def _comprobar_completo(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('El préstamo %s no tiene ninguna línea.', self.name))
        if not self.warehouse_src_id or not self.warehouse_dest_id:
            raise UserError(_(
                'Hay que indicar el almacén de origen y el de destino antes de reservar.'
            ))
        if self.warehouse_src_id.company_id != self.company_id \
                or self.warehouse_dest_id.company_id != self.company_dest_id:
            raise UserError(_(
                'Cada almacén tiene que ser de su compañía: el de origen de la '
                'prestamista y el de destino de la receptora.'
            ))

    def _revalidar_disponibilidad(self):
        """Comprueba que la prestamista puede realmente prestar lo que dice este préstamo.

        Se excluye a sí mismo del cálculo (`ignorar_prestamos`): si no, un préstamo ya
        reservado competiría contra su propia reserva y nunca se podría aprobar.
        """
        self.ensure_one()
        # 🔴 `sudo()` y `with_company()` de la PRESTAMISTA, no de quien ejecuta.
        #
        # Quien reserva un préstamo suele ser alguien de la compañía RECEPTORA —es su pedido
        # el que no se puede servir— y esa persona no tiene acceso a los quants de la otra
        # sociedad. Sin esto el cálculo le daría cero disponible y la reserva fallaría
        # siempre con un «no hay libre» falso, que además es de los que se tarda en
        # diagnosticar porque el mismo préstamo sí se reserva bien desde la otra compañía.
        #
        # `with_company` importa además porque `preparation_time` es company_dependent: el
        # padding que vale es el de quien presta.
        motor = self.env['enteza.disponibilidad'].sudo().with_company(self.company_id)

        # Se agrupa por intervalo porque la disponibilidad es una pregunta temporal: dos
        # líneas del mismo producto para fechas distintas no compiten entre sí, y sumarlas
        # daría un déficit inventado.
        por_intervalo = defaultdict(lambda: defaultdict(float))
        for linea in self.line_ids:
            por_intervalo[(linea.date_from, linea.date_to)][linea.product_id] += \
                linea._qty_comprometida() or linea.qty_proposed

        faltas = []
        for (desde, hasta), necesidades in por_intervalo.items():
            # Los registros van con el mismo entorno que el motor: si se le pasan recordsets
            # del usuario, el `sudo()` de arriba no sirve de nada porque cada `producto` se
            # lee con el suyo.
            productos = motor.env['product.product'].browse(
                [p.id for p in necesidades]
            )
            almacen_origen = motor.env['stock.warehouse'].browse(self.warehouse_src_id.id)
            cantidades = {p.id: qty for p, qty in necesidades.items()}
            # Se delega en `deficit()` en vez de comparar aquí: es quien fija con qué
            # precisión se comparan las cantidades. Repetir la comparación con otro
            # criterio haría que el módulo pudiera decir «no falta nada» en un sitio y
            # «falta» en el otro para el mismo caso.
            deficits = motor.deficit(
                productos, almacen_origen, desde, hasta, cantidades,
                ignorar_prestamos=self,
            )
            for producto in productos:
                falta = deficits.get(producto.id)
                if not falta:
                    continue
                necesaria = cantidades[producto.id]
                faltas.append(_(
                    '· %(producto)s: se piden %(pide)s y solo hay %(hay)s libres '
                    'entre el %(desde)s y el %(hasta)s',
                    producto=producto.display_name,
                    pide=necesaria, hay=necesaria - falta, desde=desde, hasta=hasta,
                ))

        if faltas:
            raise UserError(_(
                'El almacén %(almacen)s no tiene libre todo lo que este préstamo '
                'compromete:\n\n%(detalle)s',
                almacen=self.warehouse_src_id.display_name,
                detalle='\n'.join(faltas),
            ))

    def _fecha_traslado(self):
        """Fecha del traslado de ida = inicio del préstamo − días de antelación.

        Los días son un parámetro único para todas las rutas (`[PENDIENTE-3]`, decidido el
        2026-08-01). Si algún día dependen del par de almacenes, este es el sitio donde
        cambiarlo: nadie más calcula esta fecha.
        """
        self.ensure_one()
        if not self.line_ids:
            return False
        inicio = min(self.line_ids.mapped('date_from'))
        dias = self._parametro('dias_antelacion_traslado', 3)
        return fields.Date.to_date(inicio) - timedelta(days=dias)

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
