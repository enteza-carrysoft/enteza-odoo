/**
 * Rental Portal - Order Detail Page
 * Expand / Collapse All families accordion buttons
 */
(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        var accordion = document.getElementById('orderLinesAccordion');
        if (!accordion) return;

        var btnExpand = document.getElementById('btn-expand-all');
        var btnCollapse = document.getElementById('btn-collapse-all');

        if (btnExpand) {
            btnExpand.addEventListener('click', function () {
                accordion.querySelectorAll('.accordion-collapse').forEach(function (el) {
                    bootstrap.Collapse.getOrCreateInstance(el).show();
                });
            });
        }

        if (btnCollapse) {
            btnCollapse.addEventListener('click', function () {
                accordion.querySelectorAll('.accordion-collapse').forEach(function (el) {
                    bootstrap.Collapse.getOrCreateInstance(el).hide();
                });
            });
        }
    });
})();
