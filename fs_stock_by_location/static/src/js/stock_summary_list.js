odoo.define("fs_stock_by_location.StockSummaryListView", function (require) {
    "use strict";

    var ListView = require('web.ListView');
    var StockSummaryListController = require('fs_stock_by_location.StockSummaryListController');
    var registryView = require('web.view_registry');

    var StockSummaryListView = ListView.extend({
        config: _.extend({}, ListView.prototype.config, {
            Controller: StockSummaryListController,
        }),
    });

    registryView.add('stock_summary_list', StockSummaryListView);
    return StockSummaryListView;
});
