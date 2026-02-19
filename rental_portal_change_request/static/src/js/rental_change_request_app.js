/**
 * Rental Change Request App
 * Main OWL application for change request editing
 */

odoo.define('rental_portal.change_request_app', function (require) {
    "use strict";

    var core = require('web.core');
    var Widget = require('web.Widget');
    var RpcService = require('rental_portal.rpc_service');
    var AvailabilityService = require('rental_portal.availability_service');

    // Components
    var OrderLinesTable = require('rental_portal.components.order_lines_table');
    var QuickAddBySKU = require('rental_portal.components.quick_add_sku');
    var CatalogSidePanel = require('rental_portal.components.catalog_side_panel');
    var StatusIndicator = require('rental_portal.components.status_indicator');

    var _t = core._t;

    var RentalChangeRequestApp = Widget.extend({
        template: 'rental_portal.ChangeRequestApp',

        custom_events: {
            'lineQtyChanged': '_onLineQtyChanged',
            'lineRemoved': '_onLineRemoved',
            'addRequested': '_onAddRequested',
            'productSelected': '_onProductSelected',
            'showCatalogRequested': '_onShowCatalogRequested',
        },

        init: function (parent, options) {
            this._super(parent);
            this.orderId = options.orderId;
            this.changeRequestId = options.changeRequestId;
            this.csrfToken = options.csrfToken;

            // State
            this.state = {
                changeRequest: null,
                order: null,
                lines: [],
                isLoading: true,
                error: null,
                hasChanges: false,
                tokenOrder: null,
                tokenRevision: null,
            };
        },

        start: function () {
            this._super();

            // Initialize components
            this._initComponents();

            // Load initial data
            this._loadData();

            return this;
        },

        /**
         * Initialize child components
         */
        _initComponents: function () {
            var self = this;

            // Status indicator
            this.statusIndicator = new StatusIndicator(this, 'draft');
            this.statusIndicator.appendTo(this.$('.status_indicator_container'));

            // Lines table
            this.linesTable = new OrderLinesTable(this, {
                lines: [],
                readonly: false,
            });
            this.linesTable.appendTo(this.$('.lines_table_container'));

            // Quick add
            this.quickAdd = new QuickAddBySKU(this, {
                placeholder: _t('Enter SKU to add product...'),
            });
            this.quickAdd.on('addRequested', this, this._onAddRequested);
            this.quickAdd.appendTo(this.$('.quick_add_container'));

            // Catalog panel
            this.catalogPanel = new CatalogSidePanel(this, {
                pageSize: 20,
            });
            this.catalogPanel.on('productSelected', this, this._onProductSelected);
            this.catalogPanel.appendTo(this.$('.catalog_panel_container'));
        },

        /**
         * Load initial data
         */
        _loadData: function () {
            var self = this;

            this._setLoading(true);

            RpcService.loadChangeRequest(this.changeRequestId, this.orderId).then(function (data) {
                self._setLoading(false);

                if (data.success) {
                    self.state.changeRequest = data.change_request;
                    self.state.order = data.order;
                    self.state.lines = data.lines || [];

                    if (data.change_request) {
                        self.state.tokenOrder = data.change_request.expected_order_write_date;
                        self.state.tokenRevision = data.change_request.expected_revision_write_date;
                    }

                    self._render();
                } else {
                    self._showError(data.error);
                }
            }).fail(function () {
                self._setLoading(false);
                self._showError(_t('Failed to load change request'));
            });
        },

        /**
         * Render the UI
         */
        _render: function () {
            // Update title
            if (this.state.changeRequest) {
                this.$('.change_request_title').text(
                    _t('Edit Change Request: %s').replace('%s', this.state.changeRequest.name)
                );
            } else {
                this.$('.change_request_title').text(
                    _t('New Change Request for %s').replace('%s', this.state.order.name)
                );
            }

            // Update status
            var state = this.state.changeRequest ? this.state.changeRequest.state : 'draft';
            this.statusIndicator.state = state;
            this.statusIndicator.renderElement();

            // Update lines table
            this.linesTable.setLines(this.state.lines);

            // Update button states
            this._updateButtons();
        },

        /**
         * Update button states based on state
         */
        _updateButtons: function () {
            var canSubmit = this.state.lines.length > 0 && this.state.hasChanges;
            var canSave = this.state.hasChanges;

            this.$('.btn_submit').prop('disabled', !canSubmit);
            this.$('.btn_save').prop('disabled', !canSave);
        },

        /**
         * Handle line quantity changed
         */
        _onLineQtyChanged: function (ev) {
            var lineId = ev.data.line_id;
            var newQty = ev.data.qty;

            // Update local state
            var line = _.findWhere(this.state.lines, {id: lineId});
            if (line) {
                var oldQty = line.qty;
                line.qty = newQty;

                // Mark as changed
                if (oldQty !== newQty) {
                    this._markChanged();
                }

                // Queue patch operation
                this._queuePatch({
                    operation: 'update',
                    product_id: line.product_id,
                    qty: newQty,
                    line_id: lineId,
                });
            }
        },

        /**
         * Handle line removed
         */
        _onLineRemoved: function (ev) {
            var lineId = ev.data.line_id;

            // Remove from local state
            this.state.lines = _.reject(this.state.lines, function (line) {
                return line.id === lineId;
            });

            this._markChanged();

            // Queue patch operation
            this._queuePatch({
                operation: 'remove',
                line_id: lineId,
            });
        },

        /**
         * Handle add requested (from quick add)
         */
        _onAddRequested: function (ev) {
            var product = ev.data;

            // Check if product already exists
            var existingLine = _.findWhere(this.state.lines, {product_id: product.product_id});
            if (existingLine) {
                // Increment quantity
                existingLine.qty += product.qty;
                this._queuePatch({
                    operation: 'update',
                    product_id: product.product_id,
                    qty: existingLine.qty,
                    line_id: existingLine.id,
                });
            } else {
                // Add new line (temporary ID)
                var tempId = 'temp_' + Date.now();
                this.state.lines.push(_.extend({}, product, {
                    id: tempId,
                }));

                this._queuePatch({
                    operation: 'add',
                    product_id: product.product_id,
                    qty: product.qty,
                });
            }

            this._markChanged();
            this.linesTable.setLines(this.state.lines);
        },

        /**
         * Handle product selected from catalog
         */
        _onProductSelected: function (ev) {
            this._onAddRequested(ev);
            this.catalogPanel.hide();
        },

        /**
         * Handle show catalog requested
         */
        _onShowCatalogRequested: function () {
            this.catalogPanel.show();
        },

        /**
         * Queue and debounce patch operation
         */
        _queuePatch: function (operation) {
            var self = this;

            if (!this._patchQueue) {
                this._patchQueue = [];
            }

            this._patchQueue.push(operation);

            clearTimeout(this._patchTimeout);
            this._patchTimeout = setTimeout(function () {
                self._applyPatches();
            }, 500);
        },

        /**
         * Apply queued patches
         */
        _applyPatches: function () {
            var self = this;

            if (!this._patchQueue || this._patchQueue.length === 0) {
                return;
            }

            var patches = this._patchQueue;
            this._patchQueue = [];

            // Need change request ID for patches
            if (!this.changeRequestId) {
                // Will apply on submit
                return;
            }

            RpcService.patchRevision(
                this.changeRequestId,
                patches,
                this.state.tokenOrder,
                this.state.tokenRevision
            ).then(function (result) {
                if (result.success) {
                    self.state.tokenRevision = result.new_revision_token;
                } else {
                    self._showError(result.error);
                    // Reload to get correct state
                    self._loadData();
                }
            }).fail(function () {
                self._showError(_t('Failed to apply changes'));
            });
        },

        /**
         * Mark as having changes
         */
        _markChanged: function () {
            this.state.hasChanges = true;
            this._updateButtons();
        },

        /**
         * Handle submit button click
         */
        _onSubmitClicked: function () {
            var self = this;

            var note = this.$('.submission_note').val().trim();

            if (!this.changeRequestId) {
                // Create new change request first
                this._setLoading(true);

                RpcService.startChangeRequest(this.orderId).then(function (result) {
                    self._setLoading(false);

                    if (result.success) {
                        self.changeRequestId = result.change_request;
                        self.state.tokenOrder = result.order_write_date;
                        self.state.tokenRevision = result.revision_write_date;

                        // Apply pending patches
                        if (self._patchQueue && self._patchQueue.length > 0) {
                            self._applyPatches();
                        }

                        // Now submit
                        self._doSubmit(note);
                    } else {
                        self._showError(result.error);
                    }
                }).fail(function () {
                    self._setLoading(false);
                    self._showError(_t('Failed to create change request'));
                });
            } else {
                this._doSubmit(note);
            }
        },

        /**
         * Perform submit
         */
        _doSubmit: function (note) {
            var self = this;

            this._setLoading(true);

            RpcService.submitChangeRequest(this.changeRequestId, note).then(function (result) {
                self._setLoading(false);

                if (result.success) {
                    self.trigger('submitted');
                    self._showSuccess(_t('Change request submitted for approval'));
                    setTimeout(function () {
                        window.location.href = '/my/rentals/' + self.orderId;
                    }, 1500);
                } else {
                    self._showError(result.error);
                }
            }).fail(function () {
                self._setLoading(false);
                self._showError(_t('Failed to submit change request'));
            });
        },

        /**
         * Handle cancel button click
         */
        _onCancelClicked: function () {
            if (confirm(_t('Are you sure you want to cancel this change request?'))) {
                var self = this;

                if (this.changeRequestId) {
                    RpcService.cancelChangeRequest(this.changeRequestId).then(function () {
                        window.location.href = '/my/rentals/' + self.orderId;
                    });
                } else {
                    window.location.href = '/my/rentals/' + this.orderId;
                }
            }
        },

        /**
         * Set loading state
         */
        _setLoading: function (loading) {
            this.state.isLoading = loading;
            this.$el.toggleClass('loading', loading);
        },

        /**
         * Show error message
         */
        _showError: function (message) {
            this.$('.alert_container').html(
                '<div class="alert alert-danger alert-dismissible fade show" role="alert">' +
                message +
                '<button type="button" class="close" data-dismiss="alert" aria-label="Close">' +
                '<span aria-hidden="true">&times;</span></button></div>'
            );
        },

        /**
         * Show success message
         */
        _showSuccess: function (message) {
            this.$('.alert_container').html(
                '<div class="alert alert-success alert-dismissible fade show" role="alert">' +
                message +
                '<button type="button" class="close" data-dismiss="alert" aria-label="Close">' +
                '<span aria-hidden="true">&times;</span></button></div>'
            );
        },
    });

    // Auto-initialize on page load
    $(document).ready(function () {
        var $container = $('#rental_change_request_app');
        if ($container.length) {
            var orderId = parseInt($container.data('order-id'));
            var changeRequestId = parseInt($container.data('change-request-id'));
            var csrfToken = $container.data('csrf-token');

            if (orderId) {
                var app = new RentalChangeRequestApp(null, {
                    orderId: orderId,
                    changeRequestId: changeRequestId || 0,
                    csrfToken: csrfToken,
                });
                app.appendTo($container);
            }
        }
    });

    return RentalChangeRequestApp;
});
