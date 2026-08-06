# -*- coding: utf-8 -*-
"""Ayudas para el informe de factura agrupado por familia.

Nacen de dos peticiones de contabilidad (2026-08-03):

1. Las facturas de alquiler ocupan demasiados folios. La causa medida: en la factura
   AS/2026/01079 hay 60 líneas pero se imprimen 118 renglones, porque 57 de ellas llevan
   debajo el periodo de alquiler («del 30/07/2026 13:00 al 31/07/2026 13:00»), que es el
   mismo para toda la factura. Quitando ese renglón se pasa a 61: la mitad de papel.

2. Poder ver la factura agrupada por familia de producto (VAJILLAS, MANTELERÍAS, MENAJE…).

Y una tercera del 2026-08-04, tras ver el informe impreso: quitar la columna de impuestos de
las líneas —todo se vende al mismo tipo— y llevar el dato al pie de totales, agrupado por
porcentaje. De ahí `enteza_impuestos_agrupados`.

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

    def enteza_impuestos_agrupados(self):
        """Impuestos de la factura agrupados por porcentaje, para el pie de totales.

        Contabilidad pidió (2026-08-04) quitar la columna de impuestos de las líneas —aquí
        todo se vende al mismo tipo— y llevar el dato al pie, con el porcentaje y el importe.

        Se agrupa por **porcentaje**, no por impuesto: en esta instancia conviven «21% G» y
        «21% S», que son dos cuentas distintas para el mismo 21 %, y en el papel tienen que
        salir en un solo renglón. Comprobado sobre `AS/2026/00483`, la única factura del
        histórico que lleva los dos: 937,16 − 286,65 = 650,51, que es su `amount_tax`.

        Tampoco se agrupa por `tax_group_id`, aunque sería lo natural, porque los grupos de
        esta base se llaman «VAT 21%» y «Withholding 19%» —en inglés— y saldrían así impresos.

        Las retenciones no se mezclan con el IVA: tienen porcentaje negativo (−19 %), así que
        caen en su propio grupo. `LV/2026/00029` lo comprueba: 21 % → 160,94 y −19 % → −145,62,
        que suman los 15,32 de `amount_tax`.

        Devuelve una lista de diccionarios, de mayor a menor porcentaje::

            [{'porcentaje': 21.0, 'etiqueta': 'IVA 21%', 'base': 3097.66, 'importe': 650.51}]
        """
        self.ensure_one()
        grupos = {}

        def clave_de(impuesto):
            # `None` y no `False`: `False == 0.0` en Python, y un impuesto exento (0 %) se
            # mezclaría con los que no van por porcentaje al usarlos como clave del dict.
            return impuesto.amount if impuesto.amount_type == "percent" else None

        def grupo(clave, impuesto):
            g = grupos.setdefault(
                clave, {"porcentaje": clave, "base": 0.0, "importe": 0.0, "nombres": []}
            )
            if impuesto.name not in g["nombres"]:
                g["nombres"].append(impuesto.name)
            return g

        # Base: cada línea suma en el grupo de cada tipo que lleve. Si lleva dos impuestos del
        # mismo porcentaje suma una sola vez (de ahí `vistas`); si lleva IVA y retención suma
        # en los dos, que es lo correcto: las dos se calculan sobre la misma base.
        for linea in self.invoice_line_ids.filtered(lambda l: l.display_type == "product"):
            vistas = set()
            for impuesto in linea.tax_ids:
                clave = clave_de(impuesto)
                g = grupo(clave, impuesto)
                if clave not in vistas:
                    g["base"] += linea.price_subtotal
                    vistas.add(clave)

        # Importe: de las líneas de impuesto del asiento, no recalculado. Es el dato que ya
        # cuadró Odoo al validar. `direction_sign` (−1 en factura de cliente) las deja con el
        # mismo signo que `amount_total`.
        for linea in self.line_ids.filtered(
            lambda l: l.display_type == "tax" and l.tax_line_id
        ):
            g = grupo(clave_de(linea.tax_line_id), linea.tax_line_id)
            g["importe"] += self.direction_sign * linea.amount_currency

        resultado = [
            {
                "porcentaje": g["porcentaje"],
                "etiqueta": self._enteza_etiqueta_impuesto(g["porcentaje"], g["nombres"]),
                "base": self.currency_id.round(g["base"]),
                "importe": self.currency_id.round(g["importe"]),
            }
            for g in grupos.values()
        ]
        return sorted(
            resultado,
            key=lambda g: (
                g["porcentaje"] is None,
                -(g["porcentaje"] if g["porcentaje"] is not None else 0.0),
            ),
        )

    def _enteza_etiqueta_impuesto(self, porcentaje, nombres):
        """Nombre legible de un grupo de impuestos: «IVA 21 %», «Retención 19 %»…

        Privado a propósito: sólo lo llama `enteza_impuestos_agrupados`, no la plantilla.

        Los impuestos que no van por porcentaje (ninguno en esta base hoy) se quedan con su
        propio nombre, que es mejor que inventarles una etiqueta.
        """
        if porcentaje is None:
            return ", ".join(nombres)
        texto = ("%g" % abs(porcentaje)).replace(".", ",")
        if porcentaje < 0:
            return "Retención %s %%" % texto
        if not porcentaje:
            return "Exento (0 %)"
        return "IVA %s %%" % texto

    def enteza_fecha_evento(self):
        """Fecha del evento (`event_date`), si toda la factura comparte una.

        En este negocio la fecha que importa es el día del evento (petición de contabilidad del
        2026-08-03), así que se imprime junto al periodo de alquiler.

        Se lee del **pedido** y no de la línea: `sale.order.line.event_date` existe, pero es un
        related de `order_id.event_date` con `store=False`, de modo que el valor bueno está en
        la cabecera y leerlo ahí evita calcularlo línea a línea. Sigue funcionando cuando la
        factura agrupa varios pedidos del mismo evento, porque se comparan todos.

        Es un `date`, sin hora: aquí no hay huso que convertir.

        Devuelve `False` si ningún pedido la tiene informada — pasa en pedidos donde no se
        rellenó (2 de los 1.159 a 2026-08-03) — o si hay varias fechas distintas, porque
        entonces no habría una sola fecha cierta para toda la factura.
        """
        self.ensure_one()
        fechas = set(self.invoice_line_ids.sale_line_ids.order_id.mapped("event_date")) - {False}
        return fechas.pop() if len(fechas) == 1 else False


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def enteza_descripcion(self):
        """Descripción de la línea, limpiando el periodo de alquiler cuando sea común a toda la factura.

        El periodo de alquiler se imprime en cada línea cuando la factura agrupa varios pedidos
        con periodos distintos; cuando toda la factura proviene de un único pedido de alquiler,
        el periodo ya no se imprime en ningún sitio para ganar espacio. No se toca el dato
        guardado: es sólo lo que se imprime.
        """
        self.ensure_one()
        if not self.name:
            return ""
        renglones = self.name.split("\n")
        if self.move_id.enteza_pedido_alquiler():
            renglones = [r for r in renglones if not PATRON_PERIODO.match(r)]
        return "\n".join(renglones).strip()
