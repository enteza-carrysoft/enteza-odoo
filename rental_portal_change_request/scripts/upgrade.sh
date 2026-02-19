#!/bin/bash

# Upgrade script for Rental Portal Change Request module
# This script handles database updates and migrations

set -e

# Configuration
ODOO_USER="odoo"
ODOO_DIR="/opt/odoo"
DB_NAME="${1:-prod_db}"
MODULE_NAME="rental_portal_change_request"

echo "================================================"
echo "Rental Portal Change Request Upgrade Script"
echo "================================================"
echo "Database: $DB_NAME"
echo "Module: $MODULE_NAME"
echo ""

# Function to run SQL as PostgreSQL superuser
run_sql() {
    local sql_file=$1
    echo "Running SQL script: $sql_file"
    sudo -u postgres psql -d "$DB_NAME" -f "$sql_file"
    echo "✓ SQL script completed"
    echo ""
}

# Function to run Odoo upgrade
run_odoo_upgrade() {
    echo "Running Odoo module upgrade..."
    echo "This may take several minutes..."
    sudo -u "$ODOO_USER" "$ODOO_DIR/odoo-bin" \
        -c "$ODOO_DIR/odoo.conf" \
        -d "$DB_NAME" \
        -i "$MODULE_NAME" \
        --stop-after-init \
        --without-demo
    echo "✓ Odoo upgrade completed"
    echo ""
}

# Function to restart Odoo service
restart_odoo() {
    echo "Restarting Odoo service..."
    sudo systemctl restart odoo
    echo "✓ Odoo service restarted"
    echo ""
}

# Main execution
echo "Step 1: Checking pg_trgm extension..."
run_sql "$ODOO_DIR/addons/$MODULE_NAME/scripts/install_pg_trgm.sql"

echo "Step 2: Creating performance indexes..."
run_sql "$ODOO_DIR/addons/$MODULE_NAME/scripts/create_indexes.sql"

echo "Step 3: Upgrading Odoo module..."
run_odoo_upgrade

echo "Step 4: Restarting Odoo service..."
restart_odoo

echo "================================================"
echo "Upgrade completed successfully!"
echo "================================================"
echo ""
echo "Next steps:"
echo "1. Verify the module is working in the Odoo UI"
echo "2. Check that the portal is accessible"
echo "3. Test change request creation and submission"
echo "4. Monitor logs for any errors: sudo journalctl -u odoo -f"
echo ""
