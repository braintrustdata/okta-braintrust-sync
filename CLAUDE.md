# Project Preferences

## Code Style Guidelines

### Comments
- Add clear, explanatory comments to all code blocks
- Use block comments above classes and major functions to explain their purpose
- Add inline comments for complex logic or non-obvious code
- Group related configuration options with section headers using comment separators like:
  ```python
  # ========== Section Name ==========
  ```
- Include usage examples in docstrings where helpful

### Documentation Style
- Explain what each block of code does, not just what it is
- For configuration classes, explain when and how different options are used
- For enums and constants, explain the meaning and use case of each value
- Add examples in comments or docstrings to illustrate complex configurations

## Project-Specific Information

### Syncing Architecture
- The system supports both Okta groups and user attributes for syncing
- Group assignments can be based on:
  1. Direct Okta group memberships
  2. User profile attributes (department, title, location, etc.)
  3. Hybrid approach combining both

### Testing Commands
- Run tests: `pytest`
- Run specific test file: `pytest tests/test_file.py`
- Run with coverage: `pytest --cov`

### Linting and Type Checking
- Lint code: `ruff check .`
- Fix linting issues: `ruff check . --fix`
- Type check: `mypy sync/`