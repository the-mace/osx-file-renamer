# Test Fixtures

This directory contains real test files for integration testing of grok.py.

## Files

### Images

- **test_image.jpg** - Small (100x100) JPEG test image with cross pattern
- **test_image.png** - Same image in PNG format
- **test_large_image.jpg** - Larger (2000x2000) image for testing compression

### PDFs

- **test_text.pdf** - Text-based PDF with invoice content (can be extracted with pdftotext)
- **test_scanned.pdf** - Image-based PDF (simulates scanned document, requires OCR/vision)

### Text

- **test_content.txt** - Source text used to generate test_text.pdf

## Purpose

These fixtures are used for **integration tests** that verify:

1. Real PDF text extraction works
2. Real PDF to image conversion works
3. Real image processing and compression works
4. The full pipeline from file → processed content works

Unlike unit tests which mock everything, integration tests use these real files
to ensure the actual tools (pdftotext, pdftoppm, ImageMagick) work correctly.
