from odoo import _, api, fields, models
from odoo.tools import format_date

# Cada modo del panel imprime el mismo parte con otro título: lo que cambia es qué pedidos
# entran, y eso ya lo decidió `sale.order.enteza_panel_imprimir` al elegir los docids.
TITULOS = {
    'evento': lambda: _("Eventos del día"),
    'salida': lambda: _("Material que sale del almacén"),
    'devolucion': lambda: _("Material que vuelve al almacén"),
}


class ParteDia(models.AbstractModel):
    """Parte del día: la hoja de carga que baja al almacén en papel.

    El nombre del modelo tiene que ser `report.` + el `report_name` de la acción: es como
    Odoo lo encuentra al renderizar.
    """

    _name = 'report.enteza_panel_eventos.parte_dia'
    _description = 'Parte del día para el almacén'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        modo = data.get('modo') or 'evento'
        dia = data.get('dia')
        solo_sobreventa = data.get('solo_sobreventa')
        solo_confirmados = bool(data.get('solo_confirmados'))

        # 🔴 Aquí `docids` llega vacío casi siempre, y no es un error: cuando la acción lleva
        # `data`, el cliente web construye la URL como
        # `/report/pdf/<informe>?options=...&context=...` y **deja los docids fuera de la
        # ruta** (`getReportUrl` en `web/static/src/webclient/actions/reports/utils.js`, 19.0).
        # Verificado leyendo ese fichero. Como el parte queda determinado por el día y el
        # modo, se recalculan los pedidos y así el papel no puede discrepar de la pantalla.
        pedidos = self.env['sale.order']
        if dia:
            pedidos = pedidos._enteza_panel_pedidos(
                dia, pedidos._enteza_panel_modo(modo), solo_confirmados
            )
        if not pedidos:
            ids = docids or (data.get('context') or {}).get('active_ids') or []
            pedidos = self.env['sale.order'].browse(ids)

        # Se reutilizan los mismos formateadores que alimentan el panel en pantalla: el
        # papel y la pantalla no deben poder discrepar.
        articulos = pedidos._enteza_panel_datos_articulos(dia)
        if solo_sobreventa:
            articulos = [articulo for articulo in articulos if articulo['sobreventa']]

        # La columna de almacén solo sale si el día mezcla varios: con uno solo repetiría el
        # mismo valor en todas las filas y estrecharía las que sí cambian. Se mira en los
        # pedidos y no en `articulos`, que puede venir recortado por «Sobre venta»: si no,
        # la columna aparecería o desaparecería según lo que se estuviera imprimiendo.
        almacenes = pedidos.warehouse_id

        return {
            'doc_ids': pedidos.ids,
            'doc_model': 'sale.order',
            'docs': pedidos,
            # `web.external_layout` busca la compañía en varios sitios; dársela hecha evita
            # depender de cuál de esos caminos acabe tomando.
            'company': self.env.company,
            'titulo': TITULOS.get(modo, TITULOS['evento'])(),
            'fecha': format_date(self.env, fields.Date.to_date(dia)) if dia else '',
            'solo_sobreventa': bool(solo_sobreventa),
            'solo_confirmados': solo_confirmados,
            'articulos': articulos,
            'mostrar_almacen': len(almacenes) > 1,
            'pedidos': pedidos._enteza_panel_datos_pedidos(),
            'total_unidades': sum(articulo['unidades'] for articulo in articulos),
        }
