from collections import defaultdict
from datetime import timedelta

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

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
    return_picking_ids = fields.One2many(
        'stock.picking', 'enteza_loan_id', string='Albaranes de devolución',
        domain=[('enteza_devolucion', '=', True)], readonly=True,
        help='Cada devolución, total o parcial, genera su propio par de albaranes.',
    )
    qty_pendiente_devolver = fields.Float(
        string='Pendiente de devolver', compute='_compute_qty_pendiente_devolver',
        digits='Product Unit of Measure', store=True,
        help='Lo que la receptora todavía no ha devuelto. Es la columna que mira a diario '
             'el responsable de la prestamista (§7.6).',
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
    revision_pendiente = fields.Boolean(
        string='Necesita revisión', copy=False, index=True,
        help='Un pedido que alimentaba este préstamo se ha cancelado o reducido cuando el '
             'material ya había salido del almacén. Hay que decidir qué se hace con él.',
    )
    revision_motivo = fields.Text(string='Motivo de la revisión', copy=False, readonly=True)
    tiene_pendiente_aprobacion = fields.Boolean(
        string='Material pendiente de firmar', compute='_compute_pendiente_aprobacion',
        help='El préstamo ya está aprobado, pero se le ha acumulado material nuevo que '
             'todavía no ha autorizado nadie.',
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

    @api.depends('line_ids.qty_pending')
    def _compute_qty_pendiente_devolver(self):
        for prestamo in self:
            prestamo.qty_pendiente_devolver = sum(prestamo.line_ids.mapped('qty_pending'))

    @api.depends('state', 'line_ids.qty_approved', 'line_ids.qty_reserved')
    def _compute_pendiente_aprobacion(self):
        for prestamo in self:
            prestamo.tiene_pendiente_aprobacion = bool(
                prestamo.state == 'approved'
                and any(not linea.qty_approved for linea in prestamo.line_ids)
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
        """`reserved` → `approved`: un responsable autoriza el traslado físico (D2).

        También se puede volver a pulsar sobre un préstamo **ya aprobado** al que se le ha
        acumulado material nuevo: entonces se firma **solo el incremento** y el préstamo no
        sale de `approved`. Es lo que permite que un viaje siga siendo uno solo cuando
        aparece otro evento para la misma fecha, sin deshacer lo que el responsable ya
        autorizó (decisión del cliente, 2026-08-02).
        """
        for prestamo in self:
            if prestamo.state == 'approved':
                if not prestamo.tiene_pendiente_aprobacion:
                    raise UserError(_(
                        'El préstamo %s ya está aprobado y no se le ha añadido material '
                        'nuevo desde entonces.', prestamo.name,
                    ))
            else:
                prestamo._comprobar_estado('reserved')
            prestamo._comprobar_responsable()
            # Se revalida aunque venga de `reserved` y el material «ya estuviera
            # comprometido»: si aquí falta stock, no es un contratiempo sino un fallo del
            # cálculo de reservas, y el PRP §7.3 pide que se vea, no que se tape.
            prestamo._revalidar_disponibilidad()
            # Solo se rellenan las líneas SIN firmar. Es lo que distingue «material nuevo
            # que nadie ha visto» de «el responsable decidió aprobar menos»: si aquí se
            # igualara `qty_approved` a `qty_reserved` sin mirar, una segunda aprobación
            # desharía silenciosamente el recorte que hizo la primera.
            for linea in prestamo.line_ids:
                if not linea.qty_approved:
                    linea.qty_approved = linea.qty_reserved
            prestamo.state = 'approved'
            # Aquí es donde el préstamo deja de ser papel: se generan los dos albaranes, o
            # se amplían los que ya existan si esta aprobación solo firma material añadido
            # después. Va DESPUÉS de fijar `qty_approved`, que es lo que decide qué se mueve.
            prestamo._sincronizar_albaranes()
        return True

    def incorporar(self, vals_lineas, pedido=None):
        """Acumula material en un préstamo ya abierto, en vez de crear otro (§7.2).

        Varios eventos de la misma fecha que necesiten material de la otra compañía tienen
        que viajar **en el mismo porte**: un préstamo es un viaje, y partirlo en documentos
        sueltos multiplicaría los albaranes sin ninguna razón física.

        El material queda comprometido **en el acto**, aunque el préstamo estuviera aprobado
        y estas líneas todavía no lleven firma: `_qty_comprometida()` devuelve `qty_reserved`
        mientras `qty_approved` esté a cero. Así no hay ni un instante en el que otro
        comercial pueda vender esas unidades. La firma del responsable hace falta para
        **moverlas**, no para reservarlas.
        """
        self.ensure_one()
        if self.state not in ('reserved', 'approved'):
            raise UserError(_(
                'Al préstamo %(nombre)s no se le puede añadir material: está en estado '
                '«%(estado)s». Si ya se ha trasladado, lo que falte tiene que ir en un '
                'préstamo nuevo.',
                nombre=self.name,
                estado=dict(ESTADOS).get(self.state, self.state),
            ))

        lineas = self.env['enteza.stock.loan.line'].create([
            dict(vals, loan_id=self.id) for vals in vals_lineas
        ])
        for linea in lineas:
            if not linea.qty_reserved:
                linea.qty_reserved = linea.qty_proposed
        if pedido:
            self.origin_order_ids = [(4, pedido.id)]

        # Se revalida DESPUÉS de fijar las cantidades, para que la comprobación incluya el
        # material nuevo. Si la prestamista no llega, salta el error y la transacción entera
        # se deshace: no queda ni el préstamo ampliado ni el pedido confirmado.
        self._revalidar_disponibilidad()
        return lineas

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

    @api.model
    def _fecha_traslado_de(self, inicio, compania):
        """Fecha del traslado de ida: el día de la semana fijo de `compania`, antes del evento.

        Hasta la `19.0.10.0.0` era «N días antes» (`[PENDIENTE-3]`, decidido el 2026-08-01,
        un único parámetro para todas las rutas). El cliente ha pedido cambiarlo por un día
        de la semana fijo — con la temporada concentrada en fines de semana, encaja mejor con
        la logística real un «los traslados a Jerez salen los martes» que contar días desde
        cada evento. Se configura por compañía en Ajustes → Ventas → Alquiler
        (`res.company.enteza_dia_traslado_semana`), porque cada prestamista puede tener su
        propio día de reparto.

        `compania` es la PRESTAMISTA (`warehouse_src_id.company_id`), no la que recibe: es
        su almacén el que organiza el viaje de salida.

        Es **siempre anterior** al evento, nunca el mismo día: si la fecha de inicio cae
        justo en el día configurado, el traslado es el de la semana ANTERIOR. Es lo que pidió
        el cliente («antes del día del evento») y además evita el caso raro de un traslado
        programado el mismo día que empieza el alquiler.

        Es `@api.model` porque quien decide si una necesidad nueva cabe en un préstamo ya
        abierto necesita la fecha ANTES de tener el préstamo (§7.2): la agrupación es por
        fecha de traslado exacta, así que calcularla en otro sitio con otra fórmula rompería
        el criterio sin que se note.
        """
        # 🔴 A la zona horaria del usuario antes de quedarse con el día (§12, caso 8). Los
        # `Datetime` de Odoo son UTC, y un alquiler que empieza a las 00:30 del sábado en
        # España está guardado como las 22:30 del viernes: quedarse con la fecha en crudo
        # programaría el traslado contando desde el día equivocado.
        inicio = fields.Datetime.to_datetime(inicio)
        local = fields.Datetime.context_timestamp(self, inicio).date()

        dia_configurado = int(compania.enteza_dia_traslado_semana or '2')
        dias_atras = (local.weekday() - dia_configurado) % 7
        if dias_atras == 0:
            # El evento cae justo en el día configurado: no es «antes», hay que ir a la
            # semana anterior.
            dias_atras = 7
        return local - timedelta(days=dias_atras)

    def _fecha_traslado(self):
        """Fecha de traslado de este préstamo, a partir de la primera línea que empieza."""
        self.ensure_one()
        if not self.line_ids:
            return False
        return self._fecha_traslado_de(min(self.line_ids.mapped('date_from')), self.company_id)

    # ------------------------------------------------------------------
    # Liberar lo que un pedido cancelado o reducido ya no necesita (§7.0.2)
    # ------------------------------------------------------------------

    def _enteza_liberar(self, lineas, cantidad=None, motivo=''):
        """Retira de este préstamo lo que aportaban `lineas`.

        🔴 Es lo que hace viable juntar varios pedidos en un mismo viaje. Sin esto, cancelar
        uno de los eventos dejaba su material comprometido para siempre: la prestamista no
        podía volver a venderlo y, si el préstamo estaba aprobado, **viajaba igualmente**.

        `cantidad` a `None` significa «todo lo de estas líneas» (cancelación). Con un número,
        se retira esa cantidad repartida entre ellas (reducción de pedido).

        Devuelve `True` si se ha podido liberar y `False` si el material ya había salido.
        """
        self.ensure_one()
        if self.state in ('returned', 'cancelled'):
            return False
        if self.state in ('in_transit', 'lent', 'partially_returned'):
            # El material físicamente ya salió del almacén. Deshacerlo desde aquí dejaría las
            # existencias descuadradas en las dos compañías: tiene que volver por el circuito
            # de devolución, y mientras tanto alguien tiene que enterarse (§12, caso 11).
            self._marcar_para_revision(motivo)
            return False

        pendiente = cantidad
        for linea in lineas:
            redondeo = linea.product_uom_id.rounding or 0.01
            actual = linea._qty_comprometida() or linea.qty_proposed
            quitar = actual if pendiente is None else min(pendiente, actual)
            if pendiente is not None:
                pendiente -= quitar
            restante = actual - quitar

            if float_compare(restante, 0.0, precision_rounding=redondeo) <= 0:
                # Los movimientos se cancelan ANTES de borrar la línea: el enlace es
                # `ondelete='set null'`, así que un borrado a secas dejaría un movimiento
                # huérfano que seguiría sacando material del almacén.
                linea._enteza_cancelar_movimientos()
                linea.unlink()
            else:
                valores = {'qty_proposed': restante}
                if linea.qty_reserved:
                    valores['qty_reserved'] = restante
                if linea.qty_approved:
                    valores['qty_approved'] = restante
                linea.write(valores)

            if pendiente is not None and float_compare(
                pendiente, 0.0, precision_rounding=redondeo
            ) <= 0:
                break

        self._anotar(motivo)
        if not self.line_ids:
            self._enteza_cancelar_por_vacio()
        elif self.state == 'approved':
            # Quedan líneas: los albaranes se ajustan a la baja, no se rehacen (§7.0.2).
            self._sincronizar_movimientos()
        return True

    def _enteza_cancelar_por_vacio(self):
        """El préstamo se ha quedado sin material: se cancela con sus albaranes.

        No se pasa por `action_cancelar` a propósito: ese exige el grupo de responsable, y
        aquí no hay ninguna decisión que tomar —el motivo del préstamo ha desaparecido—.
        Exigir una firma para cancelar un viaje que ya no tiene carga solo conseguiría que
        quedaran documentos vivos sin sentido.
        """
        self.ensure_one()
        albaranes = (self.picking_out_id | self.picking_in_id).filtered(
            lambda albaran: albaran.state not in ('done', 'cancel')
        )
        albaranes.sudo().action_cancel()
        self.state = 'cancelled'

    def _marcar_para_revision(self, motivo):
        self.ensure_one()
        self.revision_pendiente = True
        self.revision_motivo = '\n'.join(filter(None, [self.revision_motivo, motivo]))
        self._anotar(motivo)

    def _anotar(self, texto):
        """Deja constancia en las notas. La trazabilidad pesa más que la limpieza aquí."""
        self.ensure_one()
        if not texto:
            return
        sello = fields.Datetime.to_string(fields.Datetime.now())
        self.notes = (self.notes or Markup()) + Markup('<p>%s — %s</p>') % (sello, texto)

    # ------------------------------------------------------------------
    # Traslado de ida: los dos albaranes vía tránsito (PRP §6.1 y §7.4)
    # ------------------------------------------------------------------

    @api.model
    def _ubicacion_transito(self):
        """Ubicación de tránsito compartida entre las dos sociedades.

        🔴 **Odoo 19 ya la trae**: `stock.stock_location_inter_company`, con `usage='transit'`
        y `company_id` vacío, que es exactamente lo que hace falta. Viene **archivada**, y por
        eso una búsqueda normal de ubicaciones de tránsito no la encuentra y parece que no
        existe. El módulo la activa en `data/prestamo_data.xml`.

        Corrige al PRP §6.1 en dos puntos: no hay que crear una ubicación propia —sería un
        duplicado de la que usan los flujos intercompañía del propio Odoo— y su ejemplo
        colgaba de `stock.stock_location_locations_virtual`, que **no existe en la 19**.

        Sin `company_id` vacío la mitad del flujo falla con un error de acceso poco
        descriptivo: es la causa número uno de problemas en este tipo de módulo, así que se
        comprueba y se dice claro en vez de dejar que reviente más adelante.
        """
        transito = self.env.ref(
            'stock.stock_location_inter_company', raise_if_not_found=False,
        )
        if not transito:
            raise UserError(_(
                'No existe la ubicación de tránsito entre compañías '
                '(`stock.stock_location_inter_company`). Sin ella no se puede mover '
                'material de una sociedad a otra.'
            ))
        if not transito.sudo().active:
            raise UserError(_(
                'La ubicación de tránsito entre compañías está archivada. Hay que '
                'reactivarla antes de trasladar material entre sociedades.'
            ))
        if transito.sudo().company_id:
            raise UserError(_(
                'La ubicación de tránsito «%s» tiene una compañía asignada. Tiene que '
                'estar sin compañía, o la sociedad que recibe no podrá usarla.',
                transito.display_name,
            ))
        return transito.sudo()

    def _sincronizar_albaranes(self):
        """Crea los dos albaranes del traslado, o amplía los que ya haya.

        Se llama en cada aprobación, también en las que solo firman material añadido después
        (§7.2). Por eso **amplía en vez de rehacer**: cancelar los albaranes y crear otros
        dejaría al almacén con documentos anulados que ya había impreso, y el §7.0.2 pide
        expresamente lo contrario.

        Dos albaranes y no uno porque el movimiento cruza dos compañías: cada una valida el
        suyo y ve solo su mitad. El material vive en la ubicación de tránsito entre una
        validación y la otra.
        """
        self.ensure_one()
        transito = self._ubicacion_transito()
        if not self.picking_out_id:
            self.picking_out_id = self._crear_albaran(True, transito)
        if not self.picking_in_id:
            self.picking_in_id = self._crear_albaran(False, transito)
        self._sincronizar_movimientos()

    def _crear_albaran(self, salida, transito):
        self.ensure_one()
        almacen = self.warehouse_src_id if salida else self.warehouse_dest_id
        compania = almacen.company_id
        # El albarán lo prepara y valida el almacén dueño, pero lo dispara la aprobación, que
        # puede lanzar alguien de la otra sociedad: de ahí `sudo()` y `with_company()`.
        return self.env['stock.picking'].sudo().with_company(compania).create({
            'picking_type_id': almacen._enteza_tipo_prestamo(salida).id,
            'location_id': (
                self.warehouse_src_id.lot_stock_id.id if salida else transito.id
            ),
            'location_dest_id': (
                transito.id if salida else self.warehouse_dest_id.lot_stock_id.id
            ),
            'company_id': compania.id,
            'origin': self.name,
            'scheduled_date': fields.Datetime.to_datetime(self.date_transfer)
                              or fields.Datetime.now(),
            'enteza_loan_id': self.id,
        })

    def _sincronizar_movimientos(self):
        """Pone en cada albarán un movimiento por línea aprobada, sin duplicar.

        El enlace es `stock.move.enteza_loan_line_id`, no el producto: un mismo préstamo
        puede llevar el mismo artículo dos veces para intervalos distintos, y emparejar por
        producto mezclaría las cantidades.

        Solo entra lo que tiene `qty_approved`. Es la traducción física de la regla de
        siempre: **lo reservado protege el material, lo aprobado lo mueve.**
        """
        self.ensure_one()
        for salida, albaran in ((True, self.picking_out_id), (False, self.picking_in_id)):
            if not albaran or albaran.state in ('done', 'cancel'):
                continue
            albaran = albaran.sudo().with_company(albaran.company_id)
            for linea in self.line_ids:
                cantidad = linea.qty_approved
                movimiento = albaran.move_ids.filtered(
                    lambda mov: mov.enteza_loan_line_id == linea
                )
                if not cantidad:
                    # Línea sin firmar, o firmada y luego vaciada porque su pedido se redujo:
                    # si tenía movimiento, se cancela. Dejarlo vivo sacaría material del
                    # almacén para un evento que ya no existe.
                    movimiento.filtered(
                        lambda mov: mov.state not in ('done', 'cancel')
                    )._action_cancel()
                    continue
                if movimiento:
                    if movimiento.product_uom_qty != cantidad:
                        movimiento.product_uom_qty = cantidad
                    continue
                self.env['stock.move'].sudo().with_company(albaran.company_id).create({
                    # 🔴 `name` NO existe en `stock.move` en la 19: se eliminó. La
                    # descripción de la línea es `description_picking`. Con `name` la
                    # creación revienta con «Invalid field 'name' in 'stock.move'».
                    'description_picking': linea.product_id.display_name,
                    # `date` es obligatorio en la 19; se ata a la fecha del traslado para que
                    # el albarán y sus movimientos no digan días distintos.
                    'date': albaran.scheduled_date,
                    'product_id': linea.product_id.id,
                    'product_uom_qty': cantidad,
                    'product_uom': (
                        linea.product_uom_id.id or linea.product_id.uom_id.id
                    ),
                    'picking_id': albaran.id,
                    'location_id': albaran.location_id.id,
                    'location_dest_id': albaran.location_dest_id.id,
                    'company_id': albaran.company_id.id,
                    'enteza_loan_line_id': linea.id,
                })
            albaran.action_confirm()

    def _enteza_albaran_validado(self, albaran):
        """El almacén ha validado uno de los dos albaranes: el préstamo avanza.

        El estado lo mueve el hecho físico, no un botón del documento. Si dice `in_transit`
        es porque el material ha salido de verdad de las estanterías.

        A partir de `in_transit` el préstamo **deja de contar** en
        `_prestado_a_terceros` (ver `ESTADOS_COMPROMETEN`): el material ya no está en el
        almacén de la prestamista y su stock real lo refleja. Seguir contándolo lo restaría
        dos veces.
        """
        self.ensure_one()
        if albaran.enteza_devolucion:
            # De los dos albaranes de la vuelta, solo cuenta el que ATERRIZA en la
            # prestamista. Anotar la devolución al validar la salida contaría como devuelto
            # material que todavía va por la carretera.
            if albaran.location_dest_id == self.warehouse_src_id.lot_stock_id:
                self._enteza_devolucion_recibida(albaran)
            return
        if albaran == self.picking_out_id:
            for movimiento in albaran.move_ids.filtered('enteza_loan_line_id'):
                movimiento.enteza_loan_line_id.qty_sent = movimiento.quantity
            if self.state in ('reserved', 'approved'):
                self.state = 'in_transit'
        elif albaran == self.picking_in_id:
            if self.state in ('approved', 'in_transit'):
                self.state = 'lent'
            # La propiedad del material ya es de la receptora (D1). Es el punto donde la
            # asesoría fiscal decidirá si esto genera documento (§9).
            self._post_loan_hook()

    # ------------------------------------------------------------------
    # Devolución (PRP §7.5)
    # ------------------------------------------------------------------

    def action_proponer_devolucion(self):
        """Abre la propuesta de devolución. NO devuelve nada por su cuenta (D2)."""
        self.ensure_one()
        if self.state not in ('lent', 'partially_returned'):
            raise UserError(_(
                'Solo se puede proponer la devolución de un préstamo entregado. El %s está '
                'en estado «%s».',
                self.name, dict(ESTADOS).get(self.state, self.state),
            ))
        pendientes = self.line_ids.filtered(lambda linea: linea.qty_pending > 0)
        if not pendientes:
            raise UserError(_('El préstamo %s no tiene nada pendiente de devolver.',
                              self.name))

        asistente = self.env['enteza.prestamo.devolucion'].create({
            'loan_id': self.id,
            'line_ids': [
                (0, 0, {
                    'loan_line_id': datos['linea_id'],
                    'product_id': linea.product_id.id,
                    'qty_pendiente': datos['pendiente'],
                    'necesita_receptora': datos['necesita_receptora'],
                    'propio_receptora': datos['propio_receptora'],
                    'necesita_prestamista': datos['necesita_prestamista'],
                    'qty_retener': datos['retener'],
                    'qty_devolver': datos['devolver'],
                })
                for linea, datos in (
                    (linea, linea._calcular_devolucion()) for linea in pendientes
                )
            ],
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Devolver material prestado'),
            'res_model': 'enteza.prestamo.devolucion',
            'res_id': asistente.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_cerrar_con_diferencia(self):
        """Cierra un préstamo cuyo material no va a volver (§12, caso 3).

        Roto, perdido o simplemente no aparece. El préstamo no se puede quedar en `lent` para
        siempre inmovilizando una cifra que ya no significa nada, pero **cerrarlo tiene que
        dejar rastro**: qué faltaba y quién lo decidió.

        Cómo se salda económicamente es `[PENDIENTE-6]` y está fuera del módulo: aquí solo se
        cierra el documento y se anota la diferencia.
        """
        self.ensure_one()
        self._comprobar_responsable()
        if self.state not in ('lent', 'partially_returned'):
            raise UserError(_(
                'Solo se puede cerrar con diferencia un préstamo entregado. El %s está en '
                'estado «%s».', self.name, dict(ESTADOS).get(self.state, self.state),
            ))
        faltante = self.qty_pendiente_devolver
        if not faltante:
            raise UserError(_(
                'El préstamo %s no tiene nada pendiente: ciérralo por el circuito normal.',
                self.name,
            ))
        self._anotar(_(
            'Cerrado con una diferencia de %(cantidad)s unidades sin devolver, por decisión '
            'de %(usuario)s.',
            cantidad=faltante, usuario=self.env.user.display_name,
        ))
        self._marcar_para_revision(_(
            'Se cerró con %s unidades sin devolver. Falta decidir cómo se salda.', faltante,
        ))
        self.state = 'returned'
        return True

    def _crear_albaranes_devolucion(self, cantidades):
        """Genera el par de albaranes de vuelta: receptora → tránsito → prestamista.

        `cantidades` es `{linea_de_prestamo: cantidad}`. Cada devolución parcial genera **su
        propio par**: son viajes distintos, y mezclarlos en un albarán que se reabre haría
        imposible saber qué salió cada día.

        Se reutilizan los tipos de operación que ya existen, cambiados de bando: la salida la
        hace ahora el almacén que recibió el préstamo y la entrada el que lo prestó.
        """
        self.ensure_one()
        transito = self._ubicacion_transito()
        Albaran = self.env['stock.picking'].sudo()
        Movimiento = self.env['stock.move'].sudo()

        albaranes = self.env['stock.picking'].sudo()
        for salida in (True, False):
            almacen = self.warehouse_dest_id if salida else self.warehouse_src_id
            compania = almacen.company_id
            albaran = Albaran.with_company(compania).create({
                'picking_type_id': almacen._enteza_tipo_prestamo(salida).id,
                'location_id': (
                    self.warehouse_dest_id.lot_stock_id.id if salida else transito.id
                ),
                'location_dest_id': (
                    transito.id if salida else self.warehouse_src_id.lot_stock_id.id
                ),
                'company_id': compania.id,
                'origin': _('%s · devolución', self.name),
                'scheduled_date': fields.Datetime.now(),
                'enteza_loan_id': self.id,
                'enteza_devolucion': True,
            })
            for linea, cantidad in cantidades.items():
                if cantidad <= 0:
                    continue
                Movimiento.with_company(compania).create({
                    'description_picking': linea.product_id.display_name,
                    'date': albaran.scheduled_date,
                    'product_id': linea.product_id.id,
                    'product_uom_qty': cantidad,
                    'product_uom': linea.product_uom_id.id or linea.product_id.uom_id.id,
                    'picking_id': albaran.id,
                    'location_id': albaran.location_id.id,
                    'location_dest_id': albaran.location_dest_id.id,
                    'company_id': compania.id,
                    'enteza_loan_line_id': linea.id,
                })
            albaran.action_confirm()
            albaranes |= albaran
        return albaranes

    def _enteza_devolucion_recibida(self, albaran):
        """La prestamista ha recibido el material de vuelta: se anota y se cierra si toca."""
        self.ensure_one()
        devueltas = self.env['enteza.stock.loan.line']
        for movimiento in albaran.move_ids.filtered('enteza_loan_line_id'):
            linea = movimiento.enteza_loan_line_id
            linea.qty_returned += movimiento.quantity
            devueltas |= linea

        redondeo = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        cerrado = all(
            float_compare(linea.qty_pending, 0.0, precision_digits=redondeo) <= 0
            for linea in self.line_ids
        )
        self.state = 'returned' if cerrado else 'partially_returned'
        self._post_return_hook(devueltas)

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
