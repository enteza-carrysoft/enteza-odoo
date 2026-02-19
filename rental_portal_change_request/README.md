# Rental Portal Change Request for Odoo 19 Enterprise

## Overview

This module provides a **private rental portal** with a **Change Request + Review** workflow for Odoo 19 Enterprise. Rental customers can request modifications to confirmed orders through a structured approval process.

## Features

### For Customers (Portal)
- **Rental Order List**: View all rental orders in the portal
- **Order Details**: See complete order information including pickup dates
- **Change Request Editor**: Modify order lines with an intuitive interface
  - Add/remove/update products
  - Quick add by SKU/code
  - Browse full catalog with search and pagination
  - Real-time availability indicators
- **Submission Notes**: Add context for sales managers
- **Change History**: Track all submitted and approved changes

### For Sales Team
- **Change Request Dashboard**: View and manage all pending requests
- **Review Interface**: See detailed diffs of requested changes
- **Approval Workflow**: Approve or reject with reasons
- **Automatic Application**: Changes apply atomically to orders
- **Picking Recreation**: Pickings automatically recreated on approval
- **Activity Management**: Built-in tasks and notifications
- **Chatter Integration**: Full communication history

## Technical Highlights

- **Atomic Operations**: All server-side methods are atomic with rollback support
- **Concurrency Control**: Optimistic locking prevents conflicts
- **Performance**: Optimized for 4000+ SKUs and 80+ order lines
- **pg_trgm Search**: Fast fuzzy search on product codes and names
- **OWL Components**: Reactive UI with smooth interactions
- **JSON-RPC API**: Clean separation of frontend/backend
- **Complete Audit Trail**: All changes tracked in JSON format

## Requirements

- **Odoo**: 19.0 Enterprise
- **Python**: 3.10+
- **PostgreSQL**: 14+ with pg_trgm extension
- **Modules**:
  - `sale_management`
  - `sale_rental`
  - `website_sale`
  - `portal`
  - `mail`

## Installation

### 1. Copy Module

```bash
cd /path/to/odoo/addons
cp -r /path/to/rental_portal_change_request .
```

### 2. Install PostgreSQL Extension

```bash
sudo -u postgres psql -d your_database -f addons/rental_portal_change_request/scripts/install_pg_trgm.sql
```

### 3. Update Odoo

```bash
./odoo-bin -c odoo.conf -d your_database -i rental_portal_change_request --stop-after-init
```

### 4. Restart Odoo

```bash
systemctl restart odoo
```

Or use the provided upgrade script:

```bash
chmod +x addons/rental_portal_change_request/scripts/upgrade.sh
./addons/rental_portal_change_request/scripts/upgrade.sh your_database
```

## Configuration

### Portal Access

1. Go to **Settings > Users & Companies > Users**
2. Select or create a portal user
3. Ensure **Portal** access rights are assigned
4. The user will see "Rental Orders" in their portal

### Security

- Portal users only see their own orders
- Sales managers see all change requests
- Record rules enforce data isolation

## Usage

### Customer Workflow

1. **Access Rental Orders**
   - Login to portal
   - Navigate to "Rental Orders"

2. **Request Changes**
   - Click "Request Changes" on an order
   - Edit lines using the interface:
     - Change quantities
     - Add products by SKU
     - Browse catalog
     - Remove items
   - Add optional note
   - Click "Submit for Approval"

3. **Wait for Approval**
   - Sales manager reviews request
   - You'll receive notification
   - Order updates automatically if approved

### Sales Manager Workflow

1. **Review Requests**
   - Go to Sales > Change Requests
   - Filter by "Submitted" state

2. **Analyze Changes**
   - Open change request
   - Review diff of changes
   - Check customer note

3. **Approve or Reject**
   - Click "Approve" to apply changes
   - Click "Reject" to deny (requires reason)

## API Reference

### JSON-RPC Endpoints

#### Start Change Request
```
POST /rental_portal/jsonrpc/change_request/start
{
    "order_id": 123
}
```

#### Patch Revision
```
POST /rental_portal/jsonrpc/change_request/patch
{
    "change_request_id": 456,
    "patch_operations": [
        {"operation": "add", "product_id": 789, "qty": 2}
    ],
    "token_order": "timestamp",
    "token_revision": "timestamp"
}
```

#### Submit Request
```
POST /rental_portal/jsonrpc/change_request/submit
{
    "change_request_id": 456,
    "note": "Optional note"
}
```

#### Search Catalog
```
POST /rental_portal/jsonrpc/catalog/search
{
    "search_term": "keyword",
    "limit": 20,
    "offset": 0
}
```

## Performance

### Optimization Features

- **Database Indexes**: Composite indexes for common queries
- **GIN Indexes**: Fast text search with pg_trgm
- **Lazy Loading**: Catalog loads in pages of 20
- **Debounced Updates**: Patch operations batched
- **Virtualization**: UI handles 80+ lines smoothly

### Monitoring

Check query performance:
```bash
# Enable query logging
# In odoo.conf: log_level = debug
```

## Troubleshooting

### Change Request Won't Submit

**Problem**: Submit button disabled
**Solution**: Ensure at least one change has been made

### Concurrency Error

**Problem**: "Order has been modified by another user"
**Solution**: Refresh the page to get latest state

### Catalog Search Slow

**Problem**: Search takes >500ms
**Solution**: Ensure pg_trgm extension is installed and indexes created

### Permissions Issues

**Problem**: Portal users can't see orders
**Solution**: Check record rules and ACLs in Security settings

## Development

### Running Tests

```bash
# All tests
./odoo-bin -d test_db --test-enable --stop-after-init

# Specific module
./odoo-bin -d test_db --test-enable --test-tags=rental_portal_change_request --stop-after-init
```

### Code Structure

```
rental_portal_change_request/
├── models/          # Python models
├── controllers/     # HTTP endpoints
├── views/           # XML views and templates
├── static/src/js/   # OWL components
├── security/        # Access control
├── data/            # Data files
└── tests/           # Test cases
```

## Support

For issues and questions:
- Create issue in repository
- Check Odoo logs: `journalctl -u odoo -f`
- Enable debug mode for detailed errors

## License

OPL-1 (Odoo Proprietary License v1.0)

## Credits

Developed for Odoo 19 Enterprise
