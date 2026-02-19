/** @odoo-module **/

import { Component, useState, onWillStart, mount, xml } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { templates } from "@web/core/assets";
import publicWidget from "@web/legacy/js/public/public_widget";

/**
 * Order Lines Table Component
 */
class OrderLinesTable extends Component {
    static template = xml`
        <div class="card shadow-sm">
            <div class="card-header bg-light">
                <h5 class="mb-0">Order Lines</h5>
            </div>
            <div class="table-responsive">
                <table class="table table-hover align-middle mb-0">
                    <thead class="table-light">
                        <tr>
                            <th>Product</th>
                            <th class="text-center" style="width: 120px;">Qty</th>
                            <th class="text-end">Price</th>
                            <th class="text-end">Subtotal</th>
                            <th class="text-center">Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr t-foreach="props.lines" t-as="line" t-key="line.id">
                            <td>
                                <div><strong t-esc="line.product_name"/></div>
                                <small class="text-muted" t-if="line.product_code">SKU: <t t-esc="line.product_code"/></small>
                            </td>
                            <td>
                                <input type="number" class="form-control form-control-sm text-center" 
                                       t-att-value="line.qty" 
                                       t-on-change="(ev) => this.onQtyChange(ev, line.id)"/>
                            </td>
                            <td class="text-end">
                                <t t-esc="props.formatMonetary(line.price_unit)"/>
                            </td>
                            <td class="text-end">
                                <t t-esc="props.formatMonetary(line.qty * line.price_unit)"/>
                            </td>
                            <td class="text-center">
                                <button class="btn btn-link text-danger p-0" t-on-click="() => props.onLineRemove(line.id)">
                                    <i class="fa fa-trash"/>
                                </button>
                            </td>
                        </tr>
                        <tr t-if="props.lines.length === 0">
                            <td colspan="5" class="text-center py-4 text-muted">
                                No products added. Use search or catalog to add items.
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    `;
    onQtyChange(ev, lineId) {
        if (this.props.onLineUpdate) {
            this.props.onLineUpdate(lineId, { qty: parseFloat(ev.target.value) });
        }
    }
}

/**
 * Quick Add by SKU Component
 */
class QuickAddBySKU extends Component {
    static template = xml`
        <div class="card mb-3 shadow-sm border-primary">
            <div class="card-body">
                <h6 class="card-title">Quick Add (SKU)</h6>
                <div class="input-group">
                    <input type="text" class="form-control" placeholder="Type SKU..." t-att-value="state.sku" t-on-input="onInput" t-on-keydown="onKeydown"/>
                    <button class="btn btn-primary" t-on-click="onSearch">
                        <i class="fa fa-plus"/>
                    </button>
                </div>
                <div t-if="state.finding" class="mt-1 small text-info">Searching...</div>
                <div t-if="state.notFound" class="mt-1 small text-danger">SKU not found</div>
            </div>
        </div>
    `;
    setup() {
        this.state = useState({ sku: "", finding: false, notFound: false });
    }
    async onSearch() {
        if (!this.state.sku) return;
        this.state.finding = true;
        this.state.notFound = false;
        try {
            const result = await rpc("/rental_portal/jsonrpc/catalog/search", {
                search_term: this.state.sku,
                limit: 1
            });
            if (result.success && result.products.length > 0) {
                this.props.onProductAdded(result.products[0]);
                this.state.sku = "";
            } else {
                this.state.notFound = true;
            }
        } catch (e) {
            this.state.notFound = true;
        } finally {
            this.state.finding = false;
        }
    }
    onKeydown(ev) {
        if (ev.key === "Enter") this.onSearch();
    }
    onInput(ev) {
        this.state.sku = ev.target.value;
    }
}

/**
 * Catalog Panel Component
 */
class CatalogPanel extends Component {
    static template = xml`
        <div class="card shadow-sm mt-3">
            <div class="card-header bg-primary text-white">
                <h6 class="mb-0">Product Catalog</h6>
            </div>
            <div class="card-body">
                <input type="text" class="form-control mb-3" placeholder="Search..." t-on-input="onSearch"/>
                <div class="list-group list-group-flush overflow-auto" style="max-height: 400px;">
                    <button t-foreach="state.products" t-as="p" t-key="p.product_id"
                            class="list-group-item list-group-item-action py-2"
                            t-on-click="() => props.onProductAdded(p)">
                        <div class="d-flex justify-content-between">
                            <span t-esc="p.product_name"/>
                            <span class="text-primary fw-bold" t-esc="p.price_unit + ' €'"/>
                        </div>
                        <small class="text-muted" t-esc="p.product_code"/>
                    </button>
                </div>
            </div>
        </div>
    `;
    setup() {
        this.state = useState({ products: [], loading: false });
        onWillStart(() => this.search(""));
    }
    async onSearch(ev) {
        this.search(ev.target.value);
    }
    async search(term) {
        const result = await rpc("/rental_portal/jsonrpc/catalog/search", { search_term: term });
        if (result.success) {
            // Defensive mapping for old/new Python fields
            this.state.products = (result.products || []).map(p => ({
                product_id: p.product_id || p.id,
                product_name: p.product_name || p.name || 'Unknown Product',
                product_code: p.product_code || p.default_code || '',
                price_unit: p.price_unit || p.lst_price || 0,
            }));
        }
    }
}

/**
 * Main App Component
 */
export class RentalChangeRequestApp extends Component {
    static template = xml`
        <div class="rental_change_request_app container-fluid">
            <!-- Header -->
            <div class="d-flex justify-content-between align-items-center mb-3">
                <div>
                    <h4 class="mb-0">
                        <t t-if="state.changeRequest">
                            Edit Change Request <t t-esc="state.changeRequest.name"/>
                        </t>
                        <t t-else="">
                            New Change Request for <t t-esc="state.order.name"/>
                        </t>
                    </h4>
                    <small class="text-muted">Order: <t t-esc="state.order.name"/></small>
                </div>
                <div class="status_indicator">
                    <span class="badge" t-att-class="getStatusClass()">
                        <t t-esc="state.changeRequest ? state.changeRequest.state : 'draft'"/>
                    </span>
                </div>
            </div>

            <!-- Error handling -->
            <div t-if="state.error" class="alert alert-danger alert-dismissible fade show" role="alert">
                <t t-esc="state.error"/>
                <button type="button" class="btn-close" t-on-click="() => state.error = null" aria-label="Close"></button>
            </div>

            <!-- Loading Spinner -->
            <div t-if="state.isLoading" class="text-center py-5">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
            </div>

            <!-- Main App Content -->
            <div t-else="" class="row">
                <div class="col-lg-8">
                    <!-- Lines Table Component -->
                    <OrderLinesTable lines="state.lines" onLineUpdate="this.onLineUpdate" onLineRemove="this.onLineRemove" formatMonetary="this.formatMonetary"/>
                    
                    <!-- Submission Note -->
                    <div class="card mt-3">
                        <div class="card-body">
                            <h5 class="card-title">Notes</h5>
                            <textarea class="form-control" t-att-value="state.note" t-on-input="onInput" rows="3" placeholder="Add a note..."></textarea>
                        </div>
                    </div>

                    <!-- Footer Actions -->
                    <div class="d-flex justify-content-between mt-4 mb-5">
                        <button class="btn btn-secondary" t-on-click="onCancel">Cancel</button>
                        <div class="d-flex gap-2">
                            <button class="btn btn-outline-primary" t-on-click="onSaveDraft" t-att-disabled="!state.hasChanges">Save Draft</button>
                            <button class="btn btn-primary" t-on-click="onSubmit" t-att-disabled="state.lines.length === 0">Submit for Approval</button>
                        </div>
                    </div>
                </div>

                <div class="col-lg-4">
                    <!-- Right Sidebar: Quick Add & Catalog -->
                    <div class="sticky-top" style="top: 20px;">
                        <QuickAddBySKU onProductAdded="this.onProductAdded"/>
                        <CatalogPanel onProductAdded="this.onProductAdded"/>
                    </div>
                </div>
            </div>
        </div>
    `;
    static components = { OrderLinesTable, QuickAddBySKU, CatalogPanel };

    setup() {
        this.state = useState({
            isLoading: true,
            orderId: this.props.orderId,
            changeRequestId: this.props.changeRequestId,
            order: {},
            changeRequest: null,
            lines: [],
            originalLines: [], // Track original lines to detect removals
            note: "",
            error: null,
            hasChanges: false,
            order_token: null,
            revision_token: null,
        });

        onWillStart(async () => {
            await this._loadData();
        });
    }

    async _loadData() {
        try {
            const data = await rpc("/rental_portal/jsonrpc/change_request/load", {
                change_request_id: this.state.changeRequestId,
                order_id: this.state.orderId,
            });

            if (data.success) {
                this.state.order = data.order;
                this.state.changeRequest = data.change_request;
                this.state.lines = data.lines || [];
                // Store a copy of original lines to track removals
                this.state.originalLines = JSON.parse(JSON.stringify(data.lines || []));
                if (data.change_request) {
                    this.state.note = data.change_request.submission_note || "";
                    this.state.revision_token = data.change_request.expected_revision_write_date;
                    this.state.order_token = data.change_request.expected_order_write_date;
                } else if (data.order) {
                    this.state.order_token = data.order.write_date;
                }
            } else {
                this.state.error = data.error;
            }
        } catch (e) {
            this.state.error = _t("Connection error.");
        } finally {
            this.state.isLoading = false;
        }
    }

    onLineUpdate(lineId, updates) {
        const line = this.state.lines.find(l => l.id === lineId);
        if (line) {
            Object.assign(line, updates);
            this.state.hasChanges = true;
        }
    }

    onLineRemove(lineId) {
        this.state.lines = this.state.lines.filter(l => l.id !== lineId);
        this.state.hasChanges = true;
    }

    onProductAdded(product) {
        const existing = this.state.lines.find(l => l.product_id === product.product_id);
        if (existing) {
            existing.qty += 1;
        } else {
            this.state.lines.push({
                id: 'temp_' + Date.now(),
                product_id: product.product_id,
                product_name: product.product_name,
                product_code: product.product_code,
                qty: 1,
                price_unit: product.price_unit,
            });
        }
        this.state.hasChanges = true;
    }

    onInput(ev) {
        this.state.note = ev.target.value;
    }

    formatMonetary(amount) {
        return amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
    }

    getStatusClass() {
        const state = this.state.changeRequest ? this.state.changeRequest.state : 'draft';
        const classes = {
            draft: 'bg-secondary',
            editing: 'bg-info',
            submitted: 'bg-warning text-dark',
            approved: 'bg-success',
            rejected: 'bg-danger',
        };
        return classes[state] || 'bg-light text-dark';
    }

    async onSaveDraft() {
        this.state.isLoading = true;
        try {
            // Store current user edits before any API calls
            const userEditedLines = JSON.parse(JSON.stringify(this.state.lines));

            // If no CR yet, start one
            if (!this.state.changeRequestId) {
                const startRes = await rpc("/rental_portal/jsonrpc/change_request/start", { order_id: this.state.orderId });
                if (!startRes.success) throw new Error(startRes.error);
                this.state.changeRequestId = startRes.change_request;
                this.state.order_token = startRes.order_write_date;
                this.state.revision_token = startRes.revision_write_date;
            }

            // Build patch operations based on user edits
            // We use product_id to identify lines (more robust than line_id mapping)
            const patchOperations = [];

            // Build set of current product_ids
            const currentProductIds = new Set(userEditedLines.map(l => l.product_id));

            // Find removed products (were in original but not in current)
            for (const origLine of this.state.originalLines) {
                if (!currentProductIds.has(origLine.product_id)) {
                    patchOperations.push({
                        operation: 'remove',
                        product_id: origLine.product_id,
                    });
                }
            }

            // Build set of original product_ids
            const originalProductIds = new Set(this.state.originalLines.map(l => l.product_id));

            // Add/update operations for current lines
            for (const line of userEditedLines) {
                if (!originalProductIds.has(line.product_id)) {
                    // New product - add operation
                    patchOperations.push({
                        operation: 'add',
                        product_id: line.product_id,
                        qty: line.qty,
                    });
                } else {
                    // Existing product - update operation
                    patchOperations.push({
                        operation: 'update',
                        product_id: line.product_id,
                        qty: line.qty,
                    });
                }
            }

            // Patch with operations
            const patchRes = await rpc("/rental_portal/jsonrpc/change_request/patch", {
                change_request_id: this.state.changeRequestId,
                patch_operations: patchOperations,
                token_order: this.state.order_token,
                token_revision: this.state.revision_token,
            });

            if (patchRes.success) {
                this.state.hasChanges = false;
                this.state.revision_token = patchRes.new_revision_token;
                await this._loadData(); // Refresh data
            } else {
                this.state.error = patchRes.error;
            }
        } catch (e) {
            this.state.error = e.message;
        } finally {
            this.state.isLoading = false;
        }
    }

    async onSubmit() {
        await this.onSaveDraft();
        if (this.state.error) return;

        this.state.isLoading = true;
        try {
            const res = await rpc("/rental_portal/jsonrpc/change_request/submit", {
                change_request_id: this.state.changeRequestId,
                note: this.state.note
            });
            if (res.success) {
                window.location.href = `/my/rentals/${this.state.orderId}`;
            } else {
                this.state.error = res.error;
            }
        } catch (e) {
            this.state.error = e.message;
        } finally {
            this.state.isLoading = false;
        }
    }

    onCancel() {
        window.location.href = `/my/rentals/${this.state.orderId}`;
    }
}

/**
 * Public Widget to mount OWL App
 */
publicWidget.registry.RentalChangeRequestApp = publicWidget.Widget.extend({
    selector: '#rental_change_request_app',

    async start() {
        const orderId = parseInt(this.el.dataset.orderId);
        const changeRequestId = parseInt(this.el.dataset.changeRequestId);

        // Clear the loading indicator
        this.el.innerHTML = '';

        await mount(RentalChangeRequestApp, this.el, {
            templates,
            props: { orderId, changeRequestId },
            get env() { return {}; }
        });
    },
});
