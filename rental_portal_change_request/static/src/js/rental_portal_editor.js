/**
 * Rental Portal Change Request Editor
 *
 * Simple vanilla JS editor for the portal (no OWL/ES6 modules)
 */
(function() {
    'use strict';

    // Wait for DOM ready
    document.addEventListener('DOMContentLoaded', function() {
        const container = document.getElementById('rental-change-request-app');
        if (!container) return;

        const orderId = parseInt(container.dataset.orderId, 10);
        if (!orderId) return;

        // Initialize the editor
        new ChangeRequestEditor(container, orderId);
    });

    /**
     * Main Editor Class
     */
    function ChangeRequestEditor(container, orderId) {
        this.container = container;
        this.orderId = orderId;
        this.order = null;
        this.lines = [];
        this.originalLines = [];
        this.note = '';

        this.init();
    }

    ChangeRequestEditor.prototype.init = function() {
        this.loadOrder();
    };

    ChangeRequestEditor.prototype.loadOrder = function() {
        var self = this;
        this.showLoading();

        this.rpc('/rental_portal/jsonrpc/order/load', { order_id: this.orderId })
            .then(function(result) {
                if (result.success) {
                    self.order = result.order;
                    self.lines = result.lines;
                    self.originalLines = JSON.parse(JSON.stringify(result.lines));
                    self.render();
                } else {
                    self.showError(result.error || 'Failed to load order');
                }
            })
            .catch(function(error) {
                self.showError('Network error: ' + error.message);
            });
    };

    ChangeRequestEditor.prototype.rpc = function(url, params) {
        return fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                jsonrpc: '2.0',
                method: 'call',
                params: params,
                id: Math.floor(Math.random() * 1000000)
            })
        })
        .then(function(response) {
            return response.json();
        })
        .then(function(data) {
            if (data.error) {
                throw new Error(data.error.data ? data.error.data.message : data.error.message);
            }
            return data.result;
        });
    };

    ChangeRequestEditor.prototype.showLoading = function() {
        this.container.innerHTML = `
            <div class="text-center py-5">
                <i class="fa fa-spinner fa-spin fa-3x text-primary"></i>
                <p class="mt-3">Loading order data...</p>
            </div>
        `;
    };

    ChangeRequestEditor.prototype.showError = function(message) {
        this.container.innerHTML = `
            <div class="container py-4">
                <div class="alert alert-danger">
                    <i class="fa fa-exclamation-circle me-2"></i>
                    ${this.escapeHtml(message)}
                </div>
                <a href="/my/rentals/${this.orderId}" class="btn btn-outline-secondary">
                    <i class="fa fa-arrow-left me-1"></i> Back to Order
                </a>
            </div>
        `;
    };

    ChangeRequestEditor.prototype.escapeHtml = function(text) {
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    };

    ChangeRequestEditor.prototype.formatPrice = function(amount) {
        return amount.toFixed(2) + ' €';
    };

    ChangeRequestEditor.prototype.render = function() {
        var self = this;
        var linesHtml = this.lines.map(function(line, index) {
            return `
                <tr data-product-id="${line.product_id}">
                    <td>
                        <strong>${self.escapeHtml(line.product_name)}</strong>
                        ${line.product_code ? `<small class="text-muted d-block">SKU: ${self.escapeHtml(line.product_code)}</small>` : ''}
                    </td>
                    <td class="text-center">
                        <input type="number"
                               class="form-control form-control-sm text-center line-qty"
                               value="${line.qty}"
                               min="0.01"
                               step="1"
                               data-index="${index}">
                    </td>
                    <td class="text-end">${self.formatPrice(line.price_unit)}</td>
                    <td class="text-end line-subtotal">${self.formatPrice(line.qty * line.price_unit)}</td>
                    <td class="text-center">
                        <button class="btn btn-sm btn-outline-danger btn-remove" data-index="${index}" title="Remove">
                            <i class="fa fa-trash"></i>
                        </button>
                    </td>
                </tr>
            `;
        }).join('');

        var total = this.lines.reduce(function(sum, l) { return sum + l.qty * l.price_unit; }, 0);

        this.container.innerHTML = `
            <div class="container py-4">
                <!-- Header -->
                <div class="d-flex justify-content-between align-items-center mb-4">
                    <h2>
                        <i class="fa fa-edit me-2"></i>
                        Request Changes
                        <small class="text-muted ms-2">- ${this.escapeHtml(this.order.name)}</small>
                    </h2>
                    <a href="/my/rentals/${this.orderId}" class="btn btn-outline-secondary">
                        <i class="fa fa-arrow-left me-1"></i> Back to Order
                    </a>
                </div>

                <!-- Error Alert (hidden by default) -->
                <div id="error-alert" class="alert alert-danger d-none">
                    <i class="fa fa-exclamation-circle me-2"></i>
                    <span id="error-message"></span>
                </div>

                <!-- Success Alert (hidden by default) -->
                <div id="success-alert" class="alert alert-success d-none">
                    <i class="fa fa-check-circle me-2"></i>
                    <span id="success-message"></span>
                </div>

                <div class="row">
                    <!-- Left Column - Lines -->
                    <div class="col-lg-8">
                        <div class="card mb-4">
                            <div class="card-header">
                                <h5 class="mb-0">Order Lines</h5>
                            </div>
                            <div class="card-body p-0">
                                <table class="table table-sm table-hover mb-0">
                                    <thead class="table-light">
                                        <tr>
                                            <th>Product</th>
                                            <th class="text-center" style="width: 120px;">Qty</th>
                                            <th class="text-end" style="width: 100px;">Price</th>
                                            <th class="text-end" style="width: 120px;">Subtotal</th>
                                            <th style="width: 50px;"></th>
                                        </tr>
                                    </thead>
                                    <tbody id="lines-tbody">
                                        ${linesHtml || '<tr><td colspan="5" class="text-center text-muted py-4">No items in order</td></tr>'}
                                    </tbody>
                                    <tfoot class="table-light">
                                        <tr>
                                            <td colspan="3" class="text-end"><strong>Total:</strong></td>
                                            <td class="text-end"><strong id="total-amount">${this.formatPrice(total)}</strong></td>
                                            <td></td>
                                        </tr>
                                    </tfoot>
                                </table>
                            </div>
                        </div>

                        <!-- Note -->
                        <div class="card mb-4">
                            <div class="card-header">
                                <h5 class="mb-0">Message (optional)</h5>
                            </div>
                            <div class="card-body">
                                <textarea id="submission-note" class="form-control" rows="3"
                                          placeholder="Add a note explaining your requested changes..."></textarea>
                            </div>
                        </div>

                        <!-- Actions -->
                        <div class="d-flex gap-2 justify-content-end">
                            <a href="/my/rentals/${this.orderId}" class="btn btn-outline-secondary">Cancel</a>
                            <button id="submit-btn" class="btn btn-primary" disabled>
                                <i class="fa fa-paper-plane me-1"></i>
                                Submit Request
                            </button>
                        </div>
                    </div>

                    <!-- Right Column - Add Products -->
                    <div class="col-lg-4">
                        <div class="card sticky-top" style="top: 20px;">
                            <div class="card-header">
                                <h5 class="mb-0">
                                    <i class="fa fa-plus-circle me-2"></i>
                                    Add Products
                                </h5>
                            </div>
                            <div class="card-body">
                                <div class="position-relative mb-3">
                                    <div class="input-group">
                                        <span class="input-group-text">
                                            <i class="fa fa-search"></i>
                                        </span>
                                        <input type="text" id="product-search" class="form-control"
                                               placeholder="Search products by name or SKU...">
                                    </div>
                                    <div id="search-results" class="position-absolute w-100 bg-white border rounded shadow-sm mt-1 d-none"
                                         style="z-index: 1000; max-height: 300px; overflow-y: auto;">
                                    </div>
                                </div>
                                <small class="text-muted">
                                    Search by product name or SKU code to add items to your order.
                                </small>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        this.bindEvents();
        this.updateSubmitButton();
    };

    ChangeRequestEditor.prototype.bindEvents = function() {
        var self = this;

        // Quantity change
        this.container.querySelectorAll('.line-qty').forEach(function(input) {
            input.addEventListener('change', function() {
                var index = parseInt(this.dataset.index, 10);
                var newQty = parseFloat(this.value) || 0;
                if (newQty > 0) {
                    self.lines[index].qty = newQty;
                    self.updateLineSubtotal(index);
                    self.updateTotal();
                    self.updateSubmitButton();
                }
            });
        });

        // Remove button
        this.container.querySelectorAll('.btn-remove').forEach(function(btn) {
            btn.addEventListener('click', function() {
                var index = parseInt(this.dataset.index, 10);
                self.lines.splice(index, 1);
                self.render();
            });
        });

        // Product search
        var searchInput = document.getElementById('product-search');
        var searchTimeout = null;
        searchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            var term = this.value.trim();
            if (term.length < 2) {
                self.hideSearchResults();
                return;
            }
            searchTimeout = setTimeout(function() {
                self.searchProducts(term);
            }, 300);
        });

        // Submit button
        document.getElementById('submit-btn').addEventListener('click', function() {
            self.submitRequest();
        });

        // Note
        document.getElementById('submission-note').addEventListener('input', function() {
            self.note = this.value;
        });
    };

    ChangeRequestEditor.prototype.updateLineSubtotal = function(index) {
        var line = this.lines[index];
        var row = this.container.querySelector('tr[data-product-id="' + line.product_id + '"]');
        if (row) {
            row.querySelector('.line-subtotal').textContent = this.formatPrice(line.qty * line.price_unit);
        }
    };

    ChangeRequestEditor.prototype.updateTotal = function() {
        var total = this.lines.reduce(function(sum, l) { return sum + l.qty * l.price_unit; }, 0);
        document.getElementById('total-amount').textContent = this.formatPrice(total);
    };

    ChangeRequestEditor.prototype.hasChanges = function() {
        if (this.lines.length !== this.originalLines.length) {
            return true;
        }

        var origMap = {};
        this.originalLines.forEach(function(l) {
            origMap[l.product_id] = l.qty;
        });

        for (var i = 0; i < this.lines.length; i++) {
            var l = this.lines[i];
            if (!(l.product_id in origMap) || origMap[l.product_id] !== l.qty) {
                return true;
            }
        }

        return false;
    };

    ChangeRequestEditor.prototype.updateSubmitButton = function() {
        var btn = document.getElementById('submit-btn');
        btn.disabled = !this.hasChanges();
    };

    ChangeRequestEditor.prototype.searchProducts = function(term) {
        var self = this;

        this.rpc('/rental_portal/jsonrpc/catalog/search', {
            search_term: term,
            limit: 10
        })
        .then(function(result) {
            if (result.success && result.products.length > 0) {
                self.showSearchResults(result.products);
            } else {
                self.showNoResults();
            }
        })
        .catch(function() {
            self.hideSearchResults();
        });
    };

    ChangeRequestEditor.prototype.showSearchResults = function(products) {
        var self = this;
        var resultsDiv = document.getElementById('search-results');

        resultsDiv.innerHTML = products.map(function(p) {
            return `
                <div class="p-2 border-bottom search-result" style="cursor: pointer;" data-product='${JSON.stringify(p)}'>
                    <div class="fw-bold">${self.escapeHtml(p.product_name)}</div>
                    <small class="text-muted">
                        ${p.product_code ? 'SKU: ' + self.escapeHtml(p.product_code) + ' - ' : ''}
                        ${self.formatPrice(p.price_unit)}
                    </small>
                </div>
            `;
        }).join('');

        resultsDiv.classList.remove('d-none');

        // Bind click events
        resultsDiv.querySelectorAll('.search-result').forEach(function(div) {
            div.addEventListener('click', function() {
                var product = JSON.parse(this.dataset.product);
                self.addProduct(product);
            });
        });
    };

    ChangeRequestEditor.prototype.showNoResults = function() {
        var resultsDiv = document.getElementById('search-results');
        resultsDiv.innerHTML = '<div class="p-3 text-center text-muted">No products found</div>';
        resultsDiv.classList.remove('d-none');
    };

    ChangeRequestEditor.prototype.hideSearchResults = function() {
        document.getElementById('search-results').classList.add('d-none');
    };

    ChangeRequestEditor.prototype.addProduct = function(product) {
        var existing = this.lines.find(function(l) { return l.product_id === product.product_id; });
        if (existing) {
            existing.qty += 1;
        } else {
            this.lines.push({
                product_id: product.product_id,
                product_name: product.product_name,
                product_code: product.product_code,
                qty: 1,
                price_unit: product.price_unit
            });
        }

        document.getElementById('product-search').value = '';
        this.hideSearchResults();
        this.render();
    };

    ChangeRequestEditor.prototype.submitRequest = function() {
        var self = this;
        var btn = document.getElementById('submit-btn');

        btn.disabled = true;
        btn.innerHTML = '<i class="fa fa-spinner fa-spin me-1"></i> Submitting...';

        var requestedLines = this.lines
            .filter(function(l) { return l.qty > 0; })
            .map(function(l) { return { product_id: l.product_id, qty: l.qty }; });

        this.rpc('/rental_portal/jsonrpc/change_request/submit', {
            order_id: this.orderId,
            lines: requestedLines,
            note: this.note
        })
        .then(function(result) {
            if (result.success) {
                self.showSuccess('Change request submitted successfully! Redirecting...');
                setTimeout(function() {
                    window.location.href = '/my/rentals/' + self.orderId;
                }, 1500);
            } else {
                self.showErrorMessage(result.error || 'Failed to submit request');
                btn.disabled = false;
                btn.innerHTML = '<i class="fa fa-paper-plane me-1"></i> Submit Request';
            }
        })
        .catch(function(error) {
            self.showErrorMessage('Network error: ' + error.message);
            btn.disabled = false;
            btn.innerHTML = '<i class="fa fa-paper-plane me-1"></i> Submit Request';
        });
    };

    ChangeRequestEditor.prototype.showErrorMessage = function(message) {
        var alert = document.getElementById('error-alert');
        document.getElementById('error-message').textContent = message;
        alert.classList.remove('d-none');
    };

    ChangeRequestEditor.prototype.showSuccess = function(message) {
        var alert = document.getElementById('success-alert');
        document.getElementById('success-message').textContent = message;
        alert.classList.remove('d-none');
        document.getElementById('error-alert').classList.add('d-none');
    };

})();
