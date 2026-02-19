-- PostgreSQL pg_trgm extension installation
-- This script enables the pg_trgm extension for fuzzy text search
-- Run as PostgreSQL superuser

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Verify installation
SELECT extname, extversion FROM pg_extension WHERE extname = 'pg_trgm';
