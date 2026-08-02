"""Busca ficheros de un módulo que Odoo NUNCA va a cargar.

Por qué existe
--------------
Son fallos **silenciosos**: el módulo instala con normalidad, no hay error en ningún log y
todo lo demás funciona. Simplemente una parte del código no existe. Se descubren cuando
alguien prueba la funcionalidad y «no pasa nada», que aquí cuesta un ciclo entero de
`git pull` + Actualizar.

Comprueba tres cosas:

1. **Módulos Python no importados.** Un `models/mi_modelo.py` que no está en
   `models/__init__.py` no se carga. Pasó el 2026-08-02 en
   `enteza_prestamo_intercompania`: el `action_confirm` que abría el diálogo de préstamo
   nunca llegó a registrarse, y el módulo instalaba perfectamente.
2. **Paquetes no importados** desde el `__init__.py` de la raíz (`wizard`, `report`…).
3. **Ficheros de datos** declarados en el manifiesto que no existen, y ficheros `.xml`/`.csv`
   que están en disco pero **no** declarados, que es la otra mitad del mismo problema.

Uso
---
    python .claude/skills/odoo19-dev/scripts/validar_modulo.py enteza_mi_modulo
    python .claude/skills/odoo19-dev/scripts/validar_modulo.py            # todos los del repo

Devuelve 0 si está todo bien y 1 si hay algo que Odoo no va a cargar.
"""

import ast
import os
import re
import sys

# Carpetas que Odoo carga como paquetes Python de un módulo.
PAQUETES = ('models', 'wizard', 'wizards', 'report', 'reports', 'controllers')
# Carpetas donde suelen vivir los ficheros declarados en `data`.
DATOS = ('views', 'security', 'data', 'wizard', 'wizards', 'report', 'reports')


def _importados(ruta_init):
    """Nombres que un `__init__.py` importa con `from . import X`."""
    if not os.path.exists(ruta_init):
        return None
    with open(ruta_init, encoding='utf-8') as fichero:
        arbol = ast.parse(fichero.read())
    nombres = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom) and nodo.level == 1 and nodo.module is None:
            nombres.update(alias.name for alias in nodo.names)
    return nombres


def _manifiesto(carpeta):
    ruta = os.path.join(carpeta, '__manifest__.py')
    if not os.path.exists(ruta):
        return None
    with open(ruta, encoding='utf-8') as fichero:
        try:
            return ast.literal_eval(fichero.read())
        except (ValueError, SyntaxError) as error:
            print('  MANIFIESTO ILEGIBLE: %s' % error)
            return {}


def revisar(carpeta):
    fallos = []
    avisos = []
    nombre = os.path.basename(carpeta.rstrip('/\\'))
    manifiesto = _manifiesto(carpeta)
    if manifiesto is None:
        return [], []

    # 1 y 2 · imports de Python
    raiz = _importados(os.path.join(carpeta, '__init__.py'))
    if raiz is None:
        fallos.append('falta __init__.py en la raíz del módulo')
        raiz = set()

    for paquete in PAQUETES:
        ruta_paquete = os.path.join(carpeta, paquete)
        if not os.path.isdir(ruta_paquete):
            continue
        if paquete not in raiz:
            fallos.append('el paquete «%s/» no se importa desde __init__.py' % paquete)
            continue
        dentro = _importados(os.path.join(ruta_paquete, '__init__.py'))
        if dentro is None:
            fallos.append('falta %s/__init__.py' % paquete)
            continue
        for fichero in sorted(os.listdir(ruta_paquete)):
            if not fichero.endswith('.py') or fichero == '__init__.py':
                continue
            modulo = fichero[:-3]
            if modulo not in dentro:
                fallos.append(
                    '%s/%s NO se importa: Odoo no lo carga y no avisa' % (paquete, fichero)
                )

    # 3 · ficheros de datos
    declarados = list(manifiesto.get('data', [])) + list(manifiesto.get('demo', []))
    for relativa in declarados:
        if not os.path.exists(os.path.join(carpeta, relativa)):
            fallos.append('el manifiesto declara «%s» y no existe' % relativa)

    declarados_norm = {d.replace('\\', '/') for d in declarados}
    for subcarpeta in DATOS:
        ruta_sub = os.path.join(carpeta, subcarpeta)
        if not os.path.isdir(ruta_sub):
            continue
        for fichero in sorted(os.listdir(ruta_sub)):
            if not fichero.endswith(('.xml', '.csv')):
                continue
            relativa = '%s/%s' % (subcarpeta, fichero)
            if relativa not in declarados_norm:
                # Solo aviso: a veces se deja un fichero desactivado a propósito, comentado
                # en el manifiesto. Decirlo sirve; darlo por roto, no.
                avisos.append(
                    '%s existe y no está en el manifiesto: no se cargará '
                    '(¿desactivado a propósito?)' % relativa
                )

    if fallos or avisos:
        print('%s' % nombre)
        for fallo in fallos:
            print('  FALLA  %s' % fallo)
        for aviso in avisos:
            print('  aviso  %s' % aviso)
    return fallos, avisos


def main(argv):
    if argv:
        carpetas = argv
    else:
        carpetas = [
            entrada for entrada in sorted(os.listdir('.'))
            if os.path.isfile(os.path.join(entrada, '__manifest__.py'))
        ]
    fallos = avisos = 0
    for carpeta in carpetas:
        f, a = revisar(carpeta)
        fallos += len(f)
        avisos += len(a)
    print()
    if avisos:
        print('%s aviso(s): ficheros de datos sin declarar. Puede ser intencionado.' % avisos)
    if fallos:
        print('%s FALLO(S). Hay código que Odoo no va a cargar y no lo dirá.' % fallos)
        return 1
    print('Todo el código del módulo se carga.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
