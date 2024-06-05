odoo.define('fs_stock_by_location.StockSummaryListController', function (require) {
"use strict";
    var core = require('web.core');
    var ListController = require('web.ListController');
    var qweb = core.qweb;

    var StockSummaryListController = ListController.extend({
        /**
         * @override
         */
        renderButtons: function ($node) {
            this._super.apply(this, arguments);
            var $buttonAtToDate = $(qweb.render('InventoryAtDate.Buttons'));
            $buttonAtToDate.on('click', this._inventoryAtDateWizard.bind(this));
            this.$buttons.prepend($buttonAtToDate);
        },

        _inventoryAtDateWizard: function () {
            this.do_action({
                res_model: 'stock.summary.generate',
                views: [[false, 'form']],
                target: 'new',
                type: 'ir.actions.act_window',
            });
        },
    });

    return StockSummaryListController;
});
