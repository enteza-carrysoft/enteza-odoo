from odoo import api, fields, models
from math import ceil

class InterventionMaterialLine(models.TransientModel):
    _name = "intervention.material.line"
    _description = "Materiales del presupuesto (wizard)"

    wizard_id = fields.Many2one("intervention.quote.wizard", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Producto", required=True)
    quantity = fields.Float(string="Cantidad", default=1.0)

class InterventionQuoteWizard(models.TransientModel):
    _name = "intervention.quote.wizard"
    _description = "Wizard Presupuesto de Intervención"

    # Vínculo
    order_id = fields.Many2one("sale.order", required=True)

    # Parámetros
    distance_km_one_way = fields.Float(string="Distancia (km) solo ida", required=True, default=200.0)
    on_site_hours = fields.Float(string="Horas previstas en obra", required=True, default=2.0)
    num_workers = fields.Integer(string="Nº de operarios", required=True, default=2)
    overtime_hours_per_worker = fields.Float(string="Horas extra por operario (opc.)", default=0.0)

    # Materiales
    material_line_ids = fields.One2many("intervention.material.line", "wizard_id", string="Materiales")

    # Config por defecto (lectura de ajustes)
    speed_kmh = fields.Float(string="Velocidad (km/h)", default=lambda self: float(self.env["ir.config_parameter"].sudo().get_param("sale_intervention_quote.speed_kmh", default="90.0")))
    product_labor_normal_id = fields.Many2one("product.product", string="Producto Mano de Obra (normal)", default=lambda self: int(self.env["ir.config_parameter"].sudo().get_param("sale_intervention_quote.product_labor_normal_id", default="0")) or False)
    product_labor_overtime_id = fields.Many2one("product.product", string="Producto Mano de Obra (extra)", default=lambda self: int(self.env["ir.config_parameter"].sudo().get_param("sale_intervention_quote.product_labor_overtime_id", default="0")) or False)
    product_mobile_unit_id = fields.Many2one("product.product", string="Producto Unidad Móvil", default=lambda self: int(self.env["ir.config_parameter"].sudo().get_param("sale_intervention_quote.product_mobile_unit_id", default="0")) or False)
    mobile_time_uom = fields.Selection([("hour","Horas"),("minute","Minutos")], string="UoM tiempo Unidad Móvil", default=lambda self: self.env["ir.config_parameter"].sudo().get_param("sale_intervention_quote.mobile_time_uom","minute"))
    consumables_percent = fields.Float(string="% Consumibles", default=lambda self: float(self.env["ir.config_parameter"].sudo().get_param("sale_intervention_quote.consumables_percent", default="0.0")))
    product_consumables_id = fields.Many2one("product.product", string="Producto Consumibles", default=lambda self: int(self.env["ir.config_parameter"].sudo().get_param("sale_intervention_quote.product_consumables_id", default="0")) or False)

    def _compute_times(self):
        """Devuelve (travel_hours_roundtrip, total_hours_per_worker)"""
        self.ensure_one()
        speed = self.speed_kmh or 90.0
        travel_one_way_h = (self.distance_km_one_way or 0.0) / speed
        travel_roundtrip_h = travel_one_way_h * 2.0
        total_per_worker_h = travel_roundtrip_h + (self.on_site_hours or 0.0)
        return travel_roundtrip_h, total_per_worker_h

    def _to_minutes(self, hours):
        return int(round(hours * 60.0))

    def action_apply(self):
        self.ensure_one()
        order = self.order_id
        vals_list = []

        # 1) Cálculos de tiempo
        travel_h, total_worker_h = self._compute_times()
        nworkers = max(0, self.num_workers)
        overtime_per_worker_h = max(0.0, self.overtime_hours_per_worker)

        # 2) Mano de obra normal / extra
        labor_normal_h_total = max(0.0, (total_worker_h - overtime_per_worker_h)) * nworkers
        labor_overtime_h_total = overtime_per_worker_h * nworkers

        # 3) Unidad móvil (tiempo total de desplazamiento + obra)
        mobile_time_h = total_worker_h  # Se factura por el mismo tiempo global
        mobile_qty = mobile_time_h
        mobile_qty_minutes = self._to_minutes(mobile_time_h)

        # 4) Materiales (sumatorio para consumibles)
        materials_subtotal = 0.0
        for ml in self.material_line_ids:
            product = ml.product_id
            qty = ml.quantity
            if not product or qty <= 0:
                continue
            # Deja que Odoo haga el pricing con listas/tarifas/impuestos:
            vals_list.append({
                "order_id": order.id,
                "product_id": product.id,
                "name": product.get_product_multiline_description_sale() or product.name,
                "product_uom": product.uom_id.id,
                "product_uom_qty": qty,
                # Sin price_unit para permitir reglas de precio; taxes se aplican en onchange
            })

        # Creamos primero las líneas de materiales para poder calcular su subtotal real si hiciera falta.
        material_lines = self.env["sale.order.line"].create(vals_list) if vals_list else self.env["sale.order.line"]
        vals_list = []

        # Recalcular subtotal materiales (con precio de tarifa ya aplicado)
        for line in material_lines:
            materials_subtotal += line.price_unit * line.product_uom_qty * (1 - (line.discount or 0.0)/100.0)

        # 5) Línea Mano de Obra (normal)
        if labor_normal_h_total > 0 and self.product_labor_normal_id:
            labor_product = self.product_labor_normal_id
            vals_list.append({
                "order_id": order.id,
                "product_id": labor_product.id,
                "name": labor_product.get_product_multiline_description_sale() or labor_product.name,
                "product_uom": labor_product.uom_id.id,  # debería ser hora
                "product_uom_qty": labor_normal_h_total,
            })

        # 6) Línea Mano de Obra (extra)
        if labor_overtime_h_total > 0 and self.product_labor_overtime_id:
            ot_product = self.product_labor_overtime_id
            vals_list.append({
                "order_id": order.id,
                "product_id": ot_product.id,
                "name": ot_product.get_product_multiline_description_sale() or ot_product.name,
                "product_uom": ot_product.uom_id.id,
                "product_uom_qty": labor_overtime_h_total,
            })

        # 7) Línea Unidad Móvil
        if self.product_mobile_unit_id and mobile_time_h > 0:
            mobile_product = self.product_mobile_unit_id
            if self.mobile_time_uom == "minute":
                # Si el producto tiene UoM en horas, multiplicamos qty en horas con price_unit por hora.
                # Alternativa: crear una UoM "minuto" y asignarla al producto.
                qty = mobile_qty  # horas; precio/hora
            else:
                qty = mobile_qty  # horas igual
            vals_list.append({
                "order_id": order.id,
                "product_id": mobile_product.id,
                "name": mobile_product.get_product_multiline_description_sale() or mobile_product.name,
                "product_uom": mobile_product.uom_id.id,
                "product_uom_qty": qty,
            })

        # 8) Línea Consumibles (% sobre materiales)
        percent = max(0.0, self.consumables_percent or 0.0)
        if percent > 0.0 and self.product_consumables_id and materials_subtotal > 0.0:
            cons_product = self.product_consumables_id
            amount = materials_subtotal * (percent / 100.0)
            # Creamos 1 unidad cuyo price_unit = importe calculado, para reflejar el % sobre materiales.
            vals_list.append({
                "order_id": order.id,
                "product_id": cons_product.id,
                "name": f"{cons_product.display_name} ({percent:.2f}% sobre materiales)",
                "product_uom": cons_product.uom_id.id,
                "product_uom_qty": 1.0,
                "price_unit": amount,
            })

        if vals_list:
            self.env["sale.order.line"].create(vals_list)

        return {"type": "ir.actions.act_window_close"}
