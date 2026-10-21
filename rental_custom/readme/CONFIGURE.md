Para que un artículo se alquile por envases:

1. Activar **Unidades de medida y embalajes** (grupo `uom.group_uom`) si no lo está.
2. Crear la unidad «Envase de N» en Inventario → Configuración → Unidades de medida:
   `Unidad de referencia` = Units, `Contiene` = N (por ejemplo 25).
3. En la ficha del artículo, añadirla en «Envases».

Qué envases se ignoran: los de factor 1 o menor, los que tienen otra unidad de referencia
distinta de la unidad base del artículo y los encadenados. Si un artículo tiene dos envases
válidos (10 y 25) manda el **menor**.

Asignar un envase a un artículo no modifica sus líneas ya existentes.
