#!/usr/bin/env python3
"""Cliente JSON-RPC autónomo contra la instancia Odoo 19 de Enteza (`enteza26`).

Solo biblioteca estándar: no hay que instalar nada ni hay proyecto Node en este repo.

Credenciales: se leen de las variables de entorno o de un `.env.local` en la raíz del
repositorio (que NO se commitea). Variables necesarias:

    ODOO19_URL=https://...
    ODOO19_DB=...
    ODOO19_USER=...
    ODOO19_API_KEY=...

🔴 `enteza26` es PRODUCCIÓN, con la contabilidad migrada y cuadrada al céntimo. Por eso
las operaciones de escritura exigen `--execute`: sin ese flag se muestra lo que se haría
y no se toca nada.

Uso:
    python odoo19.py fields <modelo> [--filtro texto]
    python odoo19.py search <modelo> <dominio-json> [campos] [--limit N] [--order X]
    python odoo19.py read   <modelo> <ids> [campos]
    python odoo19.py count  <modelo> [dominio-json]
    python odoo19.py exec   <modelo> <metodo> <args-json> [--execute]
    python odoo19.py create <modelo> <valores-json> [--execute]
    python odoo19.py write  <modelo> <ids> <valores-json> [--execute]

Ejemplos:
    python odoo19.py fields sale.order --filtro rental
    python odoo19.py search res.company '[]' id,name
    python odoo19.py count sale.order '[["is_rental_order","=",true]]'
    python odoo19.py search ir.module.module '[["state","=","installed"]]' name --limit 200
    python odoo19.py exec account.move action_post '[[123]]' --execute

Nota sobre `--company`: el código de cuenta contable y otros campos son
company-dependent en la 19. Pasa `--company 1` (Visueña) o `--company 2` (Stileum)
cuando leas o escribas ese tipo de campos.
"""

import argparse
import json
import os
import pathlib
import sys
import urllib.request

TIMEOUT = 120


def cargar_env():
    """Variables de entorno, y si faltan, `.env.local` de la raíz del repositorio."""
    raiz = pathlib.Path(__file__).resolve().parents[4]
    fichero = raiz / '.env.local'
    if fichero.exists():
        for linea in fichero.read_text(encoding='utf-8').splitlines():
            linea = linea.strip()
            if not linea or linea.startswith('#') or '=' not in linea:
                continue
            clave, valor = linea.split('=', 1)
            os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))

    faltan = [v for v in ('ODOO19_URL', 'ODOO19_DB', 'ODOO19_USER', 'ODOO19_API_KEY')
              if not os.environ.get(v)]
    if faltan:
        sys.exit(
            f"Faltan variables de entorno: {', '.join(faltan)}.\n"
            f"Créalas en {fichero} (ese fichero no se commitea)."
        )
    return (os.environ['ODOO19_URL'].rstrip('/'), os.environ['ODOO19_DB'],
            os.environ['ODOO19_USER'], os.environ['ODOO19_API_KEY'])


def rpc(url, servicio, metodo, args):
    peticion = urllib.request.Request(
        f'{url}/jsonrpc',
        data=json.dumps({
            'jsonrpc': '2.0',
            'method': 'call',
            'params': {'service': servicio, 'method': metodo, 'args': args},
        }).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(peticion, timeout=TIMEOUT) as respuesta:
        cuerpo = json.loads(respuesta.read().decode('utf-8'))

    if 'error' in cuerpo:
        error = cuerpo['error']
        datos = error.get('data', {})
        # El mensaje de Odoo casi siempre nombra el campo exacto que falla: merece la pena
        # sacarlo por delante en vez de enterrarlo en el traceback.
        print(f"ERROR: {datos.get('message') or error.get('message')}", file=sys.stderr)
        if datos.get('debug'):
            print(datos['debug'], file=sys.stderr)
        sys.exit(1)
    return cuerpo['result']


class Cliente:
    def __init__(self):
        self.url, self.db, usuario, self.clave = cargar_env()
        self.uid = rpc(self.url, 'common', 'login', [self.db, usuario, self.clave])
        if not self.uid:
            sys.exit('Autenticación rechazada: revisa ODOO19_USER / ODOO19_API_KEY.')

    def llamar(self, modelo, metodo, args, kwargs=None):
        return rpc(self.url, 'object', 'execute_kw',
                   [self.db, self.uid, self.clave, modelo, metodo, args, kwargs or {}])


def contexto(opciones):
    if opciones.company:
        return {'allowed_company_ids': [opciones.company], 'company_id': opciones.company}
    return {}


def mostrar(valor):
    print(json.dumps(valor, indent=2, ensure_ascii=False, default=str))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--company', type=int, help='Contexto de compañía (1 Visueña, 2 Stileum)')
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--order')
    parser.add_argument('--filtro', help='Solo en `fields`: filtra por nombre de campo')
    parser.add_argument('--execute', action='store_true',
                        help='Obligatorio para que una escritura ocurra de verdad')
    parser.add_argument('accion', choices=['fields', 'search', 'read', 'count',
                                           'exec', 'create', 'write'])
    parser.add_argument('resto', nargs='*')
    opciones = parser.parse_args()

    cliente = Cliente()
    accion, resto = opciones.accion, opciones.resto

    if accion == 'fields':
        modelo = resto[0]
        campos = cliente.llamar(modelo, 'fields_get', [],
                                {'attributes': ['string', 'type', 'store', 'relation', 'required']})
        if opciones.filtro:
            campos = {k: v for k, v in campos.items() if opciones.filtro.lower() in k.lower()}
        mostrar(dict(sorted(campos.items())))

    elif accion == 'search':
        modelo = resto[0]
        dominio = json.loads(resto[1]) if len(resto) > 1 else []
        campos = resto[2].split(',') if len(resto) > 2 else ['id', 'display_name']
        kwargs = {'fields': campos, 'limit': opciones.limit, 'context': contexto(opciones)}
        if opciones.order:
            kwargs['order'] = opciones.order
        mostrar(cliente.llamar(modelo, 'search_read', [dominio], kwargs))

    elif accion == 'read':
        modelo = resto[0]
        ids = [int(i) for i in resto[1].split(',')]
        campos = resto[2].split(',') if len(resto) > 2 else []
        mostrar(cliente.llamar(modelo, 'read', [ids, campos], {'context': contexto(opciones)}))

    elif accion == 'count':
        modelo = resto[0]
        dominio = json.loads(resto[1]) if len(resto) > 1 else []
        mostrar(cliente.llamar(modelo, 'search_count', [dominio], {'context': contexto(opciones)}))

    else:
        # Escrituras y ejecución de métodos: producción, así que nada sin --execute.
        if accion == 'exec':
            modelo, metodo, args = resto[0], resto[1], json.loads(resto[2])
        elif accion == 'create':
            modelo, metodo, args = resto[0], 'create', [json.loads(resto[1])]
        else:
            modelo, metodo = resto[0], 'write'
            args = [[int(i) for i in resto[1].split(',')], json.loads(resto[2])]

        if not opciones.execute:
            print('SIMULACIÓN (añade --execute para ejecutar de verdad):')
            mostrar({'modelo': modelo, 'metodo': metodo, 'args': args})
            return
        mostrar(cliente.llamar(modelo, metodo, args, {'context': contexto(opciones)}))


if __name__ == '__main__':
    main()
