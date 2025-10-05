# OSX File Renamer

A command-line tool for automatically renaming invoice and document files based on their content using AI analysis through the Grok API.

## Overview

This tool analyzes invoice, statement, and document files using AI (Grok API) to extract business names, document types, and dates, then applies a consistent naming convention to help organize files.

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
- macOS (designed for OSX)
- Python 3.11 or higher
- ImageMagick (`brew install imagemagick`)
- Poppler tools (`brew install poppler`)
- pngquant (optional, for better compression: `brew install pngquant`)

### API Requirements
- Grok API key from xAI
- Set as environment variable `GROK_API_KEY` or in `~/.env` file

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

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
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

Logs are automatically written to `/tmp/invoice_renamer.log` with automatic rotation to keep file size manageable. Log levels include DEBUG, INFO, WARNING, and ERROR.

## Troubleshooting

### Common Issues

1. **API Key Not Found**
   - Ensure `GROK_API_KEY` is set in environment or `~/.env` file

2. **File Too Large**
   - Images/PDFs are automatically compressed if over size limits
   - For extremely large files, try processing individual pages

3. **PDF Processing Issues**
   - Install ImageMagick and Poppler tools
   - Scanned PDFs will be converted to images automatically

4. **Permission Errors**
   - Ensure write permissions in target directory
   - Check file is not currently open in another application

### Dependencies

Install system dependencies:
```bash
brew install imagemagick poppler pngquant
```

### Error Messages

The tool provides detailed error messages for common issues. Check the log file at `/tmp/invoice_renamer.log` for additional debugging information.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests and update documentation
5. Submit a pull request

## License

This project is open source. See LICENSE file for details.

## Changelog

### Version 1.0.0
- Initial release
- AI-powered document analysis
- Support for multiple file types and document categories
- Intelligent naming conventions
- Dry run and batch processing capabilities
