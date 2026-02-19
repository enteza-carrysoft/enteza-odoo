/**
 * Rental Portal RPC Service
 * Custom JSON-RPC service for change request operations
 */

odoo.define('rental_portal.rpc_service', function (require) {
    "use strict";

    var rpc = require('web.rpc');

    var RentalRpcService = {
        /**
         * Call JSON-RPC endpoint
         */
        call: function (endpoint, params) {
            return rpc.query({
                route: endpoint,
                params: params,
            });
        },

        /**
         * Start a new change request
         */
        startChangeRequest: function (orderId) {
            return this.call('/rental_portal/jsonrpc/change_request/start', {
                order_id: orderId,
            });
        },

        /**
         * Apply patch to revision order
         */
        patchRevision: function (changeRequestId, patchOperations, tokenOrder, tokenRevision) {
            return this.call('/rental_portal/jsonrpc/change_request/patch', {
                change_request_id: changeRequestId,
                patch_operations: patchOperations,
                token_order: tokenOrder,
                token_revision: tokenRevision,
            });
        },

        /**
         * Submit change request
         */
        submitChangeRequest: function (changeRequestId, note) {
            return this.call('/rental_portal/jsonrpc/change_request/submit', {
                change_request_id: changeRequestId,
                note: note || '',
            });
        },

        /**
         * Cancel change request
         */
        cancelChangeRequest: function (changeRequestId) {
            return this.call('/rental_portal/jsonrpc/change_request/cancel', {
                change_request_id: changeRequestId,
            });
        },

        /**
         * Load change request data
         */
        loadChangeRequest: function (changeRequestId, orderId) {
            return this.call('/rental_portal/jsonrpc/change_request/load', {
                change_request_id: changeRequestId,
                order_id: orderId,
            });
        },

        /**
         * Search catalog products
         */
        searchCatalog: function (searchTerm, limit, offset) {
            return this.call('/rental_portal/jsonrpc/catalog/search', {
                search_term: searchTerm || '',
                limit: limit || 20,
                offset: offset || 0,
            });
        },

        /**
         * Check product availability
         */
        checkAvailability: function (productIds) {
            return this.call('/rental_portal/jsonrpc/catalog/check_availability', {
                product_ids: productIds,
            });
        },
    };

    return RentalRpcService;
});
