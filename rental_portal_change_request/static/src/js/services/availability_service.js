/**
 * Availability Service
 * Manages availability checking and caching
 */

odoo.define('rental_portal.availability_service', function (require) {
    "use strict";

    var RpcService = require('rental_portal.rpc_service');

    var AvailabilityService = {
        _cache: {},
        _pendingChecks: {},

        /**
         * Check availability for products (with caching)
         */
        checkAvailability: function (productIds) {
            var self = this;
            var uncachedIds = [];

            // Return cached results
            var result = {};
            productIds.forEach(function (id) {
                var strId = String(id);
                if (self._cache[strId]) {
                    result[strId] = self._cache[strId];
                } else {
                    uncachedIds.push(id);
                }
            });

            // If all cached, return immediately
            if (uncachedIds.length === 0) {
                return $.when(result);
            }

            // Check if request is already pending
            var cacheKey = uncachedIds.sort().join(',');
            if (self._pendingChecks[cacheKey]) {
                return self._pendingChecks[cacheKey].then(function (serverResult) {
                    return _.extend({}, result, serverResult);
                });
            }

            // Make request
            var promise = RpcService.checkAvailability(uncachedIds).then(function (response) {
                if (response.success) {
                    // Update cache
                    _.each(response.availability, function (data, productId) {
                        self._cache[productId] = data;
                    });
                    return _.extend({}, result, response.availability);
                }
                return result;
            });

            self._pendingChecks[cacheKey] = promise;
            promise.always(function () {
                delete self._pendingChecks[cacheKey];
            });

            return promise.then(function (serverResult) {
                return _.extend({}, result, serverResult);
            });
        },

        /**
         * Clear availability cache
         */
        clearCache: function () {
            this._cache = {};
        },

        /**
         * Get availability status for display
         */
        getStatusInfo: function (status) {
            var statusMap = {
                'available': {
                    label: _t('Available'),
                    class: 'text-success',
                    icon: 'fa-check-circle',
                },
                'partial': {
                    label: _t('Partially Available'),
                    class: 'text-warning',
                    icon: 'fa-exclamation-circle',
                },
                'unavailable': {
                    label: _t('Unavailable'),
                    class: 'text-danger',
                    icon: 'fa-times-circle',
                },
                'unknown': {
                    label: _t('Checking...'),
                    class: 'text-muted',
                    icon: 'fa-spinner fa-spin',
                },
            };
            return statusMap[status] || statusMap['unknown'];
        },
    };

    return AvailabilityService;
});
