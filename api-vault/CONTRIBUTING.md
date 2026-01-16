# Contributing to Api Vault

Thank you for your interest in contributing to Api Vault! This document provides guidelines and information for contributors.

## Development Setup

### Prerequisites

- Python 3.11 or higher
- Git

### Setting Up Your Development Environment

1. Clone the repository:
   ```bash
   git clone https://github.com/api-vault/api-vault.git
   cd api-vault
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install development dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

4. Verify installation:
   ```bash
   api-vault --version
   pytest
   ```

## Code Style

We use the following tools to maintain code quality:

- **Ruff** for linting and formatting
- **MyPy** for type checking
- **Pytest** for testing

### Running Quality Checks

```bash
# Linting
ruff check src tests

# Type checking
mypy src

# Run all tests
pytest

# Run tests with coverage
pytest --cov=src/api_vault --cov-report=html
```

## Project Structure

```
api-vault/
├── src/api_vault/      # Main source code
│   ├── cli.py            # CLI commands
│   ├── schemas.py        # Pydantic models
│   ├── repo_scanner.py   # Repository scanning
│   ├── signal_extractor.py # Signal extraction
│   ├── secret_guard.py   # Secret detection
│   ├── context_packager.py # Context preparation
│   ├── planner.py        # Plan generation
│   ├── anthropic_client.py # API client
│   ├── runner.py         # Plan execution
│   ├── config.py         # Configuration management
│   ├── errors.py         # Error hierarchy
│   └── templates/        # Prompt templates
├── tests/                # Test suite
├── docs/                 # Documentation
└── examples/             # Usage examples
```

## Making Changes

### Branch Naming

- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation changes
- `refactor/` - Code refactoring
- `test/` - Test additions or changes

### Commit Messages

Follow conventional commit format:

```
type(scope): brief description

[optional body]

[optional footer]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Examples:
```
feat(cli): add estimate command for cost preview
fix(secret-guard): handle unicode in file content
docs(readme): add installation instructions
```

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes with tests
3. Ensure all tests pass: `pytest`
4. Ensure code quality: `ruff check . && mypy src`
5. Update documentation if needed
6. Submit a pull request

### PR Checklist

- [ ] Tests added/updated for changes
- [ ] Documentation updated if needed
- [ ] Code passes linting (`ruff check`)
- [ ] Code passes type checking (`mypy src`)
- [ ] All tests pass (`pytest`)
- [ ] Commit messages follow conventions

## Testing Guidelines

### Writing Tests

- Place tests in `tests/` directory
- Name test files `test_*.py`
- Name test functions `test_*`
- Use pytest fixtures for shared setup
- Aim for high coverage of new code

### Test Categories

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_scanner.py

# Run tests matching pattern
pytest -k "test_scan"

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=src/api_vault
```

### Property-Based Testing

We use Hypothesis for property-based testing:

```python
from hypothesis import given, strategies as st

@given(st.text())
def test_function_handles_any_string(text):
    result = my_function(text)
    assert result is not None
```

## Adding New Features

### Adding a New CLI Command

1. Add the command function in `cli.py`
2. Use Typer decorators for options
3. Add tests in `tests/test_cli.py`
4. Update README with usage examples

### Adding a New Artifact Family

1. Add the family to `ArtifactFamily` enum in `schemas.py`
2. Create a prompt template in `templates/prompts.py`
3. Add appropriate signal detection in `signal_extractor.py`
4. Add tests for the new family

### Adding Secret Detection Patterns

1. Add patterns to `SECRET_PATTERNS` in `secret_guard.py`
2. Include pattern name, regex, and description
3. Add tests with example strings
4. Update SECURITY.md documentation

## Error Handling

Use the error hierarchy from `errors.py`:

```python
from api_vault.errors import ScanError, ErrorCode

raise ScanError(
    message="File not found",
    code=ErrorCode.SCAN_PATH_NOT_FOUND,
    file_path=str(path),
    suggestion="Check that the path exists",
)
```

## Documentation

- Keep docstrings up to date
- Use Google-style docstrings
- Update README for user-facing changes
- Add examples for new features

## Getting Help

- Open an issue for bugs or feature requests
- Use discussions for questions
- Tag issues appropriately

## Code of Conduct

Be respectful and constructive. We welcome contributors of all backgrounds and experience levels.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
