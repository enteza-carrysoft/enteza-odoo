# Cuenta de ingresos específica para alquiler — Odoo 19

Módulo técnico: `sale_rental_income_account`

## Función

Añade al producto el campo **Cuenta de ingresos por alquiler**. Cuando una factura se genera desde un pedido marcado por Odoo como alquiler, la línea utiliza esa cuenta. En pedidos de venta normales se conserva la cuenta estándar del producto/categoría.

La posición fiscal del pedido se aplica también sobre la cuenta de alquiler.

## Requisitos

- Odoo 19 Enterprise.
- Aplicaciones `account`, `sale_management` y `sale_renting` instaladas.
- Plan contable cargado en cada compañía.

## Instalación

1. Copiar la carpeta `sale_rental_income_account` dentro de un directorio incluido en `addons_path`.
2. Reiniciar Odoo.
3. Actualizar la lista de aplicaciones.
4. Buscar «Cuenta de ingresos específica para alquiler».
5. Instalar el módulo.

Por terminal:

```bash
./odoo-bin -d NOMBRE_BD -i sale_rental_income_account --stop-after-init
```

En Docker/Doodba:

```bash
odoo -d NOMBRE_BD -i sale_rental_income_account --stop-after-init
```

## Configuración

1. Abrir **Alquiler/Ventas → Productos**.
2. Entrar en el producto.
3. Abrir la pestaña **Contabilidad de alquiler**.
4. Seleccionar la cuenta de ingresos por alquiler.

El campo es dependiente de compañía. Cambie a cada compañía y configure la cuenta correspondiente.

## Reglas

- Pedido de venta normal: cuenta de ingresos estándar.
- Pedido de alquiler: cuenta de ingresos por alquiler.
- Cuenta de alquiler vacía: cuenta estándar como respaldo.
- Posición fiscal: puede mapear la cuenta de alquiler.
- Secciones, notas y líneas sin producto: comportamiento estándar.
- Abonos creados desde la factura: conservan la cuenta de la factura original.

## Pruebas

```bash
./odoo-bin -d BD_PRUEBAS \
  -i sale_rental_income_account \
  --test-enable \
  --test-tags /sale_rental_income_account \
  --stop-after-init
```

## Desinstalación

Desinstalar desde Aplicaciones. El campo desaparece y Odoo vuelve a usar exclusivamente la cuenta estándar. Las facturas ya creadas conservan sus cuentas contables.

## Advertencia

Probar primero en una copia de la base de datos. La cuenta debe configurarse por compañía y validarse con el responsable contable antes de emitir facturas reales.
