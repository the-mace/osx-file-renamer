# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OSX File Renamer is a command-line tool that uses AI (Grok API) to automatically rename invoice and document files based on their content. It analyzes documents to extract business names, document types, dates, and other metadata, then applies consistent naming conventions.

**Data Privacy Note**: This tool sends file contents to xAI's Grok API for analysis.

## Development Environment

**Python Version**: 3.11 (managed with pyenv)

Always use the pyenv environment when running code, tests, or tools:
```bash
pyenv exec python <command>
# or activate environment first
pyenv shell 3.11
```

## Common Commands

### Running the Application
```bash
# Basic usage - rename a file
python invoice_renamer.py path/to/file.pdf

# Dry run (preview without changes)
python invoice_renamer.py path/to/file.pdf --dry-run

# Move to target directory
python invoice_renamer.py path/to/file.pdf --move-to /target/dir

# Process all pages of PDF
python invoice_renamer.py path/to/file.pdf --all-pages
```

### Testing
```bash
# Run all tests
pyenv exec pytest

# Run specific test file
pyenv exec pytest tests/test_grok.py

# Run with coverage
pyenv exec pytest --cov=. --cov-report=term-missing

# Run in parallel
pyenv exec pytest -n auto
```

### Linting
```bash
# Check code style
pyenv exec flake8

# Configuration in .flake8:
# - Max line length: 180
# - Ignores: E201, E202, E402, E722
```

## Architecture

### Core Modules

**invoice_renamer.py** (590 lines)
- Main entry point and orchestration logic
- Extracts document metadata via grok.py subprocess calls
- Applies naming conventions and file operations
- Handles dry-run mode, file moves, and conflict resolution
- Logging with automatic rotation (logs to temp directory)

**grok.py** (700 lines)
- Grok API client for document analysis
- File processing pipeline: PDF → image extraction/conversion → compression → API call
- Supports multiple file types: PDFs, images (JPG, PNG, GIF, BMP, WebP, TIFF), text
- Image compression to meet API size limits (10MB base64)
- Constants defined at top: MAX_RAW_SIZE, MAX_BASE64_SIZE, timeouts, API endpoints
- Custom exceptions: GrokError, FileProcessingError, APIError

### Key Architecture Patterns

1. **Subprocess Communication**: invoice_renamer.py calls grok.py as subprocess rather than importing it directly. This isolation helps with error handling and allows independent execution.

2. **PDF Processing Pipeline**:
   - Text extraction via pdftotext (fast path for text-based PDFs)
   - Fallback to image extraction via pdfimages (for scanned PDFs)
   - Fallback to full PDF→image conversion via pdftoppm
   - Image compression using ImageMagick/pngquant if needed

3. **File Type Detection**: Uses mimetypes module + extension checking to determine processing path

4. **Size Management**: Multi-stage compression pipeline (PIL optimization → ImageMagick quality reduction → pngquant) to meet API limits

5. **Naming Convention**:
   ```
   Business Name [Account-Type] Document-Type [Last4] [- Patient/Animal] [Invoice#] Date
   ```
   Examples: "Chase Credit Card Statement 20240115.pdf", "Dr Smith Invoice ACS-1234 20240115.pdf"

### API Configuration

- API key from environment variable `GROK_API_KEY` or `~/.env` file
- Models: `grok-4-fast-reasoning` (default), `grok-2-vision-1212` (vision)
- Endpoint: https://api.x.ai/v1/chat/completions

### External Dependencies

System tools required:
- ImageMagick (image compression/conversion)
- Poppler tools (pdftotext, pdftoppm, pdfimages)
- pngquant (optional, better compression)

Python packages: titlecase, pytest, pytest-mock, pytest-cov, pytest-xdist

## Project Rules

1. **Environment**: Always use pyenv environment (Python 3.11) - prepend commands with `pyenv exec`
2. **Quality Gates**: Run flake8 at end of task - fix all errors before completion
3. **Testing**: Run all tests at end of task - fix all failures before completion
4. **Test Quality**: Never skip tests; no test failures acceptable
5. **Import Style**: Never import within functions - all imports at top of file
6. **Clean Imports**: No unused imports; nothing between import statements (no blank lines or code)
7. **Constants**: Use defined constants (e.g., timeouts) instead of hardcoded values

## Testing

Test files in `tests/` directory:
- `test_grok_main.py` - main grok.py functionality
- `test_grok_file_processing.py` - file processing pipeline
- `test_grok_api_interaction.py` - API calls
- `test_grok_error_handling.py` - error scenarios
- `test_invoice_renamer.py` - invoice_renamer.py functionality
- `conftest.py` - shared fixtures (mock env, jpeg data, temp file cleanup)

Key fixtures: `sample_jpeg_data`, `temp_file_cleanup`, `mock_env_file`, `mock_urllib_response`

## File Locations

- Logs: Platform-specific temp directory (e.g., `/tmp/invoice_renamer.log`)
- API key: Environment variable or `~/.env` file in home directory
