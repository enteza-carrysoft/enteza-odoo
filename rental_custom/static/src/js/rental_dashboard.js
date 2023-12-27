odoo.define('rental_custom.DashboardRental', function (require) {
"use strict";

var AbstractAction = require('web.AbstractAction');
var ajax = require('web.ajax');
var core = require('web.core');
var rpc = require('web.rpc');
var session = require('web.session');
var web_client = require('web.web_client');
var _t = core._t;
var QWeb = core.qweb;

var PosDashboard = AbstractAction.extend({
    template: 'RentalDashboard',
    events: {
            // 'click .pos_order_today':'pos_order_today',
            // 'click .pos_order':'pos_order',
            // 'click .pos_total_sales':'pos_order',
            // 'click .pos_session':'pos_session',
            // 'click .pos_refund_orders':'pos_refund_orders',
            // 'click .pos_refund_today_orders':'pos_refund_today_orders',
            // 'change #pos_sales': 'onclick_pos_sales',
    },

    init: function(parent, context) {
        this._super(parent, context);
        this.dashboards_templates = ['RentalOrders'];
        this.context = context.context;
        this.product_stok = [];
    },

    willStart: function() {
        var self = this;
        return $.when(ajax.loadLibs(this), this._super()).then(function() {
            return self.fetch_data();
        });
    },

    start: function() {
        var self = this;
        this.set("title", 'Dashboard');
        return this._super().then(function() {
            self.render_dashboards();
            self.render_graphs();
            self.$el.parent().addClass('oe_background_grey');
        });
    },

    fetch_data: function() {
        var self = this;
        var def1 =  this._rpc({
                model: 'sale.order',
                method: 'get_report_product',
                args: [self.context],
        }).then(function(result) {
           self.product_stok = result['product_ids']
        });
        return $.when(def1);
    },

    render_dashboards: function() {
        var self = this;
            _.each(this.dashboards_templates, function(template) {
                self.$('.o_pos_dashboard').append(QWeb.render(template, {widget: self}));
            });
    },
    render_graphs: function(){
        var self = this;
        // self.render_top_customer_graph();
        // self.render_top_product_graph();
        // self.render_product_category_graph();
    },


});


core.action_registry.add('rental_dashboard', PosDashboard);

return PosDashboard;

});
