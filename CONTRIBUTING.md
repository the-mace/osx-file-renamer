# Contributing to OSX File Renamer

Thank you for your interest in contributing to OSX File Renamer! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Development Workflow](#development-workflow)
- [Code Style Guidelines](#code-style-guidelines)
- [Testing](#testing)
- [Commit Messages](#commit-messages)
- [Pull Request Process](#pull-request-process)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Enhancements](#suggesting-enhancements)

## Code of Conduct

This project aims to be welcoming and inclusive. Please be respectful and constructive in all interactions.

## Getting Started

Before you begin:

- **Pull latest `main` first.** Dependabot auto-merges dependency and Actions updates after CI; local checkouts are often behind. `git checkout main && git pull --ff-only`
- Check existing [issues](https://github.com/the-mace/osx-file-renamer/issues) to see if your bug/feature is already being discussed
- For major changes, open an issue first to discuss what you'd like to change
- For minor fixes (typos, small bugs), feel free to submit a PR directly

## Development Setup

### Prerequisites

1. **macOS** (required - this tool is macOS-specific)
2. **Python 3.11+** (managed with pyenv)
3. **System dependencies:**

   ```bash
   brew install imagemagick poppler pngquant
   ```

### Initial Setup

1. Fork the repository on GitHub

2. Clone your fork:

   ```bash
   git clone https://github.com/the-mace/osx-file-renamer.git
   cd osx-file-renamer
   ```

3. Set up Python environment:

   ```bash
   # Install Python 3.11 if not already installed
   pyenv install 3.11

   # Set local Python version
   pyenv local 3.11
   ```

4. Install the package in editable mode with dev dependencies:

   ```bash
   pip install -e ".[dev]"
   ```

5. Verify installation:

   ```bash
   # Test Python version
   python --version  # Should show 3.11.x

   # Test system dependencies
   convert --version  # ImageMagick
   pdftotext -v       # Poppler
   pngquant --version # pngquant

   # Test Python package
   pyenv exec pytest
   pyenv exec flake8
   ```

6. Set up LLM API key (for testing with real API calls):

   ```bash
   # Choose your preferred provider:
   echo "GROK_API_KEY=your_api_key_here" >> ~/.env
   # or
   echo "ANTHROPIC_API_KEY=your_api_key_here" >> ~/.env
   # or
   echo "OPENAI_API_KEY=your_api_key_here" >> ~/.env
   ```

## Development Workflow

### 1. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/bug-description
```

Branch naming conventions:

- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation updates
- `refactor/` - Code refactoring
- `test/` - Test additions or modifications

### 2. Make Your Changes

- Write clean, readable code
- Follow the code style guidelines (see below)
- Add/update tests for new functionality
- Update documentation as needed

### 3. Test Your Changes

```bash
# Run all tests
pyenv exec pytest

# Run tests with coverage report
pyenv exec pytest --cov=. --cov-report=term-missing

# Run tests in parallel (faster)
pyenv exec pytest -n auto

# Run specific test file
pyenv exec pytest tests/test_llm_main.py

# Run specific test
pyenv exec pytest tests/test_llm_main.py::TestClassName::test_method_name
```

### 4. Lint Your Code

```bash
# Check code style
pyenv exec flake8

# If errors, fix them before committing
```

### 5. Commit Your Changes

```bash
git add .
git commit -m "Your descriptive commit message"
```

See [Commit Messages](#commit-messages) section for guidelines.

### 6. Push and Create Pull Request

```bash
git push origin feature/your-feature-name
```

Then open a Pull Request on GitHub.

## Code Style Guidelines

### General Principles

- **Follow PEP 8** (enforced by flake8)
- **Be explicit** - prefer clarity over cleverness
- **Write docstrings** for public functions and classes
- **Add type hints** where they improve clarity
- **Keep functions focused** - one responsibility per function

### Specific Rules

1. **Imports**
   - All imports at the top of the file (no function-level imports)
   - No unused imports
   - No blank lines between import statements
   - Standard library → Third-party → Local imports

   ```python
   # Good
   import os
   import sys
   from datetime import datetime
   import titlecase
   from llm_client import call_llm_api

   # Bad
   import os

   import sys  # Don't add blank lines between imports
   ```

2. **Line Length**
   - Maximum 180 characters per line
   - Break long lines sensibly

3. **Constants**
   - Use defined constants instead of magic numbers
   - Constants at the top of the file in ALL_CAPS

   ```python
   # Good
   API_TIMEOUT = 30
   result = subprocess.run(cmd, timeout=API_TIMEOUT)

   # Bad
   result = subprocess.run(cmd, timeout=30)
   ```

4. **Error Handling**
   - Use specific exception types (no bare `except:`)
   - Provide informative error messages
   - Log errors appropriately

   ```python
   # Good
   try:
       result = process_file(path)
   except FileNotFoundError:
       logger.error(f"File not found: {path}")
       return None

   # Bad
   try:
       result = process_file(path)
   except:
       pass
   ```

5. **Documentation**
   - Add docstrings to public functions
   - Explain "why" not just "what" in comments
   - Update CLAUDE.md if architecture changes

   ```python
   def extract_invoice_info(file_path: str, all_pages: bool = False) -> dict:
       """
       Extract invoice metadata from a document file using LLM API.

       Args:
           file_path: Path to the document file
           all_pages: Whether to process all pages or just the first

       Returns:
           Dictionary with keys: business_name, document_type, date, etc.

       Raises:
           FileNotFoundError: If file_path doesn't exist
           LLMClientError: If API call fails
       """
   ```

## Testing

### Test Requirements

- **All new features must have tests**
- **All tests must pass** before submitting PR
- **No skipped tests** in final submission
- **Maintain or improve coverage** - aim for 80%+ coverage

### Test Organization

```
tests/
├── test_llm_main.py              # Main llm_client.py functionality
├── test_llm_file_processing.py   # File processing pipeline
├── test_llm_api_interaction.py   # API calls
├── test_llm_error_handling.py    # Error scenarios
├── test_llm_integration.py       # Integration tests with real files
├── test_invoice_renamer.py        # invoice_renamer.py tests
├── test_invoice_renamer_comprehensive.py  # Edge cases
├── conftest.py                    # Shared fixtures
└── fixtures/                      # Test files
```

### Writing Tests

- Use descriptive test names: `test_compress_image_handles_large_files`
- Use pytest fixtures from `conftest.py`
- Mock external calls (API, subprocess) in unit tests
- Use real files in integration tests (from `tests/fixtures/`)

```python
def test_rename_invoice_with_patient_name(tmp_path, mock_llm_response):
    """Test that patient names are correctly included in filename."""
    # Arrange
    test_file = tmp_path / "test.pdf"
    test_file.write_text("test content")
    mock_llm_response.return_value = {
        "business_name": "Vet Clinic",
        "document_type": "Invoice",
        "patient_name": "Whiskers",
        "date": "2024-01-15"
    }

    # Act
    result = rename_invoice(str(test_file))

    # Assert
    assert "Whiskers" in result
    assert result.endswith("20240115.pdf")
```

### Running Tests Locally

```bash
# Run all tests
pyenv exec pytest

# Run with coverage
pyenv exec pytest --cov=. --cov-report=html
# Then open htmlcov/index.html in browser

# Run only integration tests
pyenv exec pytest -m integration

# Run excluding slow tests
pyenv exec pytest -m "not slow"
```

## Commit Messages

### Format

```
<type>: <subject>

<body>

<footer>
```

### Type

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `style:` - Code style changes (formatting, no logic change)
- `refactor:` - Code refactoring
- `test:` - Adding or updating tests
- `chore:` - Maintenance tasks

### Examples

**Good commit messages:**

```
feat: Add support for TIFF image processing

Adds TIFF format to the supported image types and ensures proper
compression when converting to JPEG for API submission.

Closes #42
```

```
fix: Handle division by zero in brightness calculation

Adds check for zero-pixel images before calculating average brightness
to prevent ZeroDivisionError in edge cases.
```

```
docs: Update README with troubleshooting section

Adds common error scenarios and solutions based on user feedback.
```

**Bad commit messages:**

```
fix bug          # Too vague
updated stuff    # What stuff?
WIP             # Don't commit work-in-progress to main
```

## Pull Request Process

### Before Submitting

1. ✅ All tests pass: `pyenv exec pytest`
2. ✅ No linting errors: `pyenv exec flake8`
3. ✅ Code is documented
4. ✅ CLAUDE.md updated if architecture changed
5. ✅ No unnecessary files committed (check .gitignore)

### PR Description Template

```markdown
## Description
Brief description of what this PR does.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
Describe how you tested your changes.

## Checklist
- [ ] Tests pass locally
- [ ] Code follows style guidelines
- [ ] Documentation updated
- [ ] No new warnings introduced
```

### Review Process

1. Maintainer will review your PR
2. Address any feedback or requested changes
3. Once approved, maintainer will merge

## Reporting Bugs

### Before Reporting

1. Search existing issues to avoid duplicates
2. Test with the latest version
3. Gather reproduction steps

### Bug Report Template

```markdown
**Describe the bug**
A clear description of what the bug is.

**To Reproduce**
Steps to reproduce:
1. Run command '...'
2. With file '...'
3. See error

**Expected behavior**
What you expected to happen.

**Actual behavior**
What actually happened.

**Environment:**
- OS: [e.g. macOS 14.2]
- Python version: [e.g. 3.11.5]
- Package version: [e.g. 1.0.1]

**Log output:**
```

Paste relevant log output from /tmp/invoice_renamer.log

```

**Additional context**
Any other relevant information.
```

## Suggesting Enhancements

### Enhancement Template

```markdown
**Is your feature request related to a problem?**
A clear description of the problem.

**Describe the solution you'd like**
Clear description of what you want to happen.

**Describe alternatives you've considered**
Other solutions or features you've considered.

**Additional context**
Any other context, screenshots, or examples.
```

## Questions?

- Open an [issue](https://github.com/the-mace/osx-file-renamer/issues) for questions
- Check existing issues and documentation first
- For sensitive questions, contact the maintainer directly

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to OSX File Renamer! 🎉
