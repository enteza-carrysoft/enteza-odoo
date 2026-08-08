from odoo import api, fields, models


class ProductTemplate(models.Model):
    """Caja/packaging derivado del nativo de la 19 (PRP §2.6, §4.3, §7).

    En Odoo 19 `product.packaging` ya no existe: se fusionó con las unidades de medida. El
    packaging vive en `uom_ids` («Packagings»), un m2m a `uom.uom`. Una «CAJA 25 UDS» es un
    registro de `uom.uom` con `relative_uom_id` = la unidad base del producto y
    `relative_factor` = 25 (⚠️ es `relative_factor`, NO `factor`: ese campo antiguo sigue
    existiendo pero ya no es el que usa la 19 para packagings).

    Este compute no crea ningún dato: solo LEE lo que el comercial haya configurado en
    «Packagings» y se queda con la caja más pequeña, para que el portal pueda aplicar la
    regla de múltiplos sin que cada sitio del código tenga que repetir la búsqueda.
    """
    _inherit = 'product.template'

    enteza_box_uom_id = fields.Many2one(
        'uom.uom', string="Caja", compute='_compute_enteza_box', store=True,
        compute_sudo=True,
        help="Packaging más pequeño declarado en «Packagings» (uom_ids) para la unidad "
             "base de este producto. Vacío si el artículo se pide por unidades sueltas.")

    enteza_units_per_box = fields.Float(
        string="Uds. por caja", compute='_compute_enteza_box', store=True,
        compute_sudo=True, digits='Product Unit of Measure',
        help="0 = el artículo se pide por unidades sueltas, sin restricción de múltiplo. "
             "Con packaging, la cantidad solicitada en el portal debe ser múltiplo de este "
             "valor: no se entregan nunca medias cajas.")

    enteza_portal_ok = fields.Boolean(
        string="Visible en el portal de clientes", default=True, index=True,
        help="Desmarcar para que el artículo no aparezca en la rejilla de solicitud del "
             "portal, aunque sea alquilable.")

    @api.depends('uom_ids', 'uom_ids.relative_factor', 'uom_ids.relative_uom_id', 'uom_id')
    def _compute_enteza_box(self):
        for plantilla in self:
            candidatas = plantilla.uom_ids.filtered(
                lambda uom, base=plantilla.uom_id:
                    uom.relative_uom_id == base and uom.relative_factor > 1
            )
            caja = min(candidatas, key=lambda uom: uom.relative_factor) if candidatas \
                else self.env['uom.uom']
            plantilla.enteza_box_uom_id = caja
            plantilla.enteza_units_per_box = caja.relative_factor if caja else 0.0
