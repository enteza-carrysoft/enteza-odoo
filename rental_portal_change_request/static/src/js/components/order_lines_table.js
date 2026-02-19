/**
 * Order Lines Table Component
 * Editable table for order lines with performance optimizations
 */

odoo.define('rental_portal.components.order_lines_table', function (require) {
    "use strict";

    var core = require('web.core');
    var Widget = require('web.Widget');
    var AvailabilityService = require('rental_portal.availability_service');

    var _t = core._t;

    var OrderLinesTable = Widget.extend({
        template: 'rental_portal.OrderLinesTable',

        events: {
            'change .line_qty_input': '_onQtyChanged',
            'click .btn_remove_line': '_onRemoveClicked',
            'change .line_note_input': '_onNoteChanged',
            'click .btn_add_from_catalog': '_onAddFromCatalog',
        },

        init: function (parent, options) {
            this._super(parent);
            this.lines = options.lines || [];
            this.groupBy = options.groupBy || null;
            this.readonly = options.readonly || false;
            this.currency = options.currency || '$';
        },

        start: function () {
            this._super();
            this._renderLines();
            return this;
        },

        /**
         * Render all lines
         */
        _renderLines: function () {
            var self = this;
            var $tbody = this.$('.order_lines_tbody');
            $tbody.empty();

            if (this.lines.length === 0) {
                $tbody.append(
                    '<tr><td colspan="6" class="text-center text-muted">' +
                    _t('No lines yet. Add products from the catalog or use quick add.') +
                    '</td></tr>'
                );
                return;
            }

            this.lines.forEach(function (line) {
                $tbody.append(self._renderLine(line));
            });
        },

        /**
         * Render a single line
         */
        _renderLine: function (line) {
            var self = this;
            var $tr = $('<tr/>').data('line-id', line.id);

            // Product info
            var $productCell = $('<td/>').append(
                $('<div/>').addClass('font-weight-normal').text(line.product_name),
                line.product_code ? $('<small/>').addClass('text-muted').text('SKU: ' + line.product_code) : null
            );

            // Quantity input
            var $qtyCell = $('<td/>').addClass('text-center');
            if (!this.readonly) {
                $qtyCell.append(
                    $('<input/>')
                        .addClass('form-control form-control-sm line_qty_input')
                        .attr('type', 'number')
                        .attr('min', '0')
                        .attr('step', '1')
                        .val(line.qty)
                        .data('line-id', line.id)
                );
            } else {
                $qtyCell.text(line.qty);
            }

            // Price
            var $priceCell = $('<td/>').addClass('text-right').text(
                this.currency + ' ' + (line.price_unit || 0).toFixed(2)
            );

            // Subtotal
            var subtotal = (line.qty * (line.price_unit || 0)).toFixed(2);
            var $subtotalCell = $('<td/>').addClass('text-right').text(
                this.currency + ' ' + subtotal
            );

            // Availability indicator
            var $availCell = $('<td/>').addClass('text-center');
            var $availIcon = $('<i/>').addClass('fa fa-circle text-muted');
            $availCell.append($availIcon);

            // Check availability asynchronously
            this._checkAvailability(line.product_id, $availCell);

            // Actions
            var $actionCell = $('<td/>').addClass('text-center');
            if (!this.readonly) {
                $actionCell.append(
                    $('<button/>')
                        .addClass('btn btn-sm btn-outline-danger btn_remove_line')
                        .attr('title', _t('Remove'))
                        .data('line-id', line.id)
                        .append($('<i/>').addClass('fa fa-trash'))
                );
            }

            return $tr.append($productCell, $qtyCell, $priceCell, $subtotalCell, $availCell, $actionCell);
        },

        /**
         * Check availability for a product
         */
        _checkAvailability: function (productId, $cell) {
            var self = this;
            AvailabilityService.checkAvailability([productId]).then(function (result) {
                var info = result[productId] || {};
                var statusInfo = AvailabilityService.getStatusInfo(info.status || 'unknown');

                $cell.empty();
                $cell.append(
                    $('<i/>')
                        .addClass('fa ' + statusInfo.icon + ' ' + statusInfo.class)
                        .attr('title', statusInfo.label + ' (' + (info.available_qty || 0) + ')')
                );
            });
        },

        /**
         * Handle quantity change
         */
        _onQtyChanged: function (e) {
            var $input = $(e.currentTarget);
            var lineId = $input.data('line-id');
            var newQty = parseFloat($input.val()) || 0;

            this.trigger('lineQtyChanged', {
                line_id: lineId,
                qty: newQty,
            });

            // Update subtotal immediately
            var $tr = $input.closest('tr');
            var priceUnit = parseFloat($tr.data('price-unit') || 0);
            var newSubtotal = (newQty * priceUnit).toFixed(2);
            $tr.find('td:nth-child(4)').text(this.currency + ' ' + newSubtotal);
        },

        /**
         * Handle remove button click
         */
        _onRemoveClicked: function (e) {
            var $btn = $(e.currentTarget);
            var lineId = $btn.data('line-id');
            var $tr = $btn.closest('tr');

            // Remove row with animation
            $tr.fadeOut(300, function () {
                $(this).remove();
            });

            this.trigger('lineRemoved', {
                line_id: lineId,
            });
        },

        /**
         * Handle note change
         */
        _onNoteChanged: function (e) {
            var $input = $(e.currentTarget);
            var lineId = $input.data('line-id');
            var note = $input.val();

            this.trigger('lineNoteChanged', {
                line_id: lineId,
                note: note,
            });
        },

        /**
         * Handle add from catalog button
         */
        _onAddFromCatalog: function () {
            this.trigger('showCatalogRequested');
        },

        /**
         * Update lines and re-render
         */
        setLines: function (lines) {
            this.lines = lines;
            this._renderLines();
        },

        /**
         * Update a single line (optimized, no full re-render)
         */
        updateLine: function (lineId, updates) {
            var line = _.findWhere(this.lines, {id: lineId});
            if (line) {
                _.extend(line, updates);
                var $tr = this.$('tr[data-line-id="' + lineId + '"]');
                if ($tr.length) {
                    // Update only changed cells
                    if (updates.qty !== undefined) {
                        $tr.find('.line_qty_input').val(updates.qty);
                        var subtotal = (updates.qty * (line.price_unit || 0)).toFixed(2);
                        $tr.find('td:nth-child(4)').text(this.currency + ' ' + subtotal);
                    }
                }
            }
        },
    });

    return OrderLinesTable;
});
