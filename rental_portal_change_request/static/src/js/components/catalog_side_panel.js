/**
 * Catalog Side Panel Component
 * Paginated product catalog with search
 */

odoo.define('rental_portal.components.catalog_side_panel', function (require) {
    "use strict";

    var core = require('web.core');
    var Widget = require('web.Widget');
    var RpcService = require('rental_portal.rpc_service');

    var _t = core._t;

    var CatalogSidePanel = Widget.extend({
        template: 'rental_portal.CatalogSidePanel',

        events: {
            'input .catalog_search_input': '_onSearchInput',
            'click .catalog_product_item': '_onProductClicked',
            'click .btn_catalog_prev': '_onPrevPage',
            'click .btn_catalog_next': '_onNextPage',
            'click .btn_close_catalog': '_onClose',
        },

        init: function (parent, options) {
            this._super(parent);
            this.pageSize = options.pageSize || 20;
            this.currentPage = 0;
            this.searchTerm = '';
            this.products = [];
            this.totalCount = 0;
            this.isLoading = false;
        },

        start: function () {
            this._super();
            this.$panel = this.$('.catalog_side_panel');
            this.$list = this.$('.catalog_product_list');
            this.$searchInput = this.$('.catalog_search_input');
            this.$prevBtn = this.$('.btn_catalog_prev');
            this.$nextBtn = this.$('.btn_catalog_next');
            this.$pageInfo = this.$('.catalog_page_info');

            // Initial search
            this._searchProducts();

            return this;
        },

        /**
         * Search products with current term and page
         */
        _searchProducts: function () {
            var self = this;
            this._setLoading(true);

            RpcService.searchCatalog(
                this.searchTerm,
                this.pageSize,
                this.currentPage * this.pageSize
            ).then(function (result) {
                self._setLoading(false);

                if (result.success) {
                    self.products = result.products;
                    self.totalCount = result.total_count;
                    self._renderProducts();
                    self._updatePagination();
                }
            }).fail(function () {
                self._setLoading(false);
                self._showError(_t('Error loading products'));
            });
        },

        /**
         * Render product list
         */
        _renderProducts: function () {
            var self = this;
            this.$list.empty();

            if (this.products.length === 0) {
                this.$list.append(
                    '<div class="text-center text-muted py-3">' +
                    _t('No products found') +
                    '</div>'
                );
                return;
            }

            this.products.forEach(function (product) {
                var $item = $('<div/>')
                    .addClass('catalog_product_item')
                    .data('product-id', product.id);

                if (product.image_url) {
                    $item.append(
                        $('<img/>')
                            .addClass('catalog_product_image')
                            .attr('src', product.image_url)
                            .attr('alt', product.name)
                    );
                }

                var $info = $('<div/>').addClass('catalog_product_info');

                $info.append(
                    $('<div/>').addClass('catalog_product_name').text(product.name),
                    product.default_code ? $('<small/>').addClass('text-muted').text(product.default_code) : null,
                    $('<div/>').addClass('catalog_product_price').text(
                        (product.lst_price || 0).toFixed(2)
                    )
                );

                $item.append($info);
                self.$list.append($item);
            });
        },

        /**
         * Update pagination controls
         */
        _updatePagination: function () {
            var totalPages = Math.ceil(this.totalCount / this.pageSize);
            var startItem = this.currentPage * this.pageSize + 1;
            var endItem = Math.min((this.currentPage + 1) * this.pageSize, this.totalCount);

            this.$pageInfo.text(
                this.totalCount > 0 ?
                    _t('%d - %d of %d').replace('%d', startItem).replace('%d', endItem).replace('%d', this.totalCount) :
                    _t('No products')
            );

            this.$prevBtn.prop('disabled', this.currentPage === 0);
            this.$nextBtn.prop('disabled', this.currentPage >= totalPages - 1 || this.totalCount === 0);
        },

        /**
         * Handle search input (debounced)
         */
        _onSearchInput: function () {
            var self = this;
            clearTimeout(this._searchTimeout);

            this._searchTimeout = setTimeout(function () {
                self.searchTerm = self.$searchInput.val().trim();
                self.currentPage = 0;
                self._searchProducts();
            }, 300);
        },

        /**
         * Handle product click
         */
        _onProductClicked: function (e) {
            var $item = $(e.currentTarget).closest('.catalog_product_item');
            var productId = $item.data('product-id');
            var product = _.findWhere(this.products, {id: productId});

            if (product) {
                this.trigger('productSelected', {
                    product_id: product.id,
                    product_name: product.name,
                    product_code: product.default_code || '',
                    qty: 1,
                    price_unit: product.lst_price || 0,
                });
            }
        },

        /**
         * Handle previous page
         */
        _onPrevPage: function () {
            if (this.currentPage > 0) {
                this.currentPage--;
                this._searchProducts();
            }
        },

        /**
         * Handle next page
         */
        _onNextPage: function () {
            var totalPages = Math.ceil(this.totalCount / this.pageSize);
            if (this.currentPage < totalPages - 1) {
                this.currentPage++;
                this._searchProducts();
            }
        },

        /**
         * Handle close button
         */
        _onClose: function () {
            this.$panel.removeClass('show');
        },

        /**
         * Show the panel
         */
        show: function () {
            this.$panel.addClass('show');
            this.$searchInput.focus();
        },

        /**
         * Set loading state
         */
        _setLoading: function (loading) {
            this.isLoading = loading;
            this.$list.toggleClass('loading', loading);
        },

        /**
         * Show error message
         */
        _showError: function (message) {
            this.$list.empty();
            this.$list.append(
                '<div class="text-center text-danger py-3">' + message + '</div>'
            );
        },
    });

    return CatalogSidePanel;
});
