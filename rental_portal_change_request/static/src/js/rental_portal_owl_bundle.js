/** @odoo-module **/
/**
 * Simplified Rental Portal Change Request Editor
 *
 * Simple flow:
 * 1. Load original order lines
 * 2. User edits (change qty, add, remove)
 * 3. Submit - sends desired lines to backend
 * 4. Backend calculates diff and creates change request
 */

import { Component, useState, onWillStart } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";

// ============================================================================
// ORDER LINES TABLE - Editable table of order lines
// ============================================================================

class OrderLinesTable extends Component {
    static template = "rental_portal.OrderLinesTable";
    static props = {
        lines: { type: Array },
        onUpdate: { type: Function },
        onRemove: { type: Function },
        readonly: { type: Boolean, optional: true },
    };

    onQtyChange(line, ev) {
        const newQty = parseFloat(ev.target.value) || 0;
        this.props.onUpdate(line.product_id, { qty: newQty });
    }

    onRemoveClick(line) {
        this.props.onRemove(line.product_id);
    }

    formatPrice(amount) {
        return amount.toFixed(2) + ' €';
    }
}

OrderLinesTable.template = owl.xml`
<table class="table table-sm table-hover">
    <thead class="table-light">
        <tr>
            <th>Product</th>
            <th class="text-center" style="width: 120px;">Qty</th>
            <th class="text-end" style="width: 100px;">Price</th>
            <th class="text-end" style="width: 120px;">Subtotal</th>
            <th t-if="!props.readonly" style="width: 50px;"></th>
        </tr>
    </thead>
    <tbody>
        <tr t-foreach="props.lines" t-as="line" t-key="line.product_id">
            <td>
                <strong t-esc="line.product_name"/>
                <small t-if="line.product_code" class="text-muted d-block">
                    SKU: <t t-esc="line.product_code"/>
                </small>
            </td>
            <td class="text-center">
                <input t-if="!props.readonly"
                       type="number"
                       class="form-control form-control-sm text-center"
                       t-att-value="line.qty"
                       min="0.01"
                       step="1"
                       t-on-change="(ev) => this.onQtyChange(line, ev)"/>
                <span t-else="" t-esc="line.qty"/>
            </td>
            <td class="text-end" t-esc="formatPrice(line.price_unit)"/>
            <td class="text-end" t-esc="formatPrice(line.qty * line.price_unit)"/>
            <td t-if="!props.readonly" class="text-center">
                <button class="btn btn-sm btn-outline-danger"
                        t-on-click="() => this.onRemoveClick(line)"
                        title="Remove">
                    <i class="fa fa-trash"/>
                </button>
            </td>
        </tr>
        <tr t-if="props.lines.length === 0">
            <td colspan="5" class="text-center text-muted py-4">
                No items in order
            </td>
        </tr>
    </tbody>
    <tfoot class="table-light">
        <tr>
            <td colspan="3" class="text-end"><strong>Total:</strong></td>
            <td class="text-end">
                <strong t-esc="formatPrice(props.lines.reduce((sum, l) => sum + l.qty * l.price_unit, 0))"/>
            </td>
            <td t-if="!props.readonly"/>
        </tr>
    </tfoot>
</table>
`;

// ============================================================================
// PRODUCT SEARCH - Search and add products
// ============================================================================

class ProductSearch extends Component {
    static template = "rental_portal.ProductSearch";
    static props = {
        onProductAdd: { type: Function },
    };

    setup() {
        this.state = useState({
            searchTerm: '',
            results: [],
            isSearching: false,
            showResults: false,
        });
    }

    async onSearchInput(ev) {
        const term = ev.target.value;
        this.state.searchTerm = term;

        if (term.length < 2) {
            this.state.results = [];
            this.state.showResults = false;
            return;
        }

        this.state.isSearching = true;
        try {
            const res = await rpc('/rental_portal/jsonrpc/catalog/search', {
                search_term: term,
                limit: 10,
            });
            if (res.success) {
                this.state.results = res.products;
                this.state.showResults = true;
            }
        } catch (e) {
            console.error('Search error:', e);
        } finally {
            this.state.isSearching = false;
        }
    }

    onProductClick(product) {
        this.props.onProductAdd(product);
        this.state.searchTerm = '';
        this.state.results = [];
        this.state.showResults = false;
    }

    onBlur() {
        // Delay to allow click on result
        setTimeout(() => {
            this.state.showResults = false;
        }, 200);
    }
}

ProductSearch.template = owl.xml`
<div class="position-relative mb-3">
    <div class="input-group">
        <span class="input-group-text">
            <i class="fa fa-search"/>
        </span>
        <input type="text"
               class="form-control"
               placeholder="Search products by name or SKU..."
               t-att-value="state.searchTerm"
               t-on-input="onSearchInput"
               t-on-blur="onBlur"/>
        <span t-if="state.isSearching" class="input-group-text">
            <i class="fa fa-spinner fa-spin"/>
        </span>
    </div>
    <div t-if="state.showResults and state.results.length > 0"
         class="position-absolute w-100 bg-white border rounded shadow-sm mt-1"
         style="z-index: 1000; max-height: 300px; overflow-y: auto;">
        <div t-foreach="state.results" t-as="product" t-key="product.product_id"
             class="p-2 border-bottom cursor-pointer hover-bg-light"
             style="cursor: pointer;"
             t-on-click="() => this.onProductClick(product)">
            <div class="fw-bold" t-esc="product.product_name"/>
            <small class="text-muted">
                <span t-if="product.product_code" t-esc="'SKU: ' + product.product_code + ' - '"/>
                <span t-esc="product.price_unit.toFixed(2) + ' €'"/>
            </small>
        </div>
    </div>
    <div t-if="state.showResults and state.results.length === 0 and state.searchTerm.length >= 2"
         class="position-absolute w-100 bg-white border rounded shadow-sm mt-1 p-3 text-center text-muted"
         style="z-index: 1000;">
        No products found
    </div>
</div>
`;

// ============================================================================
// MAIN APP - Change Request Editor
// ============================================================================

export class RentalChangeRequestApp extends Component {
    static template = "rental_portal.RentalChangeRequestApp";
    static components = { OrderLinesTable, ProductSearch };
    static props = {
        orderId: { type: Number },
    };

    setup() {
        this.state = useState({
            isLoading: true,
            isSaving: false,
            order: null,
            lines: [],
            originalLines: [],
            note: '',
            error: null,
            successMessage: null,
        });

        onWillStart(async () => {
            await this.loadOrder();
        });
    }

    async loadOrder() {
        this.state.isLoading = true;
        this.state.error = null;

        try {
            const res = await rpc('/rental_portal/jsonrpc/order/load', {
                order_id: this.props.orderId,
            });

            if (res.success) {
                this.state.order = res.order;
                this.state.lines = res.lines;
                // Keep a copy of original for comparison
                this.state.originalLines = JSON.parse(JSON.stringify(res.lines));
            } else {
                this.state.error = res.error;
            }
        } catch (e) {
            this.state.error = _t('Failed to load order data');
        } finally {
            this.state.isLoading = false;
        }
    }

    onLineUpdate(productId, updates) {
        const line = this.state.lines.find(l => l.product_id === productId);
        if (line) {
            Object.assign(line, updates);
        }
    }

    onLineRemove(productId) {
        this.state.lines = this.state.lines.filter(l => l.product_id !== productId);
    }

    onProductAdd(product) {
        // Check if product already exists
        const existing = this.state.lines.find(l => l.product_id === product.product_id);
        if (existing) {
            existing.qty += 1;
        } else {
            this.state.lines.push({
                product_id: product.product_id,
                product_name: product.product_name,
                product_code: product.product_code,
                qty: 1,
                price_unit: product.price_unit,
            });
        }
    }

    onNoteChange(ev) {
        this.state.note = ev.target.value;
    }

    get hasChanges() {
        if (this.state.lines.length !== this.state.originalLines.length) {
            return true;
        }

        const origMap = {};
        for (const l of this.state.originalLines) {
            origMap[l.product_id] = l.qty;
        }

        for (const l of this.state.lines) {
            if (!(l.product_id in origMap) || origMap[l.product_id] !== l.qty) {
                return true;
            }
        }

        return false;
    }

    async onSubmit() {
        if (!this.hasChanges) {
            this.state.error = _t('No changes to submit');
            return;
        }

        this.state.isSaving = true;
        this.state.error = null;

        try {
            // Build requested lines (only product_id and qty)
            const requestedLines = this.state.lines
                .filter(l => l.qty > 0)
                .map(l => ({
                    product_id: l.product_id,
                    qty: l.qty,
                }));

            const res = await rpc('/rental_portal/jsonrpc/change_request/submit', {
                order_id: this.props.orderId,
                lines: requestedLines,
                note: this.state.note,
            });

            if (res.success) {
                this.state.successMessage = _t('Change request submitted successfully!');
                // Redirect after short delay
                setTimeout(() => {
                    window.location.href = '/my/rentals/' + this.props.orderId;
                }, 1500);
            } else {
                this.state.error = res.error;
            }
        } catch (e) {
            this.state.error = _t('Failed to submit change request');
        } finally {
            this.state.isSaving = false;
        }
    }

    onCancel() {
        window.location.href = '/my/rentals/' + this.props.orderId;
    }
}

RentalChangeRequestApp.template = owl.xml`
<div class="container py-4">
    <!-- Header -->
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h2>
            <i class="fa fa-edit me-2"/>
            Request Changes
            <small t-if="state.order" class="text-muted ms-2" t-esc="'- ' + state.order.name"/>
        </h2>
        <a t-att-href="'/my/rentals/' + props.orderId" class="btn btn-outline-secondary">
            <i class="fa fa-arrow-left me-1"/> Back to Order
        </a>
    </div>

    <!-- Loading -->
    <div t-if="state.isLoading" class="text-center py-5">
        <i class="fa fa-spinner fa-spin fa-3x text-primary"/>
        <p class="mt-3">Loading order data...</p>
    </div>

    <!-- Error Alert -->
    <div t-if="state.error" class="alert alert-danger alert-dismissible fade show">
        <i class="fa fa-exclamation-circle me-2"/>
        <t t-esc="state.error"/>
        <button type="button" class="btn-close" t-on-click="() => state.error = null"/>
    </div>

    <!-- Success Alert -->
    <div t-if="state.successMessage" class="alert alert-success">
        <i class="fa fa-check-circle me-2"/>
        <t t-esc="state.successMessage"/>
    </div>

    <!-- Main Content -->
    <div t-if="!state.isLoading and !state.successMessage" class="row">
        <!-- Left Column - Lines -->
        <div class="col-lg-8">
            <div class="card mb-4">
                <div class="card-header">
                    <h5 class="mb-0">Order Lines</h5>
                </div>
                <div class="card-body">
                    <OrderLinesTable
                        lines="state.lines"
                        onUpdate.bind="onLineUpdate"
                        onRemove.bind="onLineRemove"
                        readonly="false"/>
                </div>
            </div>

            <!-- Note -->
            <div class="card mb-4">
                <div class="card-header">
                    <h5 class="mb-0">Message (optional)</h5>
                </div>
                <div class="card-body">
                    <textarea
                        class="form-control"
                        rows="3"
                        placeholder="Add a note explaining your requested changes..."
                        t-att-value="state.note"
                        t-on-input="onNoteChange"/>
                </div>
            </div>

            <!-- Actions -->
            <div class="d-flex gap-2 justify-content-end">
                <button class="btn btn-outline-secondary" t-on-click="onCancel">
                    Cancel
                </button>
                <button class="btn btn-primary"
                        t-on-click="onSubmit"
                        t-att-disabled="state.isSaving or !hasChanges">
                    <i t-if="state.isSaving" class="fa fa-spinner fa-spin me-1"/>
                    <i t-else="" class="fa fa-paper-plane me-1"/>
                    Submit Request
                </button>
            </div>
        </div>

        <!-- Right Column - Add Products -->
        <div class="col-lg-4">
            <div class="card sticky-top" style="top: 20px;">
                <div class="card-header">
                    <h5 class="mb-0">
                        <i class="fa fa-plus-circle me-2"/>
                        Add Products
                    </h5>
                </div>
                <div class="card-body">
                    <ProductSearch onProductAdd.bind="onProductAdd"/>
                    <small class="text-muted">
                        Search by product name or SKU code to add items to your order.
                    </small>
                </div>
            </div>
        </div>
    </div>
</div>
`;

// Mount the app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('rental-change-request-app');
    if (container) {
        const orderId = parseInt(container.dataset.orderId, 10);
        if (orderId) {
            const { mount } = owl;
            mount(RentalChangeRequestApp, container, { props: { orderId } });
        }
    }
});
