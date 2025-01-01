odoo.define('rental_availability_extended.AvailabilityPopup', function (require) {
    "use strict";

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');
    var rpc = require('web.rpc');
    var QWeb = core.qweb;

    var AvailabilityPopup = AbstractAction.extend({
        template: 'rental_availability_popup_template',

        init: function (parent, options) {
            this._super(parent, options);
            this.product_id = options.product_id;
            this.start_date = options.start_date;
            this.end_date = options.end_date;
            this.data = {};
        },

        willStart: function () {
            var self = this;
            return rpc.query({
                model: 'sale.order.line',
                method: 'get_availability_data',
                args: [self.product_id, self.start_date, self.end_date]
            }).then(function (result) {
                self.data = result;
            });
        },

        start: function () {
            this.$el.html(QWeb.render('rental_availability_popup_template', {
                data: this.data,
            }));
        },
    });

    core.action_registry.add('rental_availability_popup', AvailabilityPopup);
    return AvailabilityPopup;
});

