"""Dimensiones de búsqueda (PRP §2.4, §4.4, §15). No ejecutados: ver README del módulo."""
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestFacets(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({
            'name': 'Cliente facetas',
            'enteza_portal_pedidos_ok': True,
        })
        cls.faceta_marca = cls.env['enteza.product.facet'].create({
            'name': 'Marca (test)',
            'portal_visible': True,
        })
        cls.faceta_interna = cls.env['enteza.product.facet'].create({
            'name': 'Interna (test)',
            'portal_visible': False,
        })
        cls.tag_visible = cls.env['product.tag'].create({
            'name': 'Vimaple (test)',
            'enteza_facet_id': cls.faceta_marca.id,
            'visible_to_customers': True,
        })
        cls.tag_oculta = cls.env['product.tag'].create({
            'name': 'Revisar (test)',
            'enteza_facet_id': cls.faceta_marca.id,
            'visible_to_customers': False,
        })
        cls.tag_interna = cls.env['product.tag'].create({
            'name': 'Interno (test)',
            'enteza_facet_id': cls.faceta_interna.id,
            'visible_to_customers': True,
        })
        cls.tag_sin_faceta = cls.env['product.tag'].create({
            'name': 'Sin dimensión (test)',
        })
        cls.producto = cls.env['product.template'].create({
            'name': 'Silla facetas (test)',
            'type': 'consu',
            'rent_ok': True,
            'product_tag_ids': [(6, 0, [
                cls.tag_visible.id, cls.tag_oculta.id,
                cls.tag_interna.id, cls.tag_sin_faceta.id,
            ])],
        })

    def _catalogo(self):
        pedido = self.env['sale.order']._enteza_portal_get_or_create(self.partner)
        return pedido._enteza_portal_payload_catalogo()

    def test_facet_with_portal_visible_false_is_not_served(self):
        """`portal_visible=False`: la dimensión existe para uso interno pero no genera
        desplegable en el portal (PRP §4.4)."""
        payload = self._catalogo()
        nombres = {f['name'] for f in payload['facets']}
        self.assertIn('Marca (test)', nombres)
        self.assertNotIn('Interna (test)', nombres)

    def test_hidden_tag_does_not_reach_the_dropdown(self):
        """`visible_to_customers=False` en la etiqueta: no llega al portal aunque su
        dimensión sí sea visible."""
        payload = self._catalogo()
        faceta = next(f for f in payload['facets'] if f['name'] == 'Marca (test)')
        etiquetas = {t['name'] for t in faceta['tags']}
        self.assertIn('Vimaple (test)', etiquetas)
        self.assertNotIn('Revisar (test)', etiquetas)

    def test_tag_without_facet_is_irrelevant_to_filtering(self):
        """Una etiqueta sin dimensión asignada no sirve para filtrar: no viaja en
        `tag_ids` (no hay ningún desplegable contra el que compararla) ni aparece en
        ninguna faceta."""
        payload = self._catalogo()
        fila = next(p for p in payload['products'] if p['name'] == 'Silla facetas (test)')
        self.assertNotIn(self.tag_sin_faceta.id, fila['tag_ids'])
        for faceta in payload['facets']:
            self.assertNotIn(self.tag_sin_faceta.id, [t['id'] for t in faceta['tags']])

    def test_facet_without_used_tags_is_not_served(self):
        """Una faceta cuyos valores no usa ningún producto del catálogo servido no se
        manda: un desplegable vacío es ruido (PRP §8.3)."""
        vacia = self.env['enteza.product.facet'].create({
            'name': 'Vacía (test)', 'portal_visible': True,
        })
        self.env['product.tag'].create({
            'name': 'Sin producto (test)', 'enteza_facet_id': vacia.id,
            'visible_to_customers': True,
        })
        payload = self._catalogo()
        nombres = {f['name'] for f in payload['facets']}
        self.assertNotIn('Vacía (test)', nombres)

    def test_payload_sends_tag_ids_as_integers_not_repeated_names(self):
        """El payload manda `tag_ids` como enteros; los nombres viajan una sola vez, en
        `facets` (PRP §8.3: con 1.025 filas repetir cadenas triplicaría el peso)."""
        payload = self._catalogo()
        fila = next(p for p in payload['products'] if p['name'] == 'Silla facetas (test)')
        self.assertIsInstance(fila['tag_ids'], list)
        self.assertTrue(all(isinstance(i, int) for i in fila['tag_ids']))
        self.assertIn(self.tag_visible.id, fila['tag_ids'])

    def test_assigning_tag_uses_the_native_many2many(self):
        """El comercial etiqueta desde el widget nativo de siempre: no hay ninguna
        relación nueva en el producto (PRP §4.4)."""
        self.assertIn(self.tag_visible, self.producto.product_tag_ids)
