/** @odoo-module **/

import { registry } from "@web/core/registry";
import { user } from "@web/core/user";

/**
 * Marca en `<html>` el índice de color de la compañía activa (o el marcador "multi" si hay
 * dos o más compañías seleccionadas en el selector de compañías).
 *
 * El color en sí no se decide aquí: lo pinta el SCSS a partir del atributo
 * `data-company-color`, para no duplicar la paleta de Odoo en JavaScript y para no
 * añadir nodos al DOM que monta el cliente web.
 *
 * 🔴 En Odoo 19 **no existe el servicio `user`** (desapareció en la 17): `user` se importa
 * de `@web/core/user`. Declararlo como dependencia hace que `startServices` lance
 * "Some services could not be started ... Missing dependencies: user" antes de montar el
 * cliente web, y el backend entero se queda **en blanco**. Verificado en el bundle de
 * `enteza` el 2026-08-15.
 *
 * `user.activeCompanies` son las compañías marcadas en el selector (no solo las permitidas):
 * confirmar una selección de 2 o más recarga la página (`CompanySelector.apply()` del core de
 * Odoo hace `router.pushState(..., { reload: true })`), así que este servicio se vuelve a
 * ejecutar entero y no hace falta escuchar ningún evento de cambio aparte.
 */
export const companyTopColorService = {
    dependencies: ["orm"],

    async start(env, { orm }) {
        // Un fallo aquí abortaría el arranque del cliente web, así que nada sale de este
        // try: la franja es decorativa y nunca debe impedir trabajar.
        try {
            if (user.activeCompanies.length > 1) {
                // Varias compañías a la vez: rojo fijo, independiente del color de cada
                // compañía (que podría no ser rojo en ninguna de ellas).
                document.documentElement.dataset.companyColor = "multi";
                return;
            }

            const company = user.activeCompany;
            if (!company) {
                return;
            }
            const [record] = await orm.read("res.company", [company.id], ["color"]);
            const colorIndex = record && record.color;
            if (colorIndex) {
                document.documentElement.dataset.companyColor = String(colorIndex);
            } else {
                delete document.documentElement.dataset.companyColor;
            }
        } catch (error) {
            console.warn("company_top_color: no se pudo leer el color de la compañía.", error);
        }
    },
};

registry.category("services").add("company_top_color", companyTopColorService);
