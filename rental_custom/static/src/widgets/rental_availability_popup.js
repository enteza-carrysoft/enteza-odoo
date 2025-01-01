/** @odoo-module **/

import { formatDateTime } from "@web/core/l10n/dates";
import { localization } from "@web/core/l10n/localization";
import { patch } from "@web/core/utils/patch";
import {
    QtyAtDatePopover,
    QtyAtDateWidget,
    qtyAtDateWidget,
} from "@sale_stock/widgets/qty_at_date_widget";

patch(QtyAtDatePopover.prototype, {
    /**
     * Extend the method to show the rental availability for a product
     * across all warehouses during a given period.
     */
    async openRentalAvailabilityPopup() {
        const action = await this.actionService.loadAction("rental_custom.action_rental_availability_popup", this.props.context);
        action.context = {
            ...this.props.context,
            product_id: this.props.record.data.product_id[0],
            start_date: this.props.record.data.start_date,
            end_date: this.props.record.data.return_date,
        };
        this.actionService.doAction(action);
    },
});

patch(QtyAtDateWidget.prototype, {
    /**
     * Update calculation data to include start and end dates for rentals
     * and compute total availability across warehouses.
     */
    updateCalcData() {
        const { data } = this.props.record;
        if (!data.product_id) {
            return;
        }
        if (!data.is_rental || !data.return_date || !data.start_date) {
            return super.updateCalcData();
        }
        this.calcData.stock_end_date = formatDateTime(data.return_date, { format: localization.dateFormat });
        this.calcData.stock_start_date = formatDateTime(data.start_date, { format: localization.dateFormat });

        // Add a new property for total availability
        this.calcData.total_availability = this.calculateTotalAvailability(data.product_id[0], data.start_date, data.return_date);
    },

    /**
     * Custom method to calculate total availability across all warehouses
     * for the specified product and date range.
     */
    calculateTotalAvailability(productId, startDate, endDate) {
        // This should ideally call an RPC to fetch the data from the backend
        return this.rpc({
            model: "sale.order.line",
            method: "get_availability_data",
            args: [productId, startDate, endDate],
        }).then((result) => {
            return result.total_available;
        });
    },
});

export const rentalQtyAtDateWidget = {
    ...qtyAtDateWidget,
    fieldDependencies: [
        { name: "start_date", type: "datetime" },
        { name: "return_date", type: "datetime" },
    ],
};
patch(qtyAtDateWidget, rentalQtyAtDateWidget);

