.PHONY: help install install-dev test test-cov test-fast lint clean run-invoice run-grok check all coverage-html uninstall reinstall

# Colors for output
BLUE := \033[36m
RESET := \033[0m

help:  ## Show this help message
	@echo "$(BLUE)OSX File Renamer - Available Commands:$(RESET)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(BLUE)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "Examples:"
	@echo "  make install       # Install dependencies"
	@echo "  make test          # Run tests"
	@echo "  make lint          # Check code style"
	@echo "  make all           # Run full check (clean, lint, test)"

install:  ## Install package with runtime dependencies only
	pyenv exec pip install -e .

install-dev:  ## Install package in editable mode with dev dependencies
	pyenv exec pip install -e ".[dev]"

test:  ## Run all tests
	pyenv exec pytest -v

test-cov:  ## Run tests with coverage report
	pyenv exec pytest --cov=. --cov-report=term-missing --cov-report=html
	@echo ""
	@echo "$(BLUE)Coverage report generated in htmlcov/index.html$(RESET)"

test-fast:  ## Run tests in parallel (faster)
	pyenv exec pytest -n auto

test-integration:  ## Run only integration tests
	pyenv exec pytest -v -m integration

test-watch:  ## Run tests and watch for changes (requires pytest-watch)
	pyenv exec ptw -- -v

lint:  ## Check code style with flake8
	@echo "$(BLUE)Running flake8...$(RESET)"
	@pyenv exec flake8 || (echo "$(BLUE)Linting failed. Fix errors before committing.$(RESET)" && exit 1)
	@echo "$(BLUE)✓ Linting passed!$(RESET)"

clean:  ## Clean up temporary files and caches
	@echo "$(BLUE)Cleaning up...$(RESET)"
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .coverage htmlcov/ dist/ build/ *.egg-info
	@echo "$(BLUE)✓ Cleanup complete!$(RESET)"

run-invoice:  ## Run invoice renamer (usage: make run-invoice FILE=path/to/file.pdf)
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make run-invoice FILE=path/to/file.pdf"; \
		echo "Optional: make run-invoice FILE=path/to/file.pdf DRY_RUN=--dry-run"; \
		exit 1; \
	fi
	pyenv exec python invoice_renamer.py $(FILE) $(DRY_RUN)

run-grok:  ## Run grok CLI (usage: make run-grok PROMPT="your prompt")
	@if [ -z "$(PROMPT)" ]; then \
		echo "Usage: make run-grok PROMPT=\"your prompt here\""; \
		echo "Optional: make run-grok PROMPT=\"analyze this\" FILE=test.pdf"; \
		exit 1; \
	fi
	pyenv exec python grok.py $(if $(FILE),--file $(FILE)) "$(PROMPT)"

check: lint test  ## Run linting and tests (quick check before commit)
	@echo ""
	@echo "$(BLUE)✓ All checks passed!$(RESET)"

all: clean lint test  ## Run full check: clean, lint, and test
	@echo ""
	@echo "$(BLUE)✓ All tasks completed successfully!$(RESET)"

coverage-html: test-cov  ## Generate HTML coverage report and open it
	@echo "$(BLUE)Opening coverage report...$(RESET)"
	@open htmlcov/index.html 2>/dev/null || xdg-open htmlcov/index.html 2>/dev/null || echo "Open htmlcov/index.html manually"

uninstall:  ## Uninstall the package
	pyenv exec pip uninstall -y osx-file-renamer

reinstall: uninstall install-dev  ## Reinstall the package in editable mode
	@echo "$(BLUE)✓ Package reinstalled!$(RESET)"

# Development shortcuts
.PHONY: t l c
t: test  ## Shortcut for 'test'
l: lint  ## Shortcut for 'lint'
c: clean  ## Shortcut for 'clean'
