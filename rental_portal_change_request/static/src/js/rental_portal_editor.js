/**
 * Rental Portal Change Request Editor
 *
 * Vanilla JS editor (no OWL/ES6 modules).
 * Features:
 *  - Navigable category tree (accordion by family)
 *  - Live debounced search by name or SKU
 *  - Quick-add by exact SKU
 *  - Smart partial re-render (no full page rebuild on add/remove)
 */
(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        var container = document.getElementById('rental-change-request-app');
        if (!container) return;
        var orderId = parseInt(container.dataset.orderId, 10);
        if (!orderId) return;
        new ChangeRequestEditor(container, orderId);
    });

    // =========================================================================
    // Constructor
    // =========================================================================

    function ChangeRequestEditor(container, orderId) {
        this.container = container;
        this.orderId = orderId;

        // Order state
        this.order = null;
        this.lines = [];
        this.originalLines = [];
        this.note = '';

        // Catalog state
        this.categories = [];           // flat list from server
        this.categoryTree = [];         // nested tree built from flat list
        this.expandedCategories = {};   // {catId: true} for accordion state
        this.selectedCategoryId = null; // currently selected category
        this.searchTerm = '';           // current text search
        this.catalogProducts = [];      // loaded products in right panel
        this.catalogLoading = false;
        this.catalogTotalCount = 0;
        this.searchDebounceTimer = null;

        this.init();
    }

    ChangeRequestEditor.prototype.init = function () {
        this.loadOrder();
    };

    // =========================================================================
    // Load order + categories
    // =========================================================================

    ChangeRequestEditor.prototype.loadOrder = function () {
        var self = this;
        this.showLoading();

        Promise.all([
            this.rpc('/rental_portal/jsonrpc/order/load', { order_id: this.orderId }),
            this.rpc('/rental_portal/jsonrpc/catalog/categories', {})
        ]).then(function (results) {
            var orderResult = results[0];
            var categoriesResult = results[1];

            if (!orderResult.success) {
                self.showError(orderResult.error || 'Failed to load order');
                return;
            }

            self.order = orderResult.order;
            self.lines = orderResult.lines;
            self.originalLines = JSON.parse(JSON.stringify(orderResult.lines));

            if (categoriesResult.success) {
                self.categories = categoriesResult.categories;
                self.categoryTree = self.buildCategoryTree(categoriesResult.categories);
            }

            self.render();
        }).catch(function (error) {
            self.showError('Network error: ' + error.message);
        });
    };

    // =========================================================================
    // Category tree builder
    // =========================================================================

    ChangeRequestEditor.prototype.buildCategoryTree = function (flatList) {
        var byId = {};
        flatList.forEach(function (c) {
            byId[c.id] = {
                id: c.id,
                name: c.name,
                parent_id: c.parent_id,
                product_count: c.product_count,
                children: []
            };
        });

        var roots = [];
        flatList.forEach(function (c) {
            if (c.parent_id && byId[c.parent_id]) {
                byId[c.parent_id].children.push(byId[c.id]);
            } else {
                roots.push(byId[c.id]);
            }
        });

        // Sort recursively by name
        function sort(nodes) {
            nodes.sort(function (a, b) { return a.name.localeCompare(b.name); });
            nodes.forEach(function (n) { sort(n.children); });
        }
        sort(roots);

        return roots;
    };

    ChangeRequestEditor.prototype.renderCategoryTreeHtml = function (nodes, level) {
        if (!nodes || nodes.length === 0) return '';
        var self = this;
        var html = '';

        nodes.forEach(function (node) {
            var isExpanded = !!self.expandedCategories[node.id];
            var hasChildren = node.children && node.children.length > 0;
            var isSelected = self.selectedCategoryId === node.id && !self.searchTerm;
            var indent = (level * 14 + 8) + 'px';

            var chevronIcon = hasChildren
                ? (isExpanded ? 'fa-chevron-down' : 'fa-chevron-right')
                : 'fa-minus';
            var chevronStyle = hasChildren ? '' : 'opacity:0.3;';

            var bgClass = isSelected
                ? 'bg-primary text-white'
                : 'text-dark cat-item-hover';

            html += '<div class="cat-item d-flex align-items-center justify-content-between border-bottom ' + bgClass + '"'
                + ' style="padding-left:' + indent + '; padding-right:6px; cursor:pointer; font-size:0.78rem; min-height:30px;"'
                + ' data-cat-id="' + node.id + '"'
                + ' data-has-children="' + (hasChildren ? '1' : '0') + '">'
                + '<span class="text-truncate me-1">'
                + '<i class="fa ' + chevronIcon + ' me-1" style="font-size:0.6rem; width:10px; vertical-align:middle; ' + chevronStyle + '"></i>'
                + self.escapeHtml(node.name)
                + '</span>'
                + '<span class="badge rounded-pill bg-secondary" style="font-size:0.6rem; flex-shrink:0;">'
                + node.product_count
                + '</span>'
                + '</div>';

            if (isExpanded && hasChildren) {
                html += self.renderCategoryTreeHtml(node.children, level + 1);
            }
        });

        return html;
    };

    // =========================================================================
    // RPC helper
    // =========================================================================

    ChangeRequestEditor.prototype.rpc = function (url, params) {
        return fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                jsonrpc: '2.0',
                method: 'call',
                params: params,
                id: Math.floor(Math.random() * 1000000)
            })
        }).then(function (r) {
            return r.json();
        }).then(function (data) {
            if (data.error) {
                throw new Error(data.error.data ? data.error.data.message : data.error.message);
            }
            return data.result;
        });
    };

    // =========================================================================
    // Utility helpers
    // =========================================================================

    ChangeRequestEditor.prototype.escapeHtml = function (text) {
        var div = document.createElement('div');
        div.textContent = String(text || '');
        return div.innerHTML;
    };

    ChangeRequestEditor.prototype.formatPrice = function (amount) {
        return (parseFloat(amount) || 0).toFixed(2) + '\u00a0\u20ac';
    };

    ChangeRequestEditor.prototype.showLoading = function () {
        this.container.innerHTML = '<div class="text-center py-5">'
            + '<i class="fa fa-spinner fa-spin fa-3x text-primary"></i>'
            + '<p class="mt-3">Loading order data...</p>'
            + '</div>';
    };

    ChangeRequestEditor.prototype.showError = function (message) {
        this.container.innerHTML = '<div class="container py-4">'
            + '<div class="alert alert-danger"><i class="fa fa-exclamation-circle me-2"></i>'
            + this.escapeHtml(message) + '</div>'
            + '<a href="/my/rentals/' + this.orderId + '" class="btn btn-outline-secondary">'
            + '<i class="fa fa-arrow-left me-1"></i> Back to Order</a>'
            + '</div>';
    };

    // =========================================================================
    // Full render (called once after load, and on hard resets)
    // =========================================================================

    ChangeRequestEditor.prototype.render = function () {
        // Build order lines HTML
        var linesHtml = this._buildLinesHtml();
        var total = this.lines.reduce(function (s, l) { return s + l.qty * l.price_unit; }, 0);

        // Build category tree HTML
        var allActive = (!this.selectedCategoryId && !this.searchTerm)
            ? 'bg-primary text-white'
            : 'text-muted cat-item-hover';
        var treeHtml = this.renderCategoryTreeHtml(this.categoryTree, 0);

        var clearBtnStyle = this.searchTerm ? '' : 'style="display:none"';

        this.container.innerHTML = ''
            + '<div class="container-fluid py-4">'

            // ── Header ──────────────────────────────────────────────────────
            + '<div class="d-flex justify-content-between align-items-center mb-4">'
            +   '<h2 class="mb-0">'
            +     '<i class="fa fa-edit me-2"></i>Request Changes'
            +     '<small class="text-muted ms-2 fs-5">&#8211; ' + this.escapeHtml(this.order.name) + '</small>'
            +   '</h2>'
            +   '<a href="/my/rentals/' + this.orderId + '" class="btn btn-outline-secondary">'
            +     '<i class="fa fa-arrow-left me-1"></i> Back to Order'
            +   '</a>'
            + '</div>'

            // ── Alerts ──────────────────────────────────────────────────────
            + '<div id="error-alert" class="alert alert-danger d-none">'
            +   '<i class="fa fa-exclamation-circle me-2"></i><span id="error-message"></span>'
            + '</div>'
            + '<div id="success-alert" class="alert alert-success d-none">'
            +   '<i class="fa fa-check-circle me-2"></i><span id="success-message"></span>'
            + '</div>'

            // ── Two columns ─────────────────────────────────────────────────
            + '<div class="row">'

            // ── LEFT: Current order lines ────────────────────────────────────
            +   '<div class="col-lg-5 mb-4">'
            +     '<div class="card" style="height:520px; display:flex; flex-direction:column;">'
            +       '<div class="card-header bg-primary text-white flex-shrink-0">'
            +         '<h5 class="mb-0"><i class="fa fa-shopping-cart me-2"></i>Current Order Lines</h5>'
            +       '</div>'
            +       '<div class="card-body p-0 flex-grow-1" style="overflow-y:auto; min-height:0;">'
            +         '<table class="table table-sm table-hover mb-0">'
            +           '<thead class="table-light sticky-top">'
            +             '<tr>'
            +               '<th>Product</th>'
            +               '<th class="text-center" style="width:85px;">Qty</th>'
            +               '<th class="text-end" style="width:75px;">Price</th>'
            +               '<th class="text-end" style="width:85px;">Subtotal</th>'
            +               '<th style="width:34px;"></th>'
            +             '</tr>'
            +           '</thead>'
            +           '<tbody id="lines-tbody">'
            +             (linesHtml || '<tr><td colspan="5" class="text-center text-muted py-4">No items in order</td></tr>')
            +           '</tbody>'
            +           '<tfoot class="table-light">'
            +             '<tr>'
            +               '<td colspan="3" class="text-end"><strong>Total:</strong></td>'
            +               '<td class="text-end"><strong id="total-amount">' + this.formatPrice(total) + '</strong></td>'
            +               '<td></td>'
            +             '</tr>'
            +           '</tfoot>'
            +         '</table>'
            +       '</div>'
            +     '</div>'
            +   '</div>'

            // ── RIGHT: Add products ─────────────────────────────────────────
            +   '<div class="col-lg-7 mb-4">'
            +     '<div class="card" style="height:520px; display:flex; flex-direction:column;">'
            +       '<div class="card-header bg-success text-white flex-shrink-0">'
            +         '<h5 class="mb-0"><i class="fa fa-plus-circle me-2"></i>Add Products</h5>'
            +       '</div>'

            // Quick SKU add bar
            +       '<div class="px-3 py-2 border-bottom bg-light flex-shrink-0">'
            +         '<div class="d-flex align-items-center gap-2">'
            +           '<i class="fa fa-barcode text-secondary fa-lg"></i>'
            +           '<input type="text" id="sku-input" class="form-control form-control-sm"'
            +                  ' placeholder="Add by exact SKU reference..." autocomplete="off"'
            +                  ' style="max-width:270px;">'
            +           '<button class="btn btn-sm btn-primary" id="btn-sku-add">'
            +             '<i class="fa fa-plus"></i> Add'
            +           '</button>'
            +           '<span id="sku-feedback" class="small"></span>'
            +         '</div>'
            +       '</div>'

            // Text search bar
            +       '<div class="px-3 py-2 border-bottom flex-shrink-0">'
            +         '<div class="input-group input-group-sm">'
            +           '<span class="input-group-text"><i class="fa fa-search"></i></span>'
            +           '<input type="text" id="product-search" class="form-control"'
            +                  ' placeholder="Search by name or SKU across all families..."'
            +                  ' value="' + this.escapeHtml(this.searchTerm) + '">'
            +           '<button class="btn btn-outline-secondary" type="button" id="btn-clear-search" ' + clearBtnStyle + '>'
            +             '<i class="fa fa-times"></i>'
            +           '</button>'
            +         '</div>'
            +       '</div>'

            // Two-panel: tree + products
            +       '<div class="d-flex flex-grow-1" style="min-height:0; overflow:hidden;">'

            //   Category tree (left panel)
            +         '<div id="category-tree" class="border-end flex-shrink-0"'
            +              ' style="width:175px; overflow-y:auto; height:100%;">'
            +           '<div class="cat-item d-flex align-items-center border-bottom ' + allActive + '"'
            +                ' style="padding:6px 8px; cursor:pointer; font-size:0.78rem; min-height:30px;"'
            +                ' data-cat-id="" data-has-children="0">'
            +             '<i class="fa fa-th me-1" style="font-size:0.7rem;"></i>'
            +             '<span>All families</span>'
            +           '</div>'
            +           treeHtml
            +         '</div>'

            //   Product results (right panel)
            +         '<div id="catalog-results" class="flex-grow-1" style="overflow-y:auto; height:100%;">'
            +           '<div class="text-center text-muted py-5 small">'
            +             '<i class="fa fa-arrow-left fa-2x d-block mb-2 opacity-50"></i>'
            +             'Select a family on the left or search above'
            +           '</div>'
            +         '</div>'
            +       '</div>'

            // Pagination footer
            +       '<div id="catalog-footer" class="px-3 py-1 border-top bg-light small text-muted flex-shrink-0 d-none">'
            +         'Showing <strong id="catalog-count">0</strong> of <strong id="catalog-total">0</strong>'
            +         '<button id="btn-load-more" class="btn btn-link btn-sm py-0 ms-2 d-none">Load more...</button>'
            +       '</div>'
            +     '</div>'
            +   '</div>'

            + '</div>' // end row

            // ── Note + Submit ────────────────────────────────────────────────
            + '<div class="row">'
            +   '<div class="col-lg-8">'
            +     '<div class="card mb-4">'
            +       '<div class="card-header">'
            +         '<h5 class="mb-0"><i class="fa fa-comment me-2"></i>Message (optional)</h5>'
            +       '</div>'
            +       '<div class="card-body">'
            +         '<textarea id="submission-note" class="form-control" rows="2"'
            +                   ' placeholder="Add a note explaining your requested changes...">'
            +           this.escapeHtml(this.note)
            +         '</textarea>'
            +       '</div>'
            +     '</div>'
            +   '</div>'
            +   '<div class="col-lg-4">'
            +     '<div class="card mb-4">'
            +       '<div class="card-header">'
            +         '<h5 class="mb-0"><i class="fa fa-paper-plane me-2"></i>Submit Request</h5>'
            +       '</div>'
            +       '<div class="card-body">'
            +         '<p class="small text-muted mb-3">Review your changes and submit for approval.</p>'
            +         '<div class="d-grid gap-2">'
            +           '<button id="submit-btn" class="btn btn-success btn-lg" disabled>'
            +             '<i class="fa fa-check me-1"></i> Submit Request'
            +           '</button>'
            +           '<a href="/my/rentals/' + this.orderId + '" class="btn btn-outline-secondary">Cancel</a>'
            +         '</div>'
            +       '</div>'
            +     '</div>'
            +   '</div>'
            + '</div>'

            + '</div>'; // end container-fluid

        this.bindEvents();
        this.updateSubmitButton();

        // Restore catalog products if they were loaded before a re-render
        if (this.catalogProducts.length > 0) {
            this.renderCatalogProducts();
        }
    };

    // =========================================================================
    // Build order lines HTML (shared by render + rerenderOrderLines)
    // =========================================================================

    ChangeRequestEditor.prototype._buildLinesHtml = function () {
        var self = this;
        return this.lines.map(function (line, index) {
            return '<tr data-product-id="' + line.product_id + '">'
                + '<td>'
                +   '<strong>' + self.escapeHtml(line.product_name) + '</strong>'
                +   (line.product_code
                        ? '<small class="text-muted d-block">SKU: ' + self.escapeHtml(line.product_code) + '</small>'
                        : '')
                + '</td>'
                + '<td class="text-center">'
                +   '<input type="number" class="form-control form-control-sm text-center line-qty"'
                +          ' value="' + line.qty + '" min="0.01" step="1" data-index="' + index + '">'
                + '</td>'
                + '<td class="text-end">' + self.formatPrice(line.price_unit) + '</td>'
                + '<td class="text-end line-subtotal">' + self.formatPrice(line.qty * line.price_unit) + '</td>'
                + '<td class="text-center">'
                +   '<button class="btn btn-sm btn-outline-danger btn-remove" data-index="' + index + '" title="Remove">'
                +     '<i class="fa fa-trash"></i>'
                +   '</button>'
                + '</td>'
                + '</tr>';
        }).join('');
    };

    // =========================================================================
    // Bind events (called after each full render)
    // =========================================================================

    ChangeRequestEditor.prototype.bindEvents = function () {
        var self = this;

        // Order line qty changes + remove buttons
        this._bindLineEvents();

        // SKU quick-add
        var skuInput = document.getElementById('sku-input');
        skuInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') { e.preventDefault(); self.handleSkuAdd(); }
        });
        document.getElementById('btn-sku-add').addEventListener('click', function () {
            self.handleSkuAdd();
        });

        // Text search (debounced)
        document.getElementById('product-search').addEventListener('input', function () {
            self.searchTerm = this.value.trim();
            var clearBtn = document.getElementById('btn-clear-search');
            if (clearBtn) clearBtn.style.display = self.searchTerm ? '' : 'none';
            self._triggerSearchDebounced();
        });

        // Clear search button
        document.getElementById('btn-clear-search').addEventListener('click', function () {
            self.searchTerm = '';
            var si = document.getElementById('product-search');
            if (si) si.value = '';
            this.style.display = 'none';
            self.catalogProducts = [];
            self.catalogTotalCount = 0;
            self._rerenderCategoryTree();
            if (self.selectedCategoryId !== null) {
                self.loadCatalog(false);
            } else {
                self._showCatalogEmpty();
            }
        });

        // Category tree clicks
        this._bindCategoryTreeEvents();

        // Note
        document.getElementById('submission-note').addEventListener('input', function () {
            self.note = this.value;
        });

        // Submit
        document.getElementById('submit-btn').addEventListener('click', function () {
            self.submitRequest();
        });
    };

    ChangeRequestEditor.prototype._bindLineEvents = function () {
        var self = this;
        this.container.querySelectorAll('.line-qty').forEach(function (input) {
            input.addEventListener('change', function () {
                var index = parseInt(this.dataset.index, 10);
                var newQty = parseFloat(this.value) || 0;
                if (newQty > 0) {
                    self.lines[index].qty = newQty;
                    self._updateLineSubtotalDOM(index);
                    self._updateTotalDOM();
                    self.updateSubmitButton();
                }
            });
        });

        this.container.querySelectorAll('.btn-remove').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var index = parseInt(this.dataset.index, 10);
                self.lines.splice(index, 1);
                self.rerenderOrderLines();
                self.updateSubmitButton();
                if (self.catalogProducts.length > 0) {
                    self.renderCatalogProducts();
                }
            });
        });
    };

    ChangeRequestEditor.prototype._bindCategoryTreeEvents = function () {
        var self = this;
        var tree = document.getElementById('category-tree');
        if (!tree) return;

        tree.querySelectorAll('.cat-item').forEach(function (item) {
            item.addEventListener('click', function () {
                var catIdStr = this.dataset.catId;
                var catId = catIdStr ? parseInt(catIdStr, 10) : null;
                var hasChildren = this.dataset.hasChildren === '1';

                // Clear text search when browsing by category
                self.searchTerm = '';
                var si = document.getElementById('product-search');
                if (si) si.value = '';
                var cb = document.getElementById('btn-clear-search');
                if (cb) cb.style.display = 'none';

                if (catId === null) {
                    // "All families" clicked
                    self.selectedCategoryId = null;
                    self.expandedCategories = {};
                    self._rerenderCategoryTree();
                    self.loadCatalog(false);
                } else {
                    // Toggle expand state for parent nodes
                    if (hasChildren) {
                        if (self.expandedCategories[catId]) {
                            delete self.expandedCategories[catId];
                        } else {
                            self.expandedCategories[catId] = true;
                        }
                    }
                    self.selectedCategoryId = catId;
                    self._rerenderCategoryTree();
                    self.loadCatalog(false);
                }
            });
        });
    };

    // =========================================================================
    // Category tree re-render (without full page rebuild)
    // =========================================================================

    ChangeRequestEditor.prototype._rerenderCategoryTree = function () {
        var tree = document.getElementById('category-tree');
        if (!tree) return;

        var allActive = (!this.selectedCategoryId && !this.searchTerm)
            ? 'bg-primary text-white'
            : 'text-muted cat-item-hover';

        tree.innerHTML =
            '<div class="cat-item d-flex align-items-center border-bottom ' + allActive + '"'
            + ' style="padding:6px 8px; cursor:pointer; font-size:0.78rem; min-height:30px;"'
            + ' data-cat-id="" data-has-children="0">'
            + '<i class="fa fa-th me-1" style="font-size:0.7rem;"></i>'
            + '<span>All families</span>'
            + '</div>'
            + this.renderCategoryTreeHtml(this.categoryTree, 0);

        this._bindCategoryTreeEvents();
    };

    // =========================================================================
    // Order lines partial re-render
    // =========================================================================

    ChangeRequestEditor.prototype.rerenderOrderLines = function () {
        var tbody = document.getElementById('lines-tbody');
        if (!tbody) { this.render(); return; }

        var html = this._buildLinesHtml();
        tbody.innerHTML = html || '<tr><td colspan="5" class="text-center text-muted py-4">No items in order</td></tr>';
        this._updateTotalDOM();
        this._bindLineEvents();
    };

    // =========================================================================
    // Debounced search
    // =========================================================================

    ChangeRequestEditor.prototype._triggerSearchDebounced = function () {
        var self = this;
        if (this.searchDebounceTimer) clearTimeout(this.searchDebounceTimer);
        if (!this.searchTerm) {
            // Cleared: reset to category view
            if (this.selectedCategoryId !== null) {
                self._rerenderCategoryTree();
                self.loadCatalog(false);
            } else {
                self._showCatalogEmpty();
            }
            return;
        }
        this.searchDebounceTimer = setTimeout(function () {
            // Search overrides category selection highlight (but keeps tree visible)
            self._rerenderCategoryTree();
            self.loadCatalog(false);
        }, 350);
    };

    // =========================================================================
    // SKU quick-add
    // =========================================================================

    ChangeRequestEditor.prototype.handleSkuAdd = function () {
        var self = this;
        var skuInput = document.getElementById('sku-input');
        var sku = (skuInput.value || '').trim();
        if (!sku) return;

        self._showSkuFeedback('Searching\u2026', 'muted');

        this.rpc('/rental_portal/jsonrpc/catalog/by_sku', { sku: sku })
            .then(function (result) {
                if (!result.success) {
                    self._showSkuFeedback('Error: ' + result.error, 'danger');
                    return;
                }
                if (result.found) {
                    var alreadyIn = self.lines.some(function (l) {
                        return l.product_id === result.product.product_id;
                    });
                    self.addProduct(result.product);
                    skuInput.value = '';
                    if (alreadyIn) {
                        self._showSkuFeedback('\u2713 Qty updated: ' + result.product.product_name, 'success');
                    } else {
                        self._showSkuFeedback('\u2713 Added: ' + result.product.product_name, 'success');
                    }
                    setTimeout(function () { self._showSkuFeedback('', ''); }, 3000);
                } else {
                    self._showSkuFeedback('\u2717 SKU not found: ' + sku, 'danger');
                }
            })
            .catch(function (error) {
                self._showSkuFeedback('Error: ' + error.message, 'danger');
            });
    };

    ChangeRequestEditor.prototype._showSkuFeedback = function (msg, type) {
        var el = document.getElementById('sku-feedback');
        if (!el) return;
        var colorMap = { success: 'text-success', danger: 'text-danger', warning: 'text-warning', muted: 'text-muted' };
        el.className = 'small ' + (colorMap[type] || '');
        el.textContent = msg;
    };

    // =========================================================================
    // Catalog load & render
    // =========================================================================

    ChangeRequestEditor.prototype.loadCatalog = function (append) {
        var self = this;
        if (this.catalogLoading) return;
        this.catalogLoading = true;

        var offset = append ? this.catalogProducts.length : 0;

        var resultsDiv = document.getElementById('catalog-results');
        if (resultsDiv && !append) {
            resultsDiv.innerHTML = '<div class="text-center py-5">'
                + '<i class="fa fa-spinner fa-spin fa-2x text-primary"></i>'
                + '<p class="mt-2 small text-muted mb-0">Loading products...</p>'
                + '</div>';
        }

        this.rpc('/rental_portal/jsonrpc/catalog/search', {
            search_term: this.searchTerm,
            category_id: this.selectedCategoryId,
            limit: 25,
            offset: offset
        }).then(function (result) {
            self.catalogLoading = false;

            if (!result.success) {
                if (resultsDiv) {
                    resultsDiv.innerHTML = '<div class="text-center text-danger py-4 small">'
                        + '<i class="fa fa-exclamation-circle me-1"></i>'
                        + self.escapeHtml(result.error || 'Error loading products')
                        + '</div>';
                }
                return;
            }

            if (append) {
                self.catalogProducts = self.catalogProducts.concat(result.products);
            } else {
                self.catalogProducts = result.products;
            }
            self.catalogTotalCount = result.total_count;
            self.renderCatalogProducts();

        }).catch(function (error) {
            self.catalogLoading = false;
            if (resultsDiv) {
                resultsDiv.innerHTML = '<div class="text-center text-danger py-4 small">'
                    + '<i class="fa fa-exclamation-circle me-1"></i>'
                    + 'Network error: ' + self.escapeHtml(error.message)
                    + '</div>';
            }
        });
    };

    ChangeRequestEditor.prototype.renderCatalogProducts = function () {
        var self = this;
        var resultsDiv = document.getElementById('catalog-results');
        if (!resultsDiv) return;

        if (this.catalogProducts.length === 0) {
            resultsDiv.innerHTML = '<div class="text-center text-muted py-5 small">'
                + '<i class="fa fa-search fa-2x d-block mb-2 opacity-50"></i>'
                + 'No products found'
                + '</div>';
            this._hideCatalogFooter();
            return;
        }

        var html = '';
        this.catalogProducts.forEach(function (p) {
            var inOrder = self.lines.some(function (l) { return l.product_id === p.product_id; });
            var btnHtml = inOrder
                ? '<button class="btn btn-sm btn-secondary" disabled style="font-size:0.7rem; padding:2px 8px;">'
                  + '<i class="fa fa-check"></i>'
                  + '</button>'
                : '<button class="btn btn-sm btn-success btn-add-product"'
                  + ' data-product-id="' + p.product_id + '"'
                  + ' style="font-size:0.7rem; padding:2px 8px;">'
                  + '<i class="fa fa-plus"></i> Add'
                  + '</button>';

            html += '<div class="d-flex align-items-center px-2 py-1 border-bottom"'
                +        ' style="font-size:0.81rem; min-height:44px;">'
                +   '<div class="flex-grow-1 me-2" style="min-width:0;">'
                +     '<div class="fw-semibold text-truncate">' + self.escapeHtml(p.product_name) + '</div>'
                +     '<div class="text-muted" style="font-size:0.7rem;">'
                +       (p.product_code ? '<span class="me-2">SKU: <strong>' + self.escapeHtml(p.product_code) + '</strong></span>' : '')
                +       (p.category_name ? '<span class="text-truncate">' + self.escapeHtml(p.category_name) + '</span>' : '')
                +     '</div>'
                +   '</div>'
                +   '<div class="text-end flex-shrink-0" style="min-width:90px;">'
                +     '<div class="text-primary fw-bold" style="font-size:0.78rem;">' + self.formatPrice(p.price_unit) + '</div>'
                +     '<div class="mt-1">' + btnHtml + '</div>'
                +   '</div>'
                + '</div>';
        });

        resultsDiv.innerHTML = html;

        // Bind add buttons using product index lookup (avoids JSON encoding issues)
        resultsDiv.querySelectorAll('.btn-add-product').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var pid = parseInt(this.dataset.productId, 10);
                var product = self.catalogProducts.find(function (p) { return p.product_id === pid; });
                if (product) self.addProduct(product);
            });
        });

        // Update footer
        var footer = document.getElementById('catalog-footer');
        var countEl = document.getElementById('catalog-count');
        var totalEl = document.getElementById('catalog-total');
        var loadMoreBtn = document.getElementById('btn-load-more');

        if (footer) footer.classList.remove('d-none');
        if (countEl) countEl.textContent = this.catalogProducts.length;
        if (totalEl) totalEl.textContent = this.catalogTotalCount;

        if (loadMoreBtn) {
            if (this.catalogProducts.length < this.catalogTotalCount) {
                loadMoreBtn.classList.remove('d-none');
                loadMoreBtn.onclick = function () { self.loadCatalog(true); };
            } else {
                loadMoreBtn.classList.add('d-none');
            }
        }
    };

    ChangeRequestEditor.prototype._showCatalogEmpty = function () {
        var el = document.getElementById('catalog-results');
        if (el) {
            el.innerHTML = '<div class="text-center text-muted py-5 small">'
                + '<i class="fa fa-arrow-left fa-2x d-block mb-2 opacity-50"></i>'
                + 'Select a family on the left or search above'
                + '</div>';
        }
        this._hideCatalogFooter();
    };

    ChangeRequestEditor.prototype._hideCatalogFooter = function () {
        var footer = document.getElementById('catalog-footer');
        if (footer) footer.classList.add('d-none');
    };

    // =========================================================================
    // DOM update helpers
    // =========================================================================

    ChangeRequestEditor.prototype._updateLineSubtotalDOM = function (index) {
        var line = this.lines[index];
        var row = this.container.querySelector('tr[data-product-id="' + line.product_id + '"]');
        if (row) {
            var cell = row.querySelector('.line-subtotal');
            if (cell) cell.textContent = this.formatPrice(line.qty * line.price_unit);
        }
    };

    ChangeRequestEditor.prototype._updateTotalDOM = function () {
        var total = this.lines.reduce(function (s, l) { return s + l.qty * l.price_unit; }, 0);
        var el = document.getElementById('total-amount');
        if (el) el.textContent = this.formatPrice(total);
    };

    // =========================================================================
    // Change detection + submit button
    // =========================================================================

    ChangeRequestEditor.prototype.hasChanges = function () {
        if (this.lines.length !== this.originalLines.length) return true;
        var origMap = {};
        this.originalLines.forEach(function (l) { origMap[l.product_id] = l.qty; });
        for (var i = 0; i < this.lines.length; i++) {
            var l = this.lines[i];
            if (!(l.product_id in origMap) || origMap[l.product_id] !== l.qty) return true;
        }
        return false;
    };

    ChangeRequestEditor.prototype.updateSubmitButton = function () {
        var btn = document.getElementById('submit-btn');
        if (btn) btn.disabled = !this.hasChanges();
    };

    // =========================================================================
    // Add product (called from catalog + SKU quick-add)
    // =========================================================================

    ChangeRequestEditor.prototype.addProduct = function (product) {
        var existing = this.lines.find(function (l) { return l.product_id === product.product_id; });
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

        // Partial re-render: only update lines table and catalog buttons
        this.rerenderOrderLines();
        this.updateSubmitButton();
        if (this.catalogProducts.length > 0) {
            this.renderCatalogProducts();
        }
    };

    // =========================================================================
    // Submit
    // =========================================================================

    ChangeRequestEditor.prototype.submitRequest = function () {
        var self = this;
        var btn = document.getElementById('submit-btn');
        btn.disabled = true;
        btn.innerHTML = '<i class="fa fa-spinner fa-spin me-1"></i> Submitting...';

        var requestedLines = this.lines
            .filter(function (l) { return l.qty > 0; })
            .map(function (l) { return { product_id: l.product_id, qty: l.qty }; });

        this.rpc('/rental_portal/jsonrpc/change_request/submit', {
            order_id: this.orderId,
            lines: requestedLines,
            note: this.note
        }).then(function (result) {
            if (result.success) {
                self._showSuccessAlert('Change request submitted successfully! Redirecting...');
                setTimeout(function () {
                    window.location.href = '/my/rentals/' + self.orderId;
                }, 1500);
            } else {
                self._showErrorAlert(result.error || 'Failed to submit request');
                btn.disabled = false;
                btn.innerHTML = '<i class="fa fa-check me-1"></i> Submit Request';
            }
        }).catch(function (error) {
            self._showErrorAlert('Network error: ' + error.message);
            btn.disabled = false;
            btn.innerHTML = '<i class="fa fa-check me-1"></i> Submit Request';
        });
    };

    ChangeRequestEditor.prototype._showErrorAlert = function (message) {
        var alert = document.getElementById('error-alert');
        var msg = document.getElementById('error-message');
        if (alert && msg) {
            msg.textContent = message;
            alert.classList.remove('d-none');
            window.scrollTo(0, 0);
        }
    };

    ChangeRequestEditor.prototype._showSuccessAlert = function (message) {
        var alert = document.getElementById('success-alert');
        var msg = document.getElementById('success-message');
        var errAlert = document.getElementById('error-alert');
        if (alert && msg) {
            msg.textContent = message;
            alert.classList.remove('d-none');
            if (errAlert) errAlert.classList.add('d-none');
        }
    };

})();
