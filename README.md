# OSX File Renamer

![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey.svg)

A command-line tool for automatically renaming invoice and document files based on their content using AI analysis via LLM APIs (Claude, GPT, Grok, Gemini, and 100+ others).

## Overview

This tool analyzes invoice, statement, and document files using AI (via LiteLLM supporting 100+ LLM providers) to extract business names, document types, and dates, then applies a consistent naming convention to help organize files.

## Data Privacy Warning

⚠️ **Important:** This tool sends the contents of your files to your chosen LLM provider's API for analysis. By using this tool, you acknowledge that file contents (including potentially sensitive financial or personal information) are being transmitted to and processed by external AI services.

**What data is sent:**

- Complete file contents (text from PDFs, images, or text files)
- Extracted text and images from documents
- File metadata (name, type)

**Data not sent:**

- Files remain on your local system
- No automatic cloud storage or file retention by this tool

Please review your chosen provider's terms of service and privacy policy to understand how your data is handled, stored, and secured before proceeding. If you have concerns about data privacy, consider alternative local processing options or avoid processing sensitive documents.

**Provider Links:**

- [xAI (Grok) Terms & Privacy](https://x.ai/terms/)
- [Anthropic (Claude) Privacy Policy](https://www.anthropic.com/privacy)
- [OpenAI Privacy Policy](https://openai.com/privacy/)
- [Google AI Privacy](https://ai.google.dev/gemini-api/terms)

## Features

- **AI-Powered Analysis**: Uses LLM APIs (Claude, GPT, Grok, Gemini, etc.) to intelligently extract information from various document types
- **Multiple Document Types**: Supports invoices, statements, receipts, confirmations, notices, and other document types
- **Intelligent Naming**: Applies consistent naming conventions with business names, document types, and dates
- **Account Information**: Handles bank statements, credit card statements, and investment accounts
- **Patient/Medical Records**: Specifically handles medical and veterinary documents
- **File Type Support**: Works with PDFs, images, and text documents
- **Dry Run Mode**: Preview changes before applying them
- **Logging**: Daily-rotated INFO logs (~1 day retained) for multi-file rename history
- **Safe Operations**: Prevents overwriting files and provides conflict resolution

## Prerequisites

### System Requirements

- **Operating System**: macOS (designed and tested for OSX)
- **Python**: 3.11 or higher (managed via pyenv)
- **ImageMagick**: Required for image processing

  ```bash
  brew install imagemagick
  ```

- **Poppler**: Required for PDF processing

  ```bash
  brew install poppler
  ```

- **pngquant**: Optional, improves compression (recommended)

  ```bash
  brew install pngquant
  ```

### API Requirements

- **API key** from your chosen LLM provider:
  - [xAI Grok](https://x.ai/) (default) - `GROK_API_KEY`
  - [Anthropic Claude](https://anthropic.com/) - `ANTHROPIC_API_KEY`
  - [OpenAI GPT](https://openai.com/) - `OPENAI_API_KEY`
  - [Google Gemini](https://ai.google.dev/) - `GOOGLE_API_KEY`
  - [100+ other providers via LiteLLM](https://docs.litellm.ai/docs/providers)
- Configure via environment variable or in `~/.env` file

## Installation

1. Clone this repository:

   ```bash
   git clone https://github.com/the-mace/osx-file-renamer.git
   cd osx-file-renamer
   ```

2. Install the package to make the `invoice-renamer` command available system-wide:

   ```bash
   make install
   ```

   This will:
   - Install the package using your system Python (3.11+)
   - Create the `invoice-renamer` command
   - Display instructions for creating a symlink to make the command available in your PATH

3. Create the symlink (requires sudo):

   ```bash
   sudo ln -sf "/Library/Frameworks/Python.framework/Versions/3.11/bin/invoice-renamer" /usr/local/bin/invoice-renamer
   ```

4. Set up your API key:

   ```bash
   # Add to ~/.env file or set environment variable
   # For Grok (default):
   echo "GROK_API_KEY=your_api_key_here" >> ~/.env

   # Or for other providers (Claude, GPT-4, Gemini, etc.):
   echo "ANTHROPIC_API_KEY=your_api_key_here" >> ~/.env
   echo "LLM_MODEL=claude-3-5-sonnet-20241022" >> ~/.env
   ```

### Development Installation

For development with testing tools:

```bash
make install-dev
```

This installs the package in editable mode with dev dependencies (pytest, flake8, etc.).

## Usage

### Basic Usage

Rename a single invoice file:

```bash
invoice-renamer ~/Downloads/invoice.pdf
```

### Advanced Options

- **Dry Run** (preview changes):

  ```bash
  invoice-renamer ~/Downloads/invoice.pdf --dry-run
  ```

- **Move to Directory**:

  ```bash
  invoice-renamer ~/Downloads/invoice.pdf --move-to ~/Documents/Invoices
  ```

- **Process All Pages** (for multi-page PDFs):

  ```bash
  invoice-renamer ~/Downloads/statement.pdf --all-pages
  ```

### Examples

```bash
# Rename with preview
invoice-renamer ~/Downloads/invoice.pdf --dry-run

# Rename and move to organized folder
invoice-renamer ~/Downloads/invoice.pdf --move-to ~/Documents/Invoices

# Process complex multi-page document
invoice-renamer ~/Downloads/statement.pdf --all-pages --move-to ~/Documents/Statements
```

### Development Usage

When developing or testing from the repository directory:

```bash
cd ~/Documents/Code/osx-file-renamer
python3 invoice_renamer.py path/to/file.pdf --dry-run
```

## macOS Integration

### Finder Quick Actions

On macOS, you can create a Finder Quick Action shortcut to easily trigger the file renamer directly from the Finder context menu. This allows you to right-click on files and rename them in place without using the command line.

**Example Shortcut**: [OSX File Renamer Quick Action](https://www.icloud.com/shortcuts/cd48aad565124fe4b366074fe38a223e)

**To use:**

1. Open the shortcut link on your Mac
2. Install the shortcut to your system
3. The shortcut automatically renames the selected file(s) in their current location
4. Access it via Finder's right-click menu under Quick Actions

**Note**: The Quick Action performs direct renaming. For advanced options like `--dry-run` mode or moving to a target directory, use the command line interface.

**Creating Your Own Quick Action:**
You can customize the shortcut to pass different arguments by editing the shell script action:

```bash
# Use the installed command (recommended)
invoice-renamer "$@" --dry-run

# Or use direct script execution (for development)
python3 ~/Documents/Code/osx-file-renamer/invoice_renamer.py "$@" --dry-run
```

## Naming Convention

The LLM extracts **facts**; Python builds the filename with a fixed grammar:

```
Vendor [AccountType] Topic [AccountId] [- Party] [RefId] Date.ext
```

**Topic** comes from document type + optional short qualifier (`document_title`):

| Situation | Topic segment | Example |
|-----------|---------------|---------|
| No qualifier | document type | `… Statement …` |
| Premise / subject label | qualifier alone | `National Grid Barn 5018 …` |
| Confirmation / Certificate / Permit subtype | `{qualifier} {type}` | `Fidelity Trade Confirmation …` |

Examples:

- `Amex CC Statement 1000 20240115.pdf`
- `Chase Checking Statement 4521 20240115.pdf`
- `National Grid Barn 5018 20260729.pdf`
- `Tesla Portfolio Statement 20231231.pdf`
- `Fidelity Trade Confirmation 20260731.pdf`
- `Dr Smith Invoice ACS12B4 20240115.pdf`
- `Vet Clinic Invoice - Whiskers 20240110.pdf`

Short vendor names (Amex, Chase), low-PII account ids (last-4), and lowercase extensions are enforced in code.

## Supported Document Types

- **Invoice**, **Quote**, **Statement**, **Receipt**, **Confirmation**
- **Notice**, **Letter**, **Report**, **Form**, **Contract**, **Policy**
- **Certificate**, **Permit**, **Map**, **Itinerary**, **Test** (e.g. USDF scorecards)

## File Support

- **PDFs**: Text-based PDFs and scanned/image PDFs (converted automatically)
- **Images**: JPG, PNG, BMP, TIFF, WebP, GIF
- **Text Files**: Plain text documents

## Configuration

The tool accepts these optional parameters:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `--dry-run` | Preview changes without modifying files | False |
| `--move-to` | Target directory for renamed files | Current directory |
| `--all-pages` | Process all PDF pages (default: first 2 pages — cover + content) | False |

## Logging

Logs are automatically written to a platform-specific temporary directory (typically `/tmp` on Unix-like systems or system temp directory on Windows) with automatic rotation to keep file size manageable. Log levels include DEBUG, INFO, WARNING, and ERROR.

## Performance notes

Default path is optimized for short names and moderate latency:

- Text PDFs use `pdftotext` (pages 1–2); scans use vision on JPEG page renders
- LLM client runs in-process with content caching for retries
- Fast non-reasoning model by default; override with `LLM_MODEL` if needed

If you need it **faster or cheaper** later (e.g. local Tesseract for clean scans, path timing logs, cheaper vision models), see **Future Optimizations** in [`CLAUDE.md`](CLAUDE.md).

## Troubleshooting

### Common Issues

#### 1. API Key Not Found

```
Error: GROK_API_KEY not found
```

**Solution**: Ensure `GROK_API_KEY` is set in environment or `~/.env` file:

```bash
echo "GROK_API_KEY=your_api_key_here" >> ~/.env
# OR
export GROK_API_KEY=your_api_key_here
```

#### 2. File Too Large

```
Error: File exceeds maximum size
```

**Solution**:

- Images/PDFs are automatically compressed if over size limits
- For extremely large files, try `--all-pages` to process incrementally
- Check that ImageMagick and pngquant are installed for optimal compression

#### 3. PDF Processing Issues

```
Error: Unable to process PDF
```

**Solution**:

- Verify Poppler tools are installed: `which pdftotext pdftoppm`
- Verify ImageMagick is installed: `which convert`
- Scanned PDFs automatically convert to images (requires more processing time)
- Try `--all-pages` flag for complex multi-page documents

#### 4. Permission Errors

```
Error: Permission denied
```

**Solution**:

- Ensure write permissions in target directory: `ls -la`
- Check file is not currently open in another application
- Verify you own the file: `ls -l filename`

#### 5. Python Version Issues

```
Error: Module not found / Syntax error
```

**Solution**:

- Verify Python 3.11+ is active: `python --version`
- Use pyenv to manage versions: `pyenv local 3.11`
- Reinstall dependencies: `pip install -e ".[dev]"`

### System Dependencies

Install all required system dependencies:

```bash
brew install imagemagick poppler pngquant
```

Verify installation:

```bash
convert --version  # ImageMagick
pdftotext -v       # Poppler
pngquant --version # pngquant
```

### Debug Logging

Rename runs log at **INFO** to a daily-rotated file (current day + one previous day). Third-party LLM client noise is suppressed so a batch of files still leaves readable history.

```bash
# On macOS/Linux — live tail
tail -f /tmp/invoice_renamer.log

# Recent renames only
grep -E 'Successfully renamed|Would rename|New filename|Extracted account type|Finished' /tmp/invoice_renamer.log

# Previous day's rotated backup (if present)
ls -la /tmp/invoice_renamer.log*

# Or find the temp directory
python3 -c "import tempfile; print(tempfile.gettempdir())"
```

### Getting Help

If you encounter issues:

1. Check the log file for detailed error messages
2. Verify all prerequisites are installed
3. Try running with a simple test file first
4. [Open an issue](https://github.com/the-mace/osx-file-renamer/issues) with log output and steps to reproduce

## Development

### Running Tests

```bash
# Run all tests
make test
# or: pytest -v

# Run with coverage
make test-cov
# or: pytest --cov=. --cov-report=term-missing

# Run in parallel (faster)
make test-fast
# or: pytest -n auto

# Run specific test file
pytest tests/test_llm_main.py
```

### Code Quality

```bash
# Check code style
make lint
# or: flake8

# View configuration
cat .flake8
```

### Project Structure

```
osx-file-renamer/
├── invoice_renamer.py      # Main application logic
├── llm_client.py           # LLM API client (supports multiple providers via LiteLLM)
├── tests/                  # Test suite
│   ├── test_llm_*.py      # LLM client tests
│   ├── test_invoice_*.py  # Invoice renamer tests
│   ├── conftest.py        # Shared test fixtures
│   └── fixtures/          # Real test files for integration tests
├── pyproject.toml         # Package configuration and dependencies
├── Makefile               # Build and development commands
├── CLAUDE.md              # AI assistant guidance
└── README.md              # This file
```

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines on:

- Setting up your development environment
- Code style and standards
- Testing requirements
- Pull request process
- Project architecture and conventions

Quick start for contributors:

```bash
# Fork and clone the repository
git clone https://github.com/YOUR_USERNAME/osx-file-renamer.git
cd osx-file-renamer

# Install dev dependencies
make install-dev

# Run tests and linting
make test
make lint
```

## License

This project is open source. See the [LICENSE](LICENSE) file for details.

## Version History

See the [git commit history](https://github.com/the-mace/osx-file-renamer/commits/main) for detailed changes and release notes.
