# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Odoo 19 Enterprise module (`rental_multi_warehouse`) that extends `sale_renting` to enable automatic multi-warehouse stock reservation with scheduled inter-warehouse transfers for rental orders. Written in Python (backend) and JavaScript/OWL 2 (frontend widget). Language throughout the codebase is Spanish.

**Dependencies**: `sale_renting` (Enterprise), `stock`, `sale_stock`

## Common Commands

```bash
# Install/update the module
odoo -u rental_multi_warehouse

# Run with test mode
odoo -u rental_multi_warehouse --test-enable --stop-after-init

# Run Odoo server pointing to this addons path
odoo --addons-path=/path/to/addons,/path/to/rental_multi_warehouse/..
```

There is no standalone build, lint, or test runner — all operations go through the Odoo server framework.

## Architecture

### Core Data Flow

1. **User creates rental order** with product, dates, quantity
2. **Availability engine** (`sale_order_line._get_multi_wh_availability()`) calculates stock across all warehouses in priority order, assigning units in cascade
3. **OWL widget** displays color-coded availability with expandable per-warehouse breakdown
4. **On order confirmation** (`sale_order.action_confirm()`), creates `rental.warehouse.assignment` records and `stock.picking` inter-warehouse transfers
5. **Cron job** runs daily to warn about overdue/upcoming transfers
6. **On rental return**, optionally creates return transfers to send stock back to origin warehouses

### Key Models

| Model | File | Responsibility |
|-------|------|----------------|
| `rental.warehouse.priority` | `models/rental_warehouse_priority.py` | Ordered list of warehouses for stock allocation |
| `rental.warehouse.assignment` | `models/sale_order_line.py` | Concrete stock allocation records linking a sale line to a source warehouse, with transfer tracking and lifecycle state (`draft→confirmed→transferred→delivered→returned`) |
| `sale.order.line` (extended) | `models/sale_order_line.py` | **Core availability engine** — computes per-warehouse availability considering on-hand stock, committed rentals (date overlap), expected returns, and incoming transfers |
| `sale.order` (extended) | `models/sale_order.py` | Orchestrates assignment creation, inter-warehouse transfer generation, cancellation, and return transfers on order confirmation |
| `res.config.settings` (extended) | `models/res_config_settings.py` | Module settings: transfer day, lead days, auto-return toggle |
| `rental.availability.wizard` | `wizard/rental_availability_wizard.py` | Standalone availability check without creating an order |

### Availability Formula

Per warehouse: `available = qty_on_hand - committed_rentals + returning_before_start + incoming_transfers`

The cascade algorithm iterates warehouses in priority order (primary warehouse first, then by `rental.warehouse.priority` sequence), assigning `min(available, remaining_needed)` from each until demand is met or all warehouses exhausted.

### Transfer Scheduling Logic

Transfers are scheduled for the configured weekday (default: Tuesday) before the rental delivery date, respecting a minimum lead time (default: 2 days). If the calculated date falls in the past, it falls back to today.

### Frontend Widget

- **Component**: `RentalMultiWhWidget` in `static/src/js/rental_multi_wh_widget.js`
- **Template**: `static/src/xml/rental_multi_wh_widget.xml`
- **Framework**: OWL 2, registered as field widget `rental_multi_wh_availability`
- **Data source**: Reads `rental_availability_json` computed field via RPC (`get_multi_wh_availability_data`)
- **Status colors**: Green (ok), Blue (transfer_needed), Red (deficit)

### Configuration Parameters (ir.config_parameter)

- `rental_multi_wh.transfer_day` — Day of week for transfers (0=Monday, default "1"=Tuesday)
- `rental_multi_wh.transfer_lead_days` — Minimum advance notice days (default "2")
- `rental_multi_wh.auto_return_transfer` — Auto-create return transfers (default "True")

### Security

Access control in `security/ir.model.access.csv`:
- **Sales User**: Read-only on priority and assignment models, full CRUD on wizard
- **Sales Manager**: Full CRUD on all models

## Development Notes

- Both `rental.warehouse.assignment` and the `sale.order.line` extensions live in the same file (`models/sale_order_line.py`) — this is where the bulk of the business logic resides
- The `action_confirm()` override in `sale_order.py` calls `super()` and then creates assignments/transfers — order of operations matters
- The widget communicates with the backend via `orm.call()` to `get_multi_wh_availability_data` on `sale.order.line`
- The cron method `_cron_check_pending_transfers()` lives on `rental.warehouse.assignment`
- No unit tests currently exist in the module
