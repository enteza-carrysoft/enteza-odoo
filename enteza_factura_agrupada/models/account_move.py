# -*- coding: utf-8 -*-
"""Ayudas para el informe de factura agrupado por familia.

Nacen de dos peticiones de contabilidad (2026-08-03):

1. Las facturas de alquiler ocupan demasiados folios. La causa medida: en la factura
   AS/2026/01079 hay 60 líneas pero se imprimen 118 renglones, porque 57 de ellas llevan
   debajo el periodo de alquiler («del 30/07/2026 13:00 al 31/07/2026 13:00»), que es el
   mismo para toda la factura. Quitando ese renglón se pasa a 61: la mitad de papel.

2. Poder ver la factura agrupada por familia de producto (VAJILLAS, MANTELERÍAS, MENAJE…).

Los métodos son públicos a propósito: QWeb no puede llamar a métodos que empiezan por `_`.
"""
import re

from odoo import fields, models

# El periodo lo escribe `sale_renting` al facturar, en un renglón propio de la descripción.
# Se contemplan las dos formas que se han visto, en castellano y en inglés, y se exige que
# lleve fechas para no borrar por error una descripción que empiece por «del».
PATRON_PERIODO = re.compile(
    r"^\s*(del|from)\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}.*\s(al|to)\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}",
    re.IGNORECASE,
)


class AccountMove(models.Model):
    _inherit = "account.move"

    def enteza_familias_usadas(self):
        """Familias de producto presentes en la factura, en orden alfabético.

        Se usa para recorrerlas en el informe. Las líneas sin producto (o sin familia) se
        agrupan aparte con `enteza_lineas_sin_familia`, para que no se pierda ninguna.
        """
        self.ensure_one()
        familias = self.invoice_line_ids.filtered(
            lambda l: l.display_type == "product" and l.product_id.categ_id
        ).mapped("product_id.categ_id")
        return familias.sorted(key=lambda c: (c.complete_name or c.name or "").lower())

    def enteza_lineas_de_familia(self, familia):
        """Líneas de producto de una familia concreta, respetando el orden de la factura."""
        self.ensure_one()
        return self.invoice_line_ids.filtered(
            lambda l: l.display_type == "product" and l.product_id.categ_id == familia
        ).sorted(key=lambda l: (l.sequence, l.id))

    def enteza_lineas_sin_familia(self):
        """Líneas de producto que no tienen familia: se imprimen al final, sin encabezado."""
        self.ensure_one()
        return self.invoice_line_ids.filtered(
            lambda l: l.display_type == "product" and not l.product_id.categ_id
        ).sorted(key=lambda l: (l.sequence, l.id))

    def enteza_pedido_alquiler(self):
        """El pedido de alquiler de la factura, sólo si es UNO solo.

        Si la factura agrupa varios pedidos, se devuelve vacío y el periodo sigue saliendo en
        cada línea, que es lo correcto: no sería el mismo para todas.
        """
        self.ensure_one()
        pedidos = self.invoice_line_ids.sale_line_ids.order_id.filtered(
            lambda o: o.is_rental_order and o.rental_start_date and o.rental_return_date
        )
        return pedidos if len(pedidos) == 1 else pedidos.browse()

    def enteza_periodo_alquiler(self):
        """Periodo de alquiler como fechas SIN hora: `(desde, hasta)` o `(False, False)`.

        Contabilidad pidió que no salieran las horas (2026-08-03).

        La conversión de huso se hace aquí y no en la plantilla a propósito:
        `rental_start_date` se guarda en UTC (11:00) y en el papel debe verse la fecha local
        (13:00 del mismo día). Recortar la hora en la plantilla sobre el valor UTC daría el día
        equivocado en los alquileres que empiezan o terminan de madrugada.
        """
        self.ensure_one()
        pedido = self.enteza_pedido_alquiler()
        if not pedido:
            return (False, False)
        a_local = lambda dt: fields.Datetime.context_timestamp(self, dt).date()
        return (a_local(pedido.rental_start_date), a_local(pedido.rental_return_date))

    def enteza_fecha_evento(self):
        """Fecha del evento (`event_date`), si toda la factura comparte una.

        Sustituye a la fecha de vencimiento en el impreso (petición de contabilidad del
        2026-08-03): en este negocio la fecha que importa es el día del evento.

        Se lee de las líneas de pedido y no del pedido, porque `event_date` existe en los dos
        sitios y así también sale cuando la factura agrupa varios pedidos del mismo evento.
        Es un `date`, sin hora: no hay que convertir huso.
        """
        self.ensure_one()
        fechas = set(self.invoice_line_ids.sale_line_ids.mapped("event_date")) - {False}
        return fechas.pop() if len(fechas) == 1 else False


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def enteza_descripcion(self):
        """Descripción de la línea sin el renglón del periodo de alquiler.

        Sólo se quita cuando el periodo ya sale en la cabecera (`enteza_pedido_alquiler`); de
        eso se encarga la plantilla, aquí únicamente se limpia el texto. No se toca el dato
        guardado: es sólo lo que se imprime.
        """
        self.ensure_one()
        if not self.name:
            return ""
        renglones = [r for r in self.name.split("\n") if not PATRON_PERIODO.match(r)]
        return "\n".join(renglones).strip()
