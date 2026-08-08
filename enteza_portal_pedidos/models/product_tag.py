from odoo import fields, models


class ProductTag(models.Model):
    """Cada etiqueta puede pertenecer a una dimensión de búsqueda (PRP §2.4, §4.4).

    No se crea ninguna relación nueva en el producto: se sigue usando el m2m nativo
    `product.template.product_tag_ids`, con su widget de etiquetas de siempre. Lo único que
    añade este módulo es DÓNDE se agrupa cada etiqueta para formar los desplegables del
    portal — y el filtro de visibilidad nativo `visible_to_customers` decide cuáles llegan.
    """
    _inherit = 'product.tag'

    enteza_facet_id = fields.Many2one(
        'enteza.product.facet', string="Dimensión", index=True, ondelete='set null',
        help="Desplegable del portal en el que aparece esta etiqueta. Sin dimensión, la "
             "etiqueta no se usa como filtro en el portal de clientes.")
