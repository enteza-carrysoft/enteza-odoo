# Cuentas e impuestos específicos para alquiler — Odoo 19

Módulo técnico: `sale_rental_income_account`

## Función

Un mismo artículo puede alquilarse y venderse, pero contablemente no son la misma
operación: el alquiler es un servicio y la venta de material roto o no devuelto es
una venta de mercancía, con su propia cuenta de ingresos y su propio tipo de IVA.

El módulo permite definir esa doble configuración y la resuelve **línea a línea**
al facturar.

## Cómo se resuelve cada línea

| Línea | Cuenta de ingresos | Impuestos |
|---|---|---|
| **Alquiler** | producto → categoría → cuenta de venta estándar | producto → categoría → impuestos de venta |
| **Venta** | producto → categoría *(nativo de Odoo)* | producto → categoría |

La distinción se hace con `sale.order.line.is_rental`, es decir **por línea y no por
pedido**. Un pedido de alquiler que incluya una línea de venta de material roto
factura esa línea con la cuenta y el IVA de venta.

En todos los casos, la posición fiscal del pedido se aplica al final sobre la cuenta
(`map_account`) y sobre los impuestos (`map_tax`), igual que hace Odoo nativo.

## Requisitos

- Odoo 19 Enterprise.
- Aplicaciones `account`, `sale_management` y `sale_renting` instaladas.
- Plan contable cargado en cada compañía.

## Instalación

1. Copiar la carpeta `sale_rental_income_account` dentro de un directorio incluido en `addons_path`.
2. Reiniciar Odoo.
3. Actualizar la lista de aplicaciones.
4. Buscar «Cuentas e impuestos específicos para alquiler».
5. Instalar el módulo.

Por terminal:

```bash
./odoo-bin -d NOMBRE_BD -i sale_rental_income_account --stop-after-init
```

Actualización desde la versión 19.0.1.0.0:

```bash
./odoo-bin -d NOMBRE_BD -u sale_rental_income_account --stop-after-init
```

## Configuración

### Categoría de producto (recomendado)

**Inventario → Configuración → Categorías de productos**, apartado *Configuración
fiscal por tipo de operación*:

- **Venta**: impuestos de venta. La cuenta de ingresos de venta sigue siendo el
  campo estándar de la categoría.
- **Alquiler**: cuenta de ingresos por alquiler e impuestos de alquiler.

Con un único artículo por familia ya no hacen falta categorías separadas de tipo
«Alquiler Cristalería»: la categoría «Cristalería» contiene ambas configuraciones.

### Producto (excepciones)

**Alquiler/Ventas → Productos**, pestaña *Contabilidad de alquiler*: cuenta e
impuestos de alquiler propios del artículo. Si se dejan vacíos se hereda la
categoría.

Las cuentas son dependientes de compañía: hay que configurarlas en cada compañía.

## Reglas

- Línea de alquiler: cuenta e impuestos de alquiler.
- Línea de venta: comportamiento estándar de Odoo, más el respaldo de impuestos
  de la categoría.
- Campo del producto vacío: se hereda de la categoría.
- Categoría vacía: se usa la configuración de venta estándar.
- Posición fiscal: se aplica sobre cuentas e impuestos ya resueltos.
- Secciones, notas, anticipos y líneas sin producto: comportamiento estándar.
- Abonos creados desde la factura: conservan la cuenta de la factura original.

## Nota sobre el IVA de venta

Odoo rellena automáticamente el campo *Impuestos de cliente* del producto con el
IVA de venta de la compañía al crear el artículo. El respaldo a la categoría solo
actúa cuando ese campo está **vacío**, así que en los artículos que deban heredar
el IVA de su categoría hay que vaciarlo (puede hacerse de forma masiva desde la
vista de lista de productos).

## Pruebas

```bash
./odoo-bin -d BD_PRUEBAS \
  -i sale_rental_income_account \
  --test-enable \
  --test-tags /sale_rental_income_account \
  --stop-after-init
```

## Desinstalación

Desinstalar desde Aplicaciones. Los campos desaparecen y Odoo vuelve a usar
exclusivamente la configuración estándar. Las facturas ya creadas conservan sus
cuentas e impuestos.

## Advertencia

Probar primero en una copia de la base de datos. La configuración debe validarse
con el responsable contable antes de emitir facturas reales.
