"""Valida las vistas de un módulo contra el esquema RELAX NG real de Odoo 19.

Por qué existe
--------------
En este hosting no hay `odoo-bin --test-enable` ni instancia de pruebas, así que lo normal
es entregar módulos "validados por sintaxis, no ejecutados". Pero una parte del rechazo de
vistas de Odoo **sí se puede reproducir aquí**: la validación por esquema.

`odoo/tools/view_validation.py` valida por RELAX NG las vistas de tipo
`calendar, graph, pivot, search, list, activity` (los **formularios no**, de ahí que un
`<group string="...">` cuele en un form y reviente en un search). Cuando falla, el servidor
solo devuelve *«Vista no disponible <nombre> definición en <fichero>»* y manda el detalle al
log, al que no tenemos acceso: se pierde un ciclo entero de `git pull` + Actualizar para
descubrir un atributo mal puesto.

Este script hace en local exactamente esa comprobación y dice qué atributo es.

Uso
---
    python .claude/skills/odoo19-dev/scripts/validar_vistas.py enteza_mi_modulo/views/*.xml
    python .claude/skills/odoo19-dev/scripts/validar_vistas.py enteza_mi_modulo

Con una carpeta, valida todos los `.xml` que cuelguen de ella.

Devuelve 0 si todo pasa y 1 si algo falla, para poder encadenarlo.

Requisitos
----------
`lxml` (`python -m pip install lxml`). Los esquemas se descargan de Odoo Community 19.0 la
primera vez y se cachean en el directorio temporal del sistema.

Lo que NO cubre
---------------
Solo el esquema. NO comprueba que los campos existan en el modelo, ni los dominios, ni las
referencias externas, que es lo que hace el servidor después. Que esto pase no garantiza que
el módulo instale; que falle garantiza que no.
"""

import os
import sys
import tempfile
import urllib.request

try:
    from lxml import etree
except ImportError:
    sys.exit('Falta lxml. Instalar con:  python -m pip install lxml')

URL_BASE = 'https://raw.githubusercontent.com/odoo/odoo/19.0/odoo/addons/base/rng/'

# Los tipos que Odoo valida por esquema, tal cual el decorador de
# `view_validation.schema_valid`. Los formularios no están y no es un olvido.
VALIDADOS = ('calendar', 'graph', 'pivot', 'search', 'list', 'activity')

CACHE = os.path.join(tempfile.gettempdir(), 'odoo19_rng')

_cache_validadores = {}


def _descargar(nombre):
    """Descarga un .rng al caché si no está ya. Devuelve la ruta local."""
    destino = os.path.join(CACHE, nombre)
    if os.path.exists(destino) and os.path.getsize(destino) > 200:
        return destino
    os.makedirs(CACHE, exist_ok=True)
    with urllib.request.urlopen(URL_BASE + nombre, timeout=60) as respuesta:
        contenido = respuesta.read()
    with open(destino, 'wb') as fichero:
        fichero.write(contenido)
    return destino


def validador(tipo):
    """Devuelve el validador RELAX NG de un tipo de vista, o None si no se valida."""
    if tipo not in _cache_validadores:
        if tipo not in VALIDADOS:
            _cache_validadores[tipo] = None
        else:
            # `common.rng` tiene que estar junto al esquema: los .rng lo incluyen por
            # ruta relativa.
            _descargar('common.rng')
            ruta = _descargar('%s_view.rng' % tipo)
            _cache_validadores[tipo] = etree.RelaxNG(etree.parse(ruta))
    return _cache_validadores[tipo]


def _ficheros(rutas):
    for ruta in rutas:
        if os.path.isdir(ruta):
            for raiz, _dirs, nombres in os.walk(ruta):
                for nombre in sorted(nombres):
                    if nombre.endswith('.xml'):
                        yield os.path.join(raiz, nombre)
        else:
            yield ruta


def validar(ruta):
    """Valida un fichero XML de datos. Devuelve el número de vistas que fallan."""
    arbol = etree.parse(ruta)
    fallos = 0
    encontradas = 0
    for campo in arbol.iter('field'):
        # Las vistas viven en <field name="arch" type="xml"> dentro de un ir.ui.view.
        if campo.get('name') != 'arch' or campo.get('type') != 'xml':
            continue
        for raiz in campo:
            if not isinstance(raiz.tag, str):
                continue  # comentarios XML
            encontradas += 1
            comprobador = validador(raiz.tag)
            if comprobador is None:
                print('  omitida  <%s> línea %s (Odoo no valida este tipo por esquema)'
                      % (raiz.tag, raiz.sourceline))
                continue
            if comprobador.validate(raiz):
                print('  OK       <%s> línea %s' % (raiz.tag, raiz.sourceline))
            else:
                fallos += 1
                print('  FALLA    <%s> línea %s' % (raiz.tag, raiz.sourceline))
                for error in comprobador.error_log:
                    print('           línea %s: %s' % (error.line, error.message))
    if not encontradas:
        print('  (sin vistas)')
    return fallos


def main(argv):
    if not argv:
        sys.exit(__doc__)
    fallos = 0
    for ruta in _ficheros(argv):
        print(ruta)
        try:
            fallos += validar(ruta)
        except etree.XMLSyntaxError as error:
            fallos += 1
            print('  XML MAL FORMADO: %s' % error)
    print()
    print('Sin fallos de esquema.' if not fallos else '%s vista(s) con fallos.' % fallos)
    return 1 if fallos else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
