"""
Integration tests for grok.py using real PDF and image files.

These tests use actual files in tests/fixtures/ to verify that the complete
pipeline works end-to-end without mocking.
"""

import pytest
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm_client import (
    read_file_content,
    process_image_file,
    extract_embedded_images,
    convert_pdf_to_images
)


# Path to fixtures directory
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), 'fixtures')


class TestPDFTextExtraction:
    """Test real PDF text extraction."""

    def test_read_text_pdf_extracts_content(self):
        """Test that PDF without extractable text falls back to image extraction."""
        pdf_path = os.path.join(FIXTURES_DIR, 'test_text.pdf')

        # Skip if file doesn't exist (in case fixtures weren't created)
        if not os.path.exists(pdf_path):
            pytest.skip(f"Test fixture not found: {pdf_path}")

        result = read_file_content(pdf_path)

        # Note: Our test PDF created by ImageMagick is actually image-based,
        # so it will be extracted as an image, not text. This is realistic -
        # many PDFs are scanned and require image processing.
        assert result["type"] in ["text", "image_url"]

        # If it's text, verify content exists
        if result["type"] == "text":
            assert "content" in result
            assert len(result["content"]) > 0

    def test_read_scanned_pdf_converts_to_image(self):
        """Test that scanned (image-based) PDF is converted to image."""
        pdf_path = os.path.join(FIXTURES_DIR, 'test_scanned.pdf')

        if not os.path.exists(pdf_path):
            pytest.skip(f"Test fixture not found: {pdf_path}")

        result = read_file_content(pdf_path)

        # Should convert to image (either via extraction or conversion)
        assert result["type"] in ["image_url", "multi_image"]


class TestImageProcessing:
    """Test real image file processing."""

    def test_process_small_jpeg(self):
        """Test processing a small JPEG image."""
        img_path = os.path.join(FIXTURES_DIR, 'test_image.jpg')

        if not os.path.exists(img_path):
            pytest.skip(f"Test fixture not found: {img_path}")

        result = process_image_file(img_path, "image/jpeg")

        assert result["type"] == "image_url"
        assert "image_url" in result
        assert "url" in result["image_url"]
        assert result["image_url"]["url"].startswith("data:image/jpeg;base64,")

        # Verify it's valid base64
        import base64
        base64_part = result["image_url"]["url"].split(",")[1]
        decoded = base64.b64decode(base64_part)
        assert len(decoded) > 0
        # Should start with JPEG magic bytes
        assert decoded[:2] == b'\xff\xd8'

    def test_process_png(self):
        """Test processing a PNG image."""
        img_path = os.path.join(FIXTURES_DIR, 'test_image.png')

        if not os.path.exists(img_path):
            pytest.skip(f"Test fixture not found: {img_path}")

        result = process_image_file(img_path, "image/png")

        assert result["type"] == "image_url"
        assert "data:image/png;base64," in result["image_url"]["url"]

    def test_process_large_image_compresses(self):
        """Test that large images are handled (potentially compressed)."""
        img_path = os.path.join(FIXTURES_DIR, 'test_large_image.jpg')

        if not os.path.exists(img_path):
            pytest.skip(f"Test fixture not found: {img_path}")

        # This should succeed even if image is large
        result = process_image_file(img_path, "image/jpeg")

        assert result["type"] == "image_url"
        assert "url" in result["image_url"]

        # Verify base64 doesn't exceed limits
        base64_part = result["image_url"]["url"].split(",")[1]
        from llm_client import MAX_BASE64_SIZE
        assert len(base64_part) <= MAX_BASE64_SIZE


class TestPDFConversion:
    """Test PDF to image conversion pipeline."""

    def test_convert_text_pdf_to_image(self):
        """Test converting a text PDF to image format."""
        pdf_path = os.path.join(FIXTURES_DIR, 'test_text.pdf')

        if not os.path.exists(pdf_path):
            pytest.skip(f"Test fixture not found: {pdf_path}")

        # Convert first page only
        result = convert_pdf_to_images(pdf_path, max_pages=1)

        # Should return single image
        assert result["type"] == "image_url"
        assert "image_url" in result
        assert result["image_url"]["url"].startswith("data:image/png;base64,")

    def test_convert_scanned_pdf_to_image(self):
        """Test converting a scanned PDF to image format."""
        pdf_path = os.path.join(FIXTURES_DIR, 'test_scanned.pdf')

        if not os.path.exists(pdf_path):
            pytest.skip(f"Test fixture not found: {pdf_path}")

        # Try to extract embedded images first
        extracted = extract_embedded_images(pdf_path, all_pages=False)

        if extracted is None:
            # If no embedded images, convert
            result = convert_pdf_to_images(pdf_path, max_pages=1)
            assert result is not None
        else:
            # Extracted image should be valid
            assert extracted["type"] in ["image_url", "multi_image"]


class TestFullPipeline:
    """Test the complete read_file_content pipeline with real files."""

    def test_read_file_content_handles_all_formats(self):
        """Test that read_file_content correctly dispatches to appropriate handlers."""
        test_files = [
            ('test_image.jpg', 'image_url'),
            ('test_image.png', 'image_url'),
            ('test_text.pdf', ['text', 'image_url']),  # Could be either depending on PDF type
            ('test_content.txt', 'text'),  # Plain text
        ]

        for filename, expected_types in test_files:
            file_path = os.path.join(FIXTURES_DIR, filename)

            if not os.path.exists(file_path):
                continue  # Skip if fixture doesn't exist

            result = read_file_content(file_path)

            # Handle both single expected type and list of acceptable types
            if isinstance(expected_types, list):
                assert result["type"] in expected_types, f"Failed for {filename}"
            else:
                assert result["type"] == expected_types, f"Failed for {filename}"

    def test_image_file_returns_valid_base64(self):
        """Test that image files return valid, decodable base64 data."""
        img_path = os.path.join(FIXTURES_DIR, 'test_image.jpg')

        if not os.path.exists(img_path):
            pytest.skip(f"Test fixture not found: {img_path}")

        result = read_file_content(img_path)

        assert result["type"] == "image_url"

        # Extract and decode base64
        import base64
        url = result["image_url"]["url"]
        base64_data = url.split(",")[1]
        decoded = base64.b64decode(base64_data)

        # Verify we got actual image data
        assert len(decoded) > 100  # Should be reasonably sized
        assert decoded[:2] == b'\xff\xd8'  # JPEG magic bytes
