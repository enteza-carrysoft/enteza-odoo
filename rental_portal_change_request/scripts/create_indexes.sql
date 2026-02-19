-- Performance indexes for Rental Portal Change Request module
-- Run after module installation

-- Index on sale_order for parent order lookups
CREATE INDEX IF NOT EXISTS idx_sale_order_parent_order
ON sale_order (x_parent_order_id)
WHERE x_parent_order_id IS NOT NULL;

-- Composite index for portal queries
CREATE INDEX IF NOT EXISTS idx_sale_order_partner_state
ON sale_order (partner_id, state, is_rental_order)
WHERE is_rental_order = TRUE;

-- Index for rental pickup date queries
CREATE INDEX IF NOT EXISTS idx_sale_order_pickup_date
ON sale_order (x_rental_pickup_date)
WHERE x_rental_pickup_date IS NOT NULL;

-- Index for active change requests
CREATE INDEX IF NOT EXISTS idx_sale_order_active_change_request
ON sale_order (x_active_change_request_id)
WHERE x_active_change_request_id IS NOT NULL;

-- Index on change_request for order lookups
CREATE INDEX IF NOT EXISTS idx_rental_change_request_order
ON rental_change_request (order_id);

-- Index for change request state queries
CREATE INDEX IF NOT EXISTS idx_rental_change_request_state
ON rental_change_request (state)
WHERE state IN ('draft', 'editing', 'submitted');

-- Index on change_request_line for change request lookups
CREATE INDEX IF NOT EXISTS idx_rental_change_request_line_cr
ON rental_change_request_line (change_request_id);

-- GIN index for product name search with pg_trgm
CREATE INDEX IF NOT EXISTS idx_product_product_name_trgm
ON product_product USING gin (name gin_trgm_ops);

-- GIN index for product code search with pg_trgm
CREATE INDEX IF NOT EXISTS idx_product_product_code_trgm
ON product_product USING gin (default_code gin_trgm_ops)
WHERE default_code IS NOT NULL;

-- Composite index for product search
CREATE INDEX IF NOT EXISTS idx_product_product_sale_ok
ON product_product (sale_ok, active)
WHERE sale_ok = TRUE AND active = TRUE;

-- Report indexes for performance analysis
-- Analyze tables to update statistics
ANALYZE sale_order;
ANALYZE rental_change_request;
ANALYZE rental_change_request_line;
ANALYZE product_product;
