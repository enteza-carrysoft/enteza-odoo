{
    "name": "Enteza - Arrastrar socio en asientos varios",
    "version": "19.0.1.1.0",
    "summary": "Al añadir una línea nueva en un asiento manual, precarga el socio de la línea anterior",
    "category": "Accounting/Accounting",
    "author": "Enteza",
    "license": "LGPL-3",
    # Funcionalidad que existía en Odoo 15 y no tiene equivalente nativo en la 19: en un
    # asiento manual (move_type='entry') cada línea nace sin socio porque
    # account.move.line._compute_partner_id solo copia el de la cabecera del asiento
    # (account.move.partner_id), que en un asiento vario casi nunca se rellena.
    "depends": ["account"],
    "data": [],
    "installable": True,
    "application": False,
}
