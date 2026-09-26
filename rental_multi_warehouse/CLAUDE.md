# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Odoo 19 Enterprise module (`rental_multi_warehouse`) that extends `sale_renting` to enable automatic multi-warehouse stock reservation with scheduled inter-warehouse transfers for rental orders. Written in Python (backend) and JavaScript/OWL 2 (frontend widget). Language throughout the codebase is Spanish.

**Dependencies**: `sale_renting` (Enterprise), `stock`, `sale_stock`

## Common Commands

No `odoo -u` or `odoo-bin --test-enable` access on this instance — deploy is commit → push → `git pull` on the server → "Actualizar lista de aplicaciones" → Instalar/Actualizar from the Odoo UI. See the repo root `CLAUDE.md` for the full deploy flow and its gotchas. There is no standalone build, lint, or test runner either way — all operations go through the Odoo server framework.

## Development Notes

- Both `rental.warehouse.assignment` and the `sale.order.line` extensions live in the same file (`models/sale_order_line.py`) — this is where the bulk of the business logic resides
- The `action_confirm()` override in `sale_order.py` calls `super()` and then creates assignments/transfers — order of operations matters
- The widget communicates with the backend via `orm.call()` to `get_multi_wh_availability_data` on `sale.order.line`
- The cron method `_cron_check_pending_transfers()` lives on `rental.warehouse.assignment`
- No unit tests currently exist in the module
