# Contributing to Rental Portal Change Request

## How to Contribute

We welcome contributions to the Rental Portal Change Request module!

## Development Setup

1. **Fork and Clone**
   ```bash
   git clone https://github.com/your-repo/rental_portal_change_request.git
   cd rental_portal_change_request
   ```

2. **Create Development Environment**
   - Install Odoo 19 Enterprise
   - Install PostgreSQL with pg_trgm
   - Install Python dependencies

3. **Link to Odoo Addons**
   ```bash
   ln -s /path/to/rental_portal_change_request /path/to/odoo/addons/
   ```

## Code Style

### Python
- Follow PEP 8
- Use meaningful variable names
- Add docstrings to classes and methods
- Maximum line length: 100 characters

### JavaScript
- Use strict mode
- Follow Odoo JS guidelines
- Add JSDoc comments
- Use OWL component patterns

### XML
- Indent with 4 spaces
- Use meaningful IDs and names
- Add comments for complex logic

## Testing

Before submitting:
1. Run all tests: `--test-enable --test-tags=rental_portal_change_request`
2. Test in browser (Chrome/Firefox)
3. Verify no console errors
4. Check responsive design (mobile/tablet)

## Pull Request Process

1. **Create Feature Branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make Changes**
   - Write clean, documented code
   - Add tests for new features
   - Update README if needed

3. **Commit**
   ```bash
   git commit -m "feat: add feature description"
   ```

   Use conventional commits:
   - `feat:` New feature
   - `fix:` Bug fix
   - `docs:` Documentation
   - `test:` Tests
   - `refactor:` Refactoring

4. **Push and Create PR**
   ```bash
   git push origin feature/your-feature-name
   ```

5. **PR Description**
   - Describe changes
   - Link issues
   - Add screenshots if UI changes
   - List testing done

## Review Process

- At least one approval required
- All tests must pass
- Code review checklist:
  - [ ] Code follows style guide
  - [ ] Tests added/updated
  - [ ] Documentation updated
  - [ ] No console errors
  - [ ] Responsive design verified

## Bug Reports

Include:
- Odoo version
- Steps to reproduce
- Expected vs actual behavior
- Screenshots if applicable
- Browser/console errors

## Feature Requests

- Check existing issues first
- Describe use case clearly
- Explain why it's needed
- Suggest possible implementation

## License

By contributing, you agree that your code will be licensed under OPL-1.

## Questions?

Open an issue with the `question` label.
