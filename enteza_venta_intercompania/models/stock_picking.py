from odoo import _, fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    enteza_cesion_origen_picking_id = fields.Many2one(
        'stock.picking',
        string="Albarán de cesión de origen",
        copy=False,
        readonly=True,
        index=True,
        prefetch=False,
        help="Albarán de la compañía dueña que, al validarse, preparó este.",
    )

    _enteza_cesion_origen_uniq = models.UniqueIndex(
        '(enteza_cesion_origen_picking_id) WHERE enteza_cesion_origen_picking_id IS NOT NULL',
        "Ese albarán de cesión ya tiene su albarán en la compañía receptora.")

    def _action_done(self):
        """Al validar un albarán de una cesión, se prepara el espejo en la receptora.

        En `_action_done` y no en `button_validate`: por aquí pasan todos los caminos que
        validan un albarán (asistentes de backorder, otros módulos), como en
        `enteza_prestamo_intercompania`.
        """
        result = super()._action_done()
        for picking in self.filtered(
                lambda p: p.state == 'done' and p.sale_id.enteza_cesion_intercompania):
            picking._enteza_cesion_crear_espejo()
        return result

    def _enteza_cesion_crear_espejo(self):
        """Recepción (si la dueña entregó) o salida (si recibió de vuelta) en la receptora.

        Se deja confirmado, sin validar: lo valida el almacén de la receptora cuando el
        material llega o sale de verdad. La recepción lleva propietario = la dueña (Consigna),
        para que la receptora no lo valore como existencia suya.

        Origen y destino son Proveedores y Clientes, no el tránsito intercompañía: en la 19
        el tránsito exige existencias para reservar (`should_bypass_reservation`), y aquí la
        dueña no deja nada en él —su material pasa a su propia ubicación de Alquiler—.
        """
        self.ensure_one()
        rental_loc = self.company_id.rental_loc_id
        if self.location_dest_id == rental_loc:
            incoming = True
        elif self.location_id == rental_loc:
            incoming = False
        else:
            return
        # sudo(): lo valida el almacén de la dueña y el albarán nuevo es de la receptora, a la
        # que ese usuario puede no tener acceso.
        Picking = self.env['stock.picking'].sudo()
        if Picking.search_count([('enteza_cesion_origen_picking_id', '=', self.id)]):
            return
        moves = self.move_ids.filtered(
            lambda m: m.state == 'done' and m.product_uom.compare(m.quantity, 0.0) > 0)
        if not moves:
            return

        order = self.sale_id
        warehouse = order.sudo().enteza_cesion_warehouse_dest_id
        company = warehouse.company_id
        owner = self.company_id.partner_id
        if incoming:
            picking_type = warehouse.in_type_id
            location = self.env.ref('stock.stock_location_suppliers')
            location_dest = warehouse.lot_stock_id
        else:
            picking_type = warehouse.out_type_id
            location = warehouse.lot_stock_id
            location_dest = self.env.ref('stock.stock_location_customers')

        mirror = Picking.with_company(company).create({
            'picking_type_id': picking_type.id,
            'partner_id': owner.id,
            'location_id': location.id,
            'location_dest_id': location_dest.id,
            # En la salida no: todas sus existencias de estos productos son de la dueña, y un
            # propietario en la salida reescribiría el de las líneas ya reservadas.
            'owner_id': owner.id if incoming else False,
            'company_id': company.id,
            'origin': '%s - %s' % (order.name, self.name),
            'enteza_cesion_origen_picking_id': self.id,
        })
        self.env['stock.move'].sudo().with_company(company).create([{
            # En la 19 `stock.move` no tiene `name` y `date` es obligatorio.
            'description_picking': move.product_id.display_name,
            'date': mirror.scheduled_date,
            'product_id': move.product_id.id,
            'product_uom_qty': move.quantity,
            'product_uom': move.product_uom.id,
            'picking_id': mirror.id,
            'location_id': location.id,
            'location_dest_id': location_dest.id,
            'company_id': company.id,
        } for move in moves])
        mirror.action_confirm()

        mirror.message_post(body=_(
            "Preparado al validar %(picking)s de la cesión %(order)s (%(company)s).",
            picking=self._get_html_link(), order=order._get_html_link(),
            company=self.company_id.name))
        self.message_post(body=_(
            "Preparado %(picking)s en %(company)s para validarlo allí.",
            picking=mirror._get_html_link(), company=company.name))
