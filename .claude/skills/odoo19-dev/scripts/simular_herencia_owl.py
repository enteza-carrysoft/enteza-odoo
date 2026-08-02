"""Comprueba en local que un `t-inherit` de plantilla OWL va a encontrar su sitio.

Por qué existe
--------------
Cuando un `t-inherit` no encuentra su `xpath`, **se cae el bundle de assets entero** y el
síntoma es un backend en blanco, sin nada en el log del servidor y sin forma de saber qué
plantilla lo provocó. En este hosting eso cuesta un ciclo completo de `git pull` + Actualizar
para descubrirlo, y otro para arreglarlo.

Este script aplica la cadena de herencia con la misma mecánica que
`odoo.tools.template_inheritance` (localizar por xpath y aplicar la posición) y dice si el
nodo existe, cuántos coinciden y cómo queda el resultado. Además comprueba la **raíz única**
que exige OWL, que es el otro fallo silencioso del mismo terreno.

El problema de las plantillas de Enterprise, y cómo se resuelve
---------------------------------------------------------------
Para heredar de `sale_stock_renting`, `web_gantt` o cualquier módulo Enterprise hace falta su
plantilla **de la 19**, y ese código no es público. Pero **la instancia lo sirve**: los
bundles de assets llevan las plantillas dentro, así que se pueden leer de `enteza26` con
`--del-bundle`. Es la única forma verificada de leer código Enterprise de la 19.

Uso
---
    # 1) Plantilla base de Community, 2) extensión de Enterprise sacada de la instancia,
    # 3) la nuestra.
    python .claude/skills/odoo19-dev/scripts/simular_herencia_owl.py \\
        --base sale_stock.QtyAtDatePopover \\
        --del-bundle sale_stock_renting.QtyAtDatePopover \\
        mi_modulo/static/src/widgets/mi_widget.xml

`--base` se descarga de Community 19.0 si se le da `modulo.Plantilla` y se sabe la ruta, o se
pasa un fichero local con `--base-fichero`. Las plantillas que se pasen sueltas como
argumentos se leen de ficheros del repositorio, en orden.

Requisitos: `lxml`, y `.env.local` con las credenciales si se usa `--del-bundle`.
"""

import argparse
import copy
import os
import sys
import tempfile
import urllib.request

try:
    from lxml import etree
except ImportError:
    sys.exit('Falta lxml. Instalar con:  python -m pip install lxml')

CACHE = os.path.join(tempfile.gettempdir(), 'odoo19_assets')


# ----------------------------------------------------------------------
# Leer plantillas del bundle vivo de la instancia (la vía para Enterprise)
# ----------------------------------------------------------------------

def bajar_bundle(nombre='web.assets_web.min.js'):
    """Descarga el bundle de assets de la instancia y lo cachea.

    Dos detalles que cuestan un rato averiguar:

    - La URL lleva un **hash de versión que cambia** cada vez que Odoo regenera los assets,
      así que hay que preguntarla por RPC (`ir.attachment.url`) en vez de fijarla.
    - Hay que decirle **qué base de datos** es con la cabecera `X-Odoo-Database`. Sin ella el
      servidor responde 404 «No database is selected», que parece que la URL está mal.
    """
    destino = os.path.join(CACHE, nombre)
    if os.path.exists(destino) and os.path.getsize(destino) > 100000:
        return destino

    # Import diferido: solo hace falta en esta rama, y así el script sirve con ficheros
    # locales aunque no haya credenciales.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import odoo19  # noqa: E402

    cliente = odoo19.Cliente()
    adjuntos = cliente.llamar('ir.attachment', 'search_read',
                              [[('name', '=', nombre)]], {'fields': ['url']})
    if not adjuntos:
        sys.exit('No existe el bundle %r en la instancia.' % nombre)

    os.makedirs(CACHE, exist_ok=True)
    peticion = urllib.request.Request(
        cliente.url + adjuntos[0]['url'], headers={'X-Odoo-Database': cliente.db},
    )
    with urllib.request.urlopen(peticion, timeout=300) as respuesta:
        contenido = respuesta.read()
    with open(destino, 'wb') as fichero:
        fichero.write(contenido)
    return destino


def plantilla_del_bundle(nombre_plantilla):
    """Saca una plantilla del bundle por su `t-name` y la devuelve como elemento."""
    ruta = bajar_bundle()
    with open(ruta, encoding='utf-8', errors='replace') as fichero:
        datos = fichero.read()
    marca = '<t t-name="%s"' % nombre_plantilla
    inicio = datos.find(marca)
    if inicio < 0:
        sys.exit('La plantilla %r no está en el bundle.' % nombre_plantilla)
    # Las plantillas van dentro de un literal de JS delimitado por comillas invertidas.
    fin = datos.find('`)', inicio)
    fragmento = (datos[inicio:fin]
                 .replace('\\n', '\n').replace('\\t', '    ').replace("\\'", "'")
                 .rstrip())
    envuelto = ('<?xml version="1.0" encoding="UTF-8" ?><template>%s</template>' % fragmento)
    return etree.fromstring(envuelto.encode('utf-8'))[0]


# ----------------------------------------------------------------------
# Herencia
# ----------------------------------------------------------------------

def plantilla_de_fichero(ruta, nombre=None):
    raiz = etree.parse(ruta).getroot()
    for nodo in raiz:
        if not isinstance(nodo.tag, str):
            continue
        if nombre is None or nodo.get('t-name') == nombre:
            return nodo
    sys.exit('No se encuentra la plantilla %r en %s' % (nombre, ruta))


def aplicar(base, extension):
    for spec in extension:
        if not isinstance(spec.tag, str):
            continue
        if spec.tag != 'xpath':
            sys.exit('Solo se simulan specs <xpath>; encontrado <%s>.' % spec.tag)
        expr = spec.get('expr')
        posicion = spec.get('position', 'inside')
        coincidencias = base.xpath(expr)
        if not coincidencias:
            print('  FALLA  xpath %r no encuentra ningún nodo' % expr)
            return None
        destino = coincidencias[0]
        print('  OK     xpath %-34r -> <%s> (%s coincidencia/s), position=%s'
              % (expr, destino.tag, len(coincidencias), posicion))

        hijos = [copy.deepcopy(hijo) for hijo in spec]
        if posicion == 'attributes':
            for atributo in spec:
                destino.set(atributo.get('name'), (atributo.text or '').strip())
        elif posicion == 'inside':
            destino.extend(hijos)
        elif posicion in ('after', 'before', 'replace'):
            padre = destino.getparent()
            indice = list(padre).index(destino)
            desplazamiento = 1 if posicion == 'after' else 0
            if posicion == 'replace':
                padre.remove(destino)
            for salto, hijo in enumerate(hijos):
                padre.insert(indice + desplazamiento + salto, hijo)
        else:
            sys.exit('position desconocida: %s' % posicion)
    return base


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('extensiones', nargs='*',
                        help='Ficheros XML propios con las plantillas que heredan, en orden.')
    parser.add_argument('--base', help='t-name de la plantilla base (se busca en el bundle).')
    parser.add_argument('--base-fichero', help='Fichero local con la plantilla base.')
    parser.add_argument('--del-bundle', action='append', default=[],
                        help='t-name de una extensión intermedia a sacar del bundle vivo '
                             '(las de Enterprise). Se aplican antes que las locales.')
    args = parser.parse_args()

    if args.base_fichero:
        base = plantilla_de_fichero(args.base_fichero, args.base)
    elif args.base:
        base = plantilla_del_bundle(args.base)
    else:
        sys.exit('Hace falta --base o --base-fichero.')

    print('Base: %s' % (args.base or args.base_fichero))
    for nombre in args.del_bundle:
        print('Extensión (bundle): %s' % nombre)
        base = aplicar(base, plantilla_del_bundle(nombre))
        if base is None:
            return 1
    for ruta in args.extensiones:
        print('Extensión (local): %s' % ruta)
        base = aplicar(base, plantilla_de_fichero(ruta))
        if base is None:
            return 1

    raices = [hijo for hijo in base if isinstance(hijo.tag, str)]
    print()
    print('Raíces del componente tras heredar: %s' % len(raices))
    if len(raices) > 1:
        etiquetas = [
            '<%s%s>' % (hijo.tag,
                        ' t-if' if hijo.get('t-if') is not None else
                        ' t-else' if hijo.get('t-else') is not None else
                        ' t-elif' if hijo.get('t-elif') is not None else '')
            for hijo in raices
        ]
        print('  %s' % ' '.join(etiquetas))
        condicionales = all(
            hijo.get('t-if') is not None or hijo.get('t-else') is not None
            or hijo.get('t-elif') is not None for hijo in raices
        )
        if not condicionales:
            print('  🔴 OWL exige RAÍZ ÚNICA. Varias raíces solo valen si son t-if/t-elif/'
                  't-else y solo se pinta una. Esto reventaría el componente.')
            return 1
        print('  Todas condicionales: correcto, solo se pinta una.')
    print()
    print('La cadena de herencia se resuelve.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
