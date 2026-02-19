# Rental Portal Change Request - Odoo 19 Implementation

## Phase 1: Compatibility & Installation
- [x] Initial Odoo 19 compatibility fixes (SaleOrder, ChangeRequest, controllers)
- [x] Migrate mail templates from Mako to Jinja2 (Odoo 17+ requirement)
- [x] Fix search view and security access for installation
- [x] Successful installation on Odoo 19 Enterprise

## Phase 2: Refinement & Restoration
- [/] Restore search view filters in `rental_change_request_views.xml`
- [ ] Verify `sale_order_views.xml` layout in Odoo 19
- [x] Create session handoff document
- [x] Fix portal access "Forbidden" error (Product access)
- [x] Refactor frontend to modern OWL 2 (Odoo 19 compatibility)
- [x] Fix "Permission Denied" error during change request submission (Sudo + Commercial Partner)
- [x] Fix catalog data mapping and UI redundancy
- [x] Fix JS crash `onQtyChange` and implements concurrency tokens
- [x] Fix Python `AttributeError` in `user_has_groups`
- [/] Restore search view filters in `rental_change_request_views.xml` (Pending verification of functional app)

## Permanent Memory (Critical)
- **Git en Windows**: EJECUTAR COMANDOS UNO POR UNO. No usar `&&`.
- **OWL 2 Templates**: Integrar XML en el JS con la etiqueta `xml`.
- **Concurrency**: El frontend debe capturar y enviar `write_date` (tokens) para que el servidor guarde los cambios correctamente.

## Phase 3: Testing & Validation
- [ ] Create test rental order in backend
- [ ] Grant portal access to test customer
- [ ] Verify portal list/detail pages
- [ ] Test "Request Change" flow (creation of CR and Revision)
- [ ] Verify OWL editor loading and basic functionality

## Phase 4: Feature Completion
- [ ] Restore/Refine OWL components for the minimalist table view
- [ ] Verify atomic methods (Patch, Submit, Approve)
- [ ] Final end-to-end testing
