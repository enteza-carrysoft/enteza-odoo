from odoo import fields, models


class ProductFacet(models.Model):
    """Dimensión de búsqueda del catálogo del portal (PRP §2.4, §4.4).

    `product.tag` ya trae `visible_to_customers` y el m2m con el producto, pero es una bolsa
    plana: no hay forma de saber que «Vimaple» y «Colonial» son valores de «Marca» mientras
    que «Blanco» y «Natural» son valores de «Color». Este modelo es el eslabón que falta.

    Cada faceta se convierte en un desplegable del portal (§9.3). Se crea aquí, en Odoo, sin
    tocar código: es la promesa del criterio de aceptación §16.3c.
    """
    _name = 'enteza.product.facet'
    _description = "Dimensión de búsqueda del catálogo del portal"
    _order = 'sequence, name'

    name = fields.Char(string="Nombre", required=True, translate=True)
    sequence = fields.Integer(string="Secuencia", default=10)
    active = fields.Boolean(string="Activa", default=True)
    tag_ids = fields.One2many('product.tag', 'enteza_facet_id', string="Valores")
    tag_count = fields.Integer(string="Nº de valores", compute='_compute_tag_count')
    portal_visible = fields.Boolean(
        string="Mostrar en el portal", default=True,
        help="Desmarcar para usar la dimensión solo internamente, sin que se convierta en "
             "un desplegable del portal de clientes.")
    multi = fields.Boolean(
        string="Permite varios valores", default=True,
        help="Si está marcado, el cliente puede elegir varias opciones a la vez dentro de "
             "esta dimensión (se combinan con O). Si no, la selección es única.")

    _name_uniq = models.Constraint('UNIQUE(name)', "Ya existe una dimensión con ese nombre.")

    def _compute_tag_count(self):
        for faceta in self:
            faceta.tag_count = len(faceta.tag_ids)
