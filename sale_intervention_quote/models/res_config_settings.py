from odoo import api, fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    intervention_speed_kmh = fields.Float(
        string="Velocidad desplazamiento (km/h)", default=90.0,
        config_parameter="sale_intervention_quote.speed_kmh"
    )
    product_labor_normal_id = fields.Many2one(
        "product.product", string="Producto Mano de Obra (normal)",
        config_parameter="sale_intervention_quote.product_labor_normal_id",
        domain=[("type", "in", ["service","consu","product"])]
    )
    product_labor_overtime_id = fields.Many2one(
        "product.product", string="Producto Mano de Obra (extra)",
        config_parameter="sale_intervention_quote.product_labor_overtime_id",
        domain=[("type", "in", ["service","consu","product"])]
    )
    product_mobile_unit_id = fields.Many2one(
        "product.product", string="Producto Unidad Móvil (coste horario)",
        config_parameter="sale_intervention_quote.product_mobile_unit_id",
        domain=[("type", "in", ["service","consu","product"])]
    )
    mobile_time_uom = fields.Selection(
        [("hour","Horas"),("minute","Minutos")],
        string="UoM tiempo Unidad Móvil", default="minute",
        config_parameter="sale_intervention_quote.mobile_time_uom"
    )
    consumables_percent = fields.Float(
        string="% Consumibles sobre materiales", default=0.0,
        help="Ej. 5.0 para 5%", config_parameter="sale_intervention_quote.consumables_percent"
    )
    product_consumables_id = fields.Many2one(
        "product.product", string="Producto Consumibles",
        config_parameter="sale_intervention_quote.product_consumables_id",
        domain=[("type", "in", ["service","consu","product"])]
    )
