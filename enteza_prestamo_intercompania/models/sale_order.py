"""Enganche en la confirmación del pedido (PRP D5, D5.1 y §7.0).

Es el camino principal del módulo: al confirmar un pedido de alquiler que el almacén propio
no puede servir, se propone cubrirlo con material de la otra compañía y **se pide permiso
antes de reservar nada**.

🔴 Por qué esto son DOS transacciones
--------------------------------------
Entre que se enseña la propuesta y el comercial la acepta pasan segundos o minutos. El
bloqueo de concurrencia **no se puede sostener durante ese rato**: sería una transacción
abierta bloqueando a todos los demás comerciales sobre esos productos, es decir, un cuelgue
justo en temporada alta, que es cuando hay cola.

De ahí el reparto:

- **Paso 1, aquí** (`action_confirm`): solo mira. Calcula, propone y abre el diálogo. No toma
  bloqueo y no escribe nada.
- **Paso 2, en el asistente**: bloquea, **recalcula desde cero** y solo entonces reserva.

Es decir, **el diálogo es una propuesta, no una reserva**. Si mientras el comercial decidía
otro pedido se llevó el material, al aceptar no se reserva nada y se le dice qué ha cambiado.
"""

from odoo import _, models
from odoo.exceptions import UserError

# Espacio de nombres de los bloqueos de asesoramiento de PostgreSQL. Es un número arbitrario;
# lo único que importa es que no lo use nadie más en esta base de datos.
ESPACIO_BLOQUEO_PRESTAMO = 720190


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _action_cancel(self):
        """Al cancelar el pedido se libera lo que tenía comprometido en préstamos (§7.0.2).

        🔴 Es lo que hace viable juntar varios pedidos en un mismo viaje. Sin esto, cancelar
        uno de los eventos dejaba su material comprometido para siempre: la prestamista no
        podía volver a venderlo y, si el traslado ya estaba aprobado, **viajaba igualmente**.

        Se libera **antes** de llamar a `super()`: mientras las líneas siguen en `sale`. Es
        el único momento en que se sabe con certeza qué aportaba cada una.

        Se engancha en `_action_cancel` y no en `action_cancel` porque el segundo es solo el
        botón; el asistente de cancelación y las llamadas de otros módulos pasan por este.
        """
        for pedido in self:
            pedido.order_line._enteza_liberar_prestamo(motivo=_(
                'Se ha cancelado el pedido %s.', pedido.name,
            ))
        return super()._action_cancel()

    def action_confirm(self):
        """Intercepta la confirmación si hay déficit que cubrir (PRP §7.0, paso 1).

        Devuelve una acción en vez de `True` cuando abre el diálogo. Es el idioma de Odoo
        para los botones que necesitan preguntar algo — el mismo que usa
        `stock.picking.button_validate` con el asistente de entregas parciales.
        """
        if self.env.context.get('enteza_prestamo_aceptado'):
            # Segunda pasada, ya con el permiso dado en el diálogo. Sin esta salida el
            # asistente volvería a abrir el diálogo al reconfirmar: bucle infinito.
            return super().action_confirm()

        con_deficit = self.filtered(lambda pedido: pedido._enteza_lineas_con_deficit())
        if not con_deficit:
            return super().action_confirm()

        if len(con_deficit) > 1:
            # Confirmar varios a la vez desde la lista. No se puede preguntar por uno sin
            # dejar los demás a medias, y confirmarlos en silencio se saltaría el permiso que
            # D5.1 existe para pedir. Se para y se dice cuáles.
            raise UserError(_(
                'Estos pedidos necesitan material prestado de otra compañía y hay que '
                'revisarlos de uno en uno:\n\n%(pedidos)s',
                pedidos='\n'.join('· %s' % pedido.display_name for pedido in con_deficit),
            ))

        return con_deficit._enteza_abrir_dialogo_prestamo()

    # ------------------------------------------------------------------
    # Propuesta (paso 1: solo lectura)
    # ------------------------------------------------------------------

    def _enteza_lineas_con_deficit(self):
        """Líneas que este almacén no puede servir, con o sin quien las preste."""
        self.ensure_one()
        return self.order_line.filtered(lambda linea: linea.enteza_falta > 0)

    def _enteza_abrir_dialogo_prestamo(self):
        """Monta el asistente con la propuesta y devuelve la acción que lo abre."""
        self.ensure_one()
        lineas = self._enteza_lineas_con_deficit()

        asistente = self.env['enteza.prestamo.confirm'].create({
            'order_id': self.id,
            'line_ids': [
                (0, 0, {
                    'sale_line_id': linea.id,
                    'product_id': linea.product_id.id,
                    'qty_pedida': linea.product_uom_qty,
                    # Se guarda lo propuesto para poder compararlo al aceptar: es lo que
                    # detecta que la propuesta ha caducado.
                    'qty_falta': linea.enteza_falta,
                    'qty_prestable': linea.enteza_prestable_otra,
                    'warehouse_src_id': linea.enteza_almacen_prestamista_id.id or False,
                })
                for linea in lineas
            ],
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('Falta material para este pedido'),
            'res_model': 'enteza.prestamo.confirm',
            'res_id': asistente.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

    # ------------------------------------------------------------------
    # Bloqueo (paso 2)
    # ------------------------------------------------------------------

    def _enteza_bloquear_productos(self, productos):
        """Bloqueo de concurrencia del PRP §5.6, acotado a la transacción.

        Sin esto, dos comerciales que confirman a la vez el mismo artículo para las mismas
        fechas ven ambos el mismo material libre y **lo reservan los dos**: se venden 200
        unidades que no existen, y encima con toda la apariencia de estar bien.

        Se usa un bloqueo de asesoramiento de PostgreSQL en vez de `SELECT ... FOR UPDATE`
        sobre el producto: se libera solo al cerrar la transacción, no deja filas bloqueadas
        para escrituras que nada tienen que ver (cambiar el precio de un artículo, por
        ejemplo) y no depende de que el cálculo toque unas tablas concretas.

        🔴 Los ids se bloquean **ordenados**. Dos confirmaciones que compartan varios
        productos y los bloqueen en orden distinto se quedan esperándose la una a la otra
        para siempre.
        """
        ids = sorted(set(productos.ids))
        for producto_id in ids:
            self.env.cr.execute(
                'SELECT pg_advisory_xact_lock(%s, %s)',
                (ESPACIO_BLOQUEO_PRESTAMO, producto_id),
            )
