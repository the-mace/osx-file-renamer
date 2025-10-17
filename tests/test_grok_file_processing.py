import pytest
import os
import base64
from unittest.mock import patch, MagicMock

# Import the functions to test from grok.py
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from grok import (
    process_image_file, compress_image, read_file_content,
    MAX_RAW_SIZE
)


class TestProcessImageFile:

    def test_process_image_file_success(self, tmp_path, sample_jpeg_data):
        """Test successful processing of a valid image within size limits."""
        image_file = tmp_path / "test.jpg"
        image_file.write_bytes(sample_jpeg_data)

        result = process_image_file(str(image_file))

        assert "type" in result
        assert result["type"] == "image_url"
        assert "image_url" in result
        assert "url" in result["image_url"]
        assert result["image_url"]["url"].startswith("data:image/jpeg;base64,")
        assert result["image_url"]["detail"] == "high"

        # Verify base64 encoding
        base64_part = result["image_url"]["url"].split(",")[1]
        decoded = base64.b64decode(base64_part)
        assert decoded == sample_jpeg_data

    @patch('grok.compress_image')
    def test_process_image_file_compression_needed(self, mock_compress, tmp_path, sample_jpeg_data):
        """Test that large images trigger compression."""
        # Create oversized data - make it much larger than MAX_RAW_SIZE
        large_data = sample_jpeg_data * (MAX_RAW_SIZE // len(sample_jpeg_data) + 1000)
        image_file = tmp_path / "large.jpg"
        image_file.write_bytes(large_data)

        # Mock compression to return smaller data
        mock_compress.return_value = sample_jpeg_data

        with patch('builtins.open', create=True) as mock_open:
            mock_file = MagicMock()
            mock_file.read.return_value = large_data
            mock_open.return_value.__enter__.return_value = mock_file

            result = process_image_file(str(image_file))

            # Verify compression was called
            mock_compress.assert_called_once()
            assert result["type"] == "image_url"

    def test_process_image_file_unsupported_format(self):
        """Test that unsupported formats raise an error via sys.exit."""
        with pytest.raises(SystemExit):
            # This would normally be caught by read_file_content, but let's test directly
            with patch('builtins.open', side_effect=Exception("Test error")):
                process_image_file("nonexistent.xyz")


class TestCompressImage:

    def test_compress_image_failure_returns_none(self):
        """Test that compression failure returns None."""
        result = compress_image("nonexistent.jpg", b"data", 1000)
        assert result is None


class TestReadFileContent:

    def test_read_file_content_text_file(self, tmp_path):
        """Test reading text files."""
        text_file = tmp_path / "test.txt"
        test_content = "This is test content"
        text_file.write_text(test_content)

        result = read_file_content(str(text_file))

        assert result["type"] == "text"
        assert result["content"] == test_content

    def test_read_file_content_nonexistent_file(self):
        """Test handling of nonexistent files."""
        with pytest.raises(SystemExit):
            read_file_content("nonexistent.xyz")

    @patch('grok.subprocess.run')
    @patch('os.path.exists', return_value=True)
    def test_read_file_content_pdf_with_text(self, mock_exists, mock_run, tmp_path):
        """Test PDF processing with text extraction."""
        pdf_file = tmp_path / "test.pdf"

        # Mock pdftotext command
        mock_run.return_value = MagicMock(returncode=0, stdout="PDF content here")

        result = read_file_content(str(pdf_file))

        assert result["type"] == "text"
        assert "PDF content here" in result["content"]

    @patch('grok.extract_embedded_images')
    @patch('grok.subprocess.run')
    def test_read_file_content_pdf_fallback_to_images(self, mock_run, mock_extract, tmp_path):
        """Test PDF fallback to image processing."""
        pdf_file = tmp_path / "test.pdf"

        # Mock pdftotext failure with minimal text
        mock_run.return_value = MagicMock(returncode=0, stdout="   ")
        mock_extract.return_value = None

        with patch('grok.convert_pdf_to_images') as mock_convert:
            mock_convert.return_value = {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64,test"}
            }

            with patch('os.path.exists', return_value=True):
                result = read_file_content(str(pdf_file))

                # Should return the image when conversion succeeds
                assert result["type"] == "image_url"
                mock_convert.assert_called_once_with(str(pdf_file), max_pages=1)

    def test_read_file_content_image_file(self, tmp_path, sample_jpeg_data):
        """Test processing image files."""
        image_file = tmp_path / "test.jpg"
        image_file.write_bytes(sample_jpeg_data)

        with patch('grok.process_image_file') as mock_process:
            mock_process.return_value = {
                "type": "image_url",
                "image_url": {"url": "data:image/jpeg;base64,test"}
            }

            result = read_file_content(str(image_file))

            assert result["type"] == "image_url"
            mock_process.assert_called_once()

    def test_read_file_content_binary_unsupported(self, tmp_path):
        """Test handling of unsupported binary files."""
        bin_file = tmp_path / "test.bin"
        bin_file.write_bytes(b"binary data here")

        with patch('builtins.open', side_effect=UnicodeDecodeError("utf-8", b"", 0, 1, "test")):
            with pytest.raises(SystemExit):
                read_file_content(str(bin_file))
