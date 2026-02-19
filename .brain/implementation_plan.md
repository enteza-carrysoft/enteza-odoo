# Rental Portal Change Request (Odoo 19) - Feature Implementation Plan

## Goal
Implement the full "Change Request + Revision" workflow as specified in the analysis document, ensuring compatibility with Odoo 19 and a responsive UI for customers.

### Frontend (Odoo 19 / OWL 2)
The frontend has been refactored to modern OWL 2 to resolve loading issues in the Odoo 19 portal.

#### [MODIFY] [rental_portal_owl_bundle.js](file:///d:/apps/AI/enteza-odoo/rental_portal_change_request/static/src/js/rental_portal_owl_bundle.js) [NEW]
Consolidated OWL 2 bundle containing:
- `OrderLinesTable`: Editable table for order lines.
- `QuickAddBySKU`: Fast product addition via SKU search.
- `CatalogPanel`: Searchable product list.
- `RentalChangeRequestApp`: Main application component.
- `publicWidget.registry.RentalChangeRequestApp`: Bridge widget to mount the OWL app on the portal page.

#### [DELETE] legacy JS files
Removed individual legacy JS files (`rental_change_request_app.js`, components, services) to prevent conflicts and redundant logic.

#### [MODIFY] [__manifest__.py](file:///d:/apps/AI/enteza-odoo/rental_portal_change_request/__manifest__.py)
Updated assets bundle to point only to necessary files:
- `rental_portal_owl_bundle.js`
- `rental_portal.scss`

### Security & Controller
- Updated `jsonrpc.py` to use `.sudo()` and `commercial_partner_id` for ownership checks.
- Granted `product.product` read access to portal users in `ir.model.access.csv`.xml)
  - Re-add advanced filters and grouping.
  - Verify layout in Odoo 19 Enterprise.

## Verification Plan

### Automated Tests
- Run Odoo test suite:
  ```bash
  ./odoo-bin --test-enable -u rental_portal_change_request -d <db_name> --stop-after-init
  ```

### Manual Verification
1. Create a rental order for a portal customer.
2. Confirm the order.
3. Login as the customer in the portal.
4. Access /my/rentals and the order detail.
5. Click "Request Change" and verify the CR is created in draft.
6. Edit lines and submit.
7. Approve in the backend and verify the original order is updated.
