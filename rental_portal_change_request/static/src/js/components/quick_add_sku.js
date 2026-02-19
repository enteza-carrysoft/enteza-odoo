/**
 * Quick Add by SKU Component
 * Allows quick product addition via SKU/code search
 */

odoo.define('rental_portal.components.quick_add_sku', function (require) {
    "use strict";

    var core = require('web.core');
    var Widget = require('web.Widget');
    var RpcService = require('rental_portal.rpc_service');

    var _t = core._t;

    var QuickAddBySKU = Widget.extend({
        template: 'rental_portal.QuickAddBySKU',

        events: {
            'keypress .sku_input': '_onKeypress',
            'click .btn_add_sku': '_onAddClicked',
        },

        init: function (parent, options) {
            this._super(parent);
            this.placeholder = options.placeholder || _t('Enter SKU to add product...');
            this.disabled = options.disabled || false;
        },

        start: function () {
            this._super();
            this.$input = this.$('.sku_input');
            this.$button = this.$('.btn_add_sku');
            this.$feedback = this.$('.sku_feedback');
            return this;
        },

        /**
         * Handle keypress in input (Enter to add)
         */
        _onKeypress: function (e) {
            if (e.which === 13) { // Enter key
                e.preventDefault();
                this._onAddClicked();
            }
        },

        /**
         * Handle add button click
         */
        _onAddClicked: function () {
            var self = this;
            var sku = this.$input.val().trim();

            if (!sku) {
                return;
            }

            this._setLoading(true);

            // Search for product by SKU
            RpcService.searchCatalog(sku, 1, 0).then(function (result) {
                self._setLoading(false);

                if (result.success && result.products.length > 0) {
                    var product = result.products[0];
                    self.trigger('addRequested', {
                        product_id: product.id,
                        product_name: product.name,
                        product_code: product.default_code,
                        qty: 1,
                    });
                    self.$input.val('');
                    self._showFeedback(_t('Product added: %s').replace('%s', product.name), 'success');
                } else {
                    self._showFeedback(_t('Product not found: %s').replace('%s', sku), 'error');
                }
            }).fail(function () {
                self._setLoading(false);
                self._showFeedback(_t('Error searching for product'), 'error');
            });
        },

        /**
         * Set loading state
         */
        _setLoading: function (loading) {
            this.$button.prop('disabled', loading);
            this.$input.prop('disabled', loading);
            if (loading) {
                this.$button.find('i').addClass('fa-spinner fa-spin');
            } else {
                this.$button.find('i').removeClass('fa-spinner fa-spin');
            }
        },

        /**
         * Show feedback message
         */
        _showFeedback: function (message, type) {
            this.$feedback
                .removeClass('text-success text-danger text-warning')
                .addClass(type === 'success' ? 'text-success' : 'text-danger')
                .text(message)
                .fadeIn();

            var self = this;
            setTimeout(function () {
                self.$feedback.fadeOut();
            }, 3000);
        },

        /**
         * Disable/enable the component
         */
        setDisabled: function (disabled) {
            this.disabled = disabled;
            this.$input.prop('disabled', disabled);
            this.$button.prop('disabled', disabled);
        },
    });

    return QuickAddBySKU;
});
