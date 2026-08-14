# Company Top Color — Odoo 19

Módulo ligero para identificar visualmente la empresa activa sin modificar
el modo Light/Dark elegido por cada usuario.

## Funcionamiento

- Añade `Identification color` a `res.company`.
- Usa el selector de colores estándar de Odoo.
- Al cargar el backend muestra una franja fija de 5 px en la parte superior.
- El color corresponde a la empresa principal/activa del contexto.
- No modifica `color_scheme`, cookies de apariencia ni los assets de Dark Mode.
- Si el color es 0, no se muestra ninguna franja visible.

## Instalación

1. Reiniciar Odoo tras incorporar el addon.
2. Actualizar la lista de aplicaciones.
3. Instalar **Company Top Color**.
4. Ir a Ajustes > Usuarios y compañías > Compañías.
5. Abrir cada empresa y elegir `Identification color`.

## Rendimiento

El módulo añade un asset JS/CSS muy pequeño y realiza una única lectura de
`res.company` al arrancar el webclient. No ejecuta polling, cron ni consultas
continuas.

## Compatibilidad

Diseñado para Odoo 19. No sustituye el tema y no depende del modo claro/oscuro.
