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
    static template = "rental_portal.OrderLinesTable";

    formatMonetary(amount) {
        return amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
    }
}

/**
 * Quick Add by SKU Component
 */
class QuickAddBySKU extends Component {
    static template = "rental_portal.QuickAddBySKU";
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
        if (result.success) this.state.products = result.products;
    }
}

/**
 * Main App Component
 */
export class RentalChangeRequestApp extends Component {
    static template = "rental_portal.ChangeRequestApp";
    static components = { OrderLinesTable, QuickAddBySKU, CatalogPanel };

    setup() {
        this.state = useState({
            isLoading: true,
            orderId: this.props.orderId,
            changeRequestId: this.props.changeRequestId,
            order: {},
            changeRequest: null,
            lines: [],
            note: "",
            error: null,
            hasChanges: false,
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
                if (data.change_request) this.state.note = data.change_request.submission_note || "";
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
            // If no CR yet, start one
            if (!this.state.changeRequestId) {
                const startRes = await rpc("/rental_portal/jsonrpc/change_request/start", { order_id: this.state.orderId });
                if (!startRes.success) throw new Error(startRes.error);
                this.state.changeRequestId = startRes.change_request;
            }

            // Patch with current lines
            const patchRes = await rpc("/rental_portal/jsonrpc/change_request/patch", {
                change_request_id: this.state.changeRequestId,
                patch_operations: this.state.lines.map(l => ({
                    operation: l.id.toString().startsWith('temp') ? 'add' : 'update',
                    product_id: l.product_id,
                    qty: l.qty,
                    line_id: l.id.toString().startsWith('temp') ? null : l.id,
                })),
            });

            if (patchRes.success) {
                this.state.hasChanges = false;
                await this._loadData(); // Refresh IDs
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

        await mount(RentalChangeRequestApp, this.el, {
            templates,
            props: { orderId, changeRequestId },
            get env() { return {}; }
        });
    },
});
