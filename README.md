# OSX File Renamer

![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey.svg)

A command-line tool for automatically renaming invoice and document files based on their content using AI analysis through the Grok API.

## Overview

This tool analyzes invoice, statement, and document files using AI (Grok API) to extract business names, document types, and dates, then applies a consistent naming convention to help organize files.

## Data Privacy Warning

⚠️ **Important:** This tool sends the contents of your files to xAI's Grok API for analysis. By using this tool, you acknowledge that file contents (including potentially sensitive financial or personal information) are being transmitted to and processed by external AI services.

**What data is sent:**

- Complete file contents (text from PDFs, images, or text files)
- Extracted text and images from documents
- File metadata (name, type)

**Data not sent:**

- Files remain on your local system
- No automatic cloud storage or file retention by this tool

Please review xAI's [terms of service](https://x.ai/terms/) and [privacy policy](https://x.ai/privacy/) to understand how your data is handled, stored, and secured before proceeding. If you have concerns about data privacy, consider alternative local processing options or avoid processing sensitive documents.

## Features

- **AI-Powered Analysis**: Uses Grok API to intelligently extract information from various document types
- **Multiple Document Types**: Supports invoices, statements, receipts, confirmations, notices, and other document types
- **Intelligent Naming**: Applies consistent naming conventions with business names, document types, and dates
- **Account Information**: Handles bank statements, credit card statements, and investment accounts
- **Patient/Medical Records**: Specifically handles medical and veterinary documents
- **File Type Support**: Works with PDFs, images, and text documents
- **Dry Run Mode**: Preview changes before applying them
- **Logging**: Comprehensive logging with automatic log rotation
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

- **Grok API key** from [xAI](https://x.ai/)
- Configure via environment variable `GROK_API_KEY` or in `~/.env` file

## Installation

1. Clone this repository:

   ```bash
   git clone https://github.com/the-mace/osx-file-renamer.git
   cd osx-file-renamer
   ```

2. Set up Python environment with pyenv:

   ```bash
   pyenv install 3.11
   pyenv local 3.11
   ```

3. Install the package with dependencies:

   ```bash
   # For development (includes testing tools)
   pip install -e ".[dev]"

   # Or for runtime only
   pip install -e .
   ```

4. Set up your Grok API key:

   ```bash
   # Add to ~/.env file or set environment variable
   echo "GROK_API_KEY=your_api_key_here" >> ~/.env
   ```

## Usage

### Basic Usage

Rename a single invoice file:

```bash
python invoice_renamer.py path/to/invoice.pdf
```

### Advanced Options

- **Dry Run** (preview changes):

  ```bash
  python invoice_renamer.py path/to/invoice.pdf --dry-run
  ```

- **Move to Directory**:

  ```bash
  python invoice_renamer.py path/to/invoice.pdf --move-to /path/to/organized/documents
  ```

- **Process All Pages** (for multi-page PDFs):

  ```bash
  python invoice_renamer.py path/to/invoice.pdf --all-pages
  ```

### Examples

```bash
# Rename with preview
python invoice_renamer.py "Business Name Document 20240315.pdf" --dry-run

# Rename and move to organized folder
python invoice_renamer.py invoice.pdf --move-to ./organized/

# Process complex multi-page document
python invoice_renamer.py complex-statement.pdf --all-pages --move-to ./statements/
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
python3 ~/Documents/Code/osx-file-renamer/invoice_renamer.py "$@" --dry-run
```

## Naming Convention

Files are renamed using the following format:

```
Business Name [Account-Type] Document-Type [Last4] [- Patient/Animal] [Invoice#] Date
```

Examples:

- `Chase Credit Card Statement 20240115.pdf`
- `Wells Fargo Checking Statement 4567 20240101.pdf`
- `Tesla Portfolio Statement 20231231.pdf`
- `Dr Smith Invoice ACS-1234 20240115.pdf`
- `Vet Clinic Invoice - Whiskers 20240110.pdf`

## Supported Document Types

- **Invoices** - Bills and payment requests
- **Statements** - Bank, credit card, and account statements
- **Receipts** - Payment confirmations
- **Confirmations** - Order and transaction confirmations
- **Notices** - Account updates and notifications
- **Letters** - General correspondence
- **Reports** - Financial and summary reports

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
| `--all-pages` | Process all PDF pages (vs. first page only) | False |

## Logging

Logs are automatically written to a platform-specific temporary directory (typically `/tmp` on Unix-like systems or system temp directory on Windows) with automatic rotation to keep file size manageable. Log levels include DEBUG, INFO, WARNING, and ERROR.

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

The tool provides detailed error messages for common issues. Check the log file in your system's temporary directory for additional debugging information:

```bash
# On macOS/Linux
tail -f /tmp/invoice_renamer.log

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
pyenv exec pytest

# Run with coverage
pyenv exec pytest --cov=. --cov-report=term-missing

# Run in parallel
pyenv exec pytest -n auto

# Run specific test file
pyenv exec pytest tests/test_grok.py
```

### Code Quality

```bash
# Check code style
pyenv exec flake8

# View configuration
cat .flake8
```

### Project Structure

```
osx-file-renamer/
├── invoice_renamer.py      # Main application logic
├── grok.py                 # Grok API client and file processing
├── tests/                  # Test suite
│   ├── test_grok_*.py     # Grok module tests
│   ├── test_invoice_*.py  # Invoice renamer tests
│   ├── conftest.py        # Shared test fixtures
│   └── fixtures/          # Real test files for integration tests
├── requirements.txt        # Python dependencies
├── CLAUDE.md              # AI assistant guidance
└── README.md              # This file
```

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Ensure tests pass: `pyenv exec pytest`
6. Ensure code style is clean: `pyenv exec flake8`
7. Update documentation as needed
8. Commit your changes (`git commit -m 'Add amazing feature'`)
9. Push to the branch (`git push origin feature/amazing-feature`)
10. Open a Pull Request

### Development Guidelines

- Use Python 3.11+ features
- Follow PEP 8 style guide (enforced by flake8)
- Write tests for new features
- Update CLAUDE.md if architecture changes
- Never skip tests in test suite
- All imports at top of file (no function-level imports)

## License

This project is open source. See LICENSE file for details.

## Changelog

### Version 1.0.1

- **Security/Fix**: Limit account numbers and invoice numbers to last 4 digits only for privacy and naming consistency
- **Documentation**: Added data privacy warning about AI data transmission
- **macOS Integration**: Added guide for using Finder Quick Actions with example shortcut

### Version 1.0.0

- Initial release
- AI-powered document analysis
- Support for multiple file types and document categories
- Intelligent naming conventions
- Dry run and batch processing capabilities
