from odoo import api, fields, models, tools


class EntezaStockLoanLine(models.Model):
    _name = 'enteza.stock.loan.line'
    _description = 'Línea de préstamo entre compañías'

    loan_id = fields.Many2one(
        'enteza.stock.loan', string='Préstamo', required=True, ondelete='cascade', index=True,
    )
    company_id = fields.Many2one(related='loan_id.company_id', store=True, index=True)
    state = fields.Selection(related='loan_id.state', store=True, index=True)
    # Almacenado porque el cálculo de disponibilidad filtra por almacén de origen en cada
    # confirmación de pedido: atravesar la cabecera en el dominio lo haría inviable.
    warehouse_src_id = fields.Many2one(
        related='loan_id.warehouse_src_id', store=True, index=True,
        string='Almacén de origen',
    )

    product_id = fields.Many2one(
        'product.product', string='Producto', required=True, index=True,
    )
    product_uom_id = fields.Many2one(
        'uom.uom', string='Unidad de medida',
        help='Las cantidades se guardan en la unidad de referencia del producto, igual '
             'que hace el cálculo nativo de alquiler con `product_uom_qty`. El caso de '
             'artículos gestionados en otra unidad (docenas) está pendiente y hay que '
             'resolverlo a la vez aquí y en el motor de disponibilidad.',
    )

    qty_proposed = fields.Float(string='Cantidad propuesta', digits='Product Unit of Measure')
    qty_reserved = fields.Float(
        string='Cantidad reservada', digits='Product Unit of Measure',
        help='Reservada en firme en la compañía prestamista. Es la cantidad que alimenta '
             '`prestado_a_terceros` en el cálculo de disponibilidad.',
    )
    qty_approved = fields.Float(string='Cantidad aprobada', digits='Product Unit of Measure')
    qty_sent = fields.Float(
        string='Cantidad trasladada', digits='Product Unit of Measure', readonly=True,
    )
    qty_returned = fields.Float(
        string='Cantidad devuelta', digits='Product Unit of Measure', readonly=True,
    )
    qty_pending = fields.Float(
        string='Pendiente de devolver', digits='Product Unit of Measure',
        compute='_compute_qty_pending', store=True,
    )

    # 🔴 Intervalo que ocupa la reserva. Sin él no se puede calcular `prestado_a_terceros`
    # por fecha y la reserva bloquearía el material indefinidamente (PRP §5.5).
    date_from = fields.Datetime(string='Reservado desde', required=True, index=True)
    date_to = fields.Datetime(string='Reservado hasta', required=True)

    sale_line_id = fields.Many2one(
        'sale.order.line', string='Línea de pedido', index=True, ondelete='set null',
        help='Línea de alquiler que motivó el préstamo. Permite liberar la reserva si el '
             'pedido se reduce o se cancela.',
    )
    deficit_date = fields.Date(string='Fecha del déficit')

    @api.depends('qty_sent', 'qty_returned')
    def _compute_qty_pending(self):
        for linea in self:
            linea.qty_pending = linea.qty_sent - linea.qty_returned

    def _qty_comprometida(self):
        """Cantidad que esta línea compromete en la compañía prestamista.

        Mientras está en `reserved` manda lo reservado; una vez aprobada manda lo que
        autorizó el responsable, que puede haber ajustado la cantidad a la baja.
        """
        self.ensure_one()
        if self.loan_id.state == 'approved' and self.qty_approved:
            return self.qty_approved
        return self.qty_reserved

    def _auto_init(self):
        # Índice compuesto para el cálculo de `prestado_a_terceros`, que se ejecuta en cada
        # confirmación de pedido y tiene que resolverse rápido (PRP §6.3). Los índices por
        # campo suelto no sirven aquí: el dominio filtra siempre por los cuatro a la vez.
        resultado = super()._auto_init()
        tools.create_index(
            self._cr,
            'enteza_stock_loan_line_producto_intervalo_idx',
            self._table,
            ['product_id', 'warehouse_src_id', 'date_from', 'date_to'],
        )
        return resultado
