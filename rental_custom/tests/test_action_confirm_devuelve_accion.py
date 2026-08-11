from unittest.mock import patch

from odoo.addons.sale.models.sale_order import SaleOrder as SaleOrderBase
from odoo.tests.common import TransactionCase


class TestActionConfirmDevuelveAccion(TransactionCase):
    """`action_confirm` debe propagar TAL CUAL lo que devuelve la cadena de herencia.

    Regresión del 12/08/2026. `rental_custom` troceaba el recordset para que los pedidos
    marcados como "no generar albarán" saltasen el envío, y recomponía el resultado con
    `super().action_confirm() and result`. Cuando otro módulo de la cadena devuelve una ACCIÓN
    en vez de `True` —`enteza_prestamo_intercompania` devuelve el diálogo de "falta material"
    en cuanto una línea tiene déficit, y sin inventario cargado eso son todas—, el `and` la
    reducía a `True`: el diálogo no llegaba al navegador y el pedido se quedaba en presupuesto
    sin ningún mensaje. Como no se confirmaba nada, no se generaba ningún movimiento de
    almacén en toda la instalación.

    El contrato de `action_confirm` admite devolver un `dict` de acción y quien lo extienda
    tiene que dejarlo pasar intacto.
    """

    def test_propaga_la_accion_que_devuelve_la_cadena(self):
        partner = self.env["res.partner"].create({"name": "Cliente diálogo"})
        product = self.env["product.product"].create({
            "name": "Artículo diálogo",
            "lst_price": 10.0,
        })
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "order_line": [(0, 0, {"product_id": product.id, "product_uom_qty": 1})],
        })

        accion = {"type": "ir.actions.act_window", "res_model": "enteza.prestamo.confirm"}
        with patch.object(SaleOrderBase, "action_confirm", return_value=accion):
            resultado = order.action_confirm()

        self.assertEqual(
            resultado,
            accion,
            "action_confirm ha perdido la acción devuelta por la cadena de herencia: el "
            "diálogo no llegaría al navegador y el pedido se quedaría en presupuesto.",
        )
