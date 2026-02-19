/**
 * Status Indicator Component
 * Displays change request state with appropriate styling
 */

odoo.define('rental_portal.components.status_indicator', function (require) {
    "use strict";

    var core = require('web.core');
    var Widget = require('web.Widget');

    var _t = core._t;

    var StatusIndicator = Widget.extend({
        template: 'rental_portal.StatusIndicator',

        init: function (parent, state) {
            this._super(parent);
            this.state = state;
        },

        /**
         * Get state configuration
         */
        getStateInfo: function () {
            var stateMap = {
                'draft': {
                    label: _t('Draft'),
                    class: 'bg-secondary',
                    icon: 'fa-file',
                },
                'editing': {
                    label: _t('Editing'),
                    class: 'bg-info',
                    icon: 'fa-edit',
                },
                'submitted': {
                    label: _t('Submitted'),
                    class: 'bg-warning',
                    icon: 'fa-paper-plane',
                },
                'approved': {
                    label: _t('Approved'),
                    class: 'bg-success',
                    icon: 'fa-check',
                },
                'rejected': {
                    label: _t('Rejected'),
                    class: 'bg-danger',
                    icon: 'fa-times',
                },
                'cancelled': {
                    label: _t('Cancelled'),
                    class: 'bg-dark',
                    icon: 'fa-ban',
                },
                'applied': {
                    label: _t('Applied'),
                    class: 'bg-primary',
                    icon: 'fa-check-circle',
                },
            };
            return stateMap[this.state] || stateMap['draft'];
        },
    });

    return StatusIndicator;
});
