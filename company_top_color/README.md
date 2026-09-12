# Company Top Color — Odoo 19

Franja de color fija en el borde superior del backend para saber de un vistazo en qué
compañía se está trabajando. No toca el modo Claro/Oscuro de cada usuario.

## Funcionamiento

- Reutiliza el campo **nativo** `res.company.color`, que ya trae su selector en el
  formulario estándar de la compañía (*Ajustes › Usuarios y compañías › Compañías*,
  pestaña *Información general*, campo **Color**). El módulo **no añade ningún campo**.
- Al arrancar el cliente web lee ese color y lo escribe como `data-company-color` en
  `<html>`; el SCSS pinta la franja de 5 px con la paleta de la lista de colores de
  Odoo 19, de modo que coincide con el color que se ve en el selector.
- Si la compañía no tiene color (índice 0), no se pinta nada.
- El color es el de la **compañía activa principal** (`user.activeCompany`). Al cambiar de
  compañía Odoo recarga la página, así que la franja se actualiza sola.
- **Si hay 2 o más compañías seleccionadas a la vez** (`user.activeCompanies.length > 1`),
  la franja se pinta **en rojo fijo**, sin mirar el color de ninguna compañía en concreto.
  Confirmar una selección múltiple en el selector de compañías recarga la página (lo hace el
  propio `CompanySelector.apply()` del core de Odoo), así que este caso también se
  actualiza solo.
- No modifica `color_scheme`, ni cookies de apariencia, ni los assets del modo oscuro.

En `enteza` las dos compañías ya tienen color asignado (Visueña = 1 rojo, Stileum = 2
naranja), así que el módulo funciona sin configurar nada.

## Instalación

1. `git pull` en la instancia.
2. Aplicaciones → *Actualizar lista de aplicaciones*.
3. Instalar **Company Top Color**.
4. `Ctrl+F5` en el navegador: el bundle de assets se cachea y sin recargarlo se sigue
   viendo el anterior.

## Rendimiento

Un asset JS y otro SCSS muy pequeños, y una única lectura de `res.company` al arrancar el
cliente web. Sin polling, sin cron.

## Notas de mantenimiento

- 🔴 **En Odoo 19 no existe el servicio `user`** (se retiró en la 17). Un servicio que lo
  declare en `dependencies` hace que `startServices` lance
  `Some services could not be started: … Missing dependencies: user` **antes** de montar el
  cliente web, y el backend se queda en blanco entero. Ese fue el fallo de la versión
  `19.0.1.0.0`. Se importa con `import { user } from "@web/core/user"`.
- El `start()` del servicio va entero dentro de un `try/catch` por el mismo motivo: si
  lanza, tumba el arranque del cliente web.
- La paleta de la lista de colores **cambió** respecto a la clásica (`#F06050`,
  `#F4A460`…). Los valores del SCSS salen de `web.assets_web.min.css` de la propia
  instancia (`.o_colorlist > button.o_colorlist_item_color_N`), leído el 2026-08-15.
