import pytest
import os
import base64
import subprocess
from unittest.mock import patch, MagicMock

# Import the functions to test from grok.py
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm_client import (
    process_image_file, compress_image, read_file_content,
    extract_embedded_images, convert_pdf_to_images,
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

    @patch('llm_client.compress_image')
    def test_process_image_file_compression_needed(self, mock_compress, tmp_path, sample_jpeg_data):
        """Test that large images trigger compression."""
        # Create oversized data - make it much larger than MAX_RAW_SIZE
        large_data = sample_jpeg_data * (MAX_RAW_SIZE // len(sample_jpeg_data) + 1000)
        image_file = tmp_path / "large.jpg"
        image_file.write_bytes(large_data)

        # Mock compression to return smaller data
        mock_compress.return_value = sample_jpeg_data

        result = process_image_file(str(image_file))

        # Verify compression was called with correct parameters
        mock_compress.assert_called_once_with(str(image_file), large_data, MAX_RAW_SIZE)
        assert result["type"] == "image_url"

        # Verify the result uses the compressed data
        base64_part = result["image_url"]["url"].split(",")[1]
        decoded = base64.b64decode(base64_part)
        assert decoded == sample_jpeg_data

    def test_process_image_file_unsupported_format(self):
        """Test that unsupported formats raise an error via sys.exit."""
        with pytest.raises(SystemExit):
            # This would normally be caught by read_file_content, but let's test directly
            with patch('builtins.open', side_effect=Exception("Test error")):
                process_image_file("nonexistent.xyz")

    def test_process_image_file_with_none_mime_type(self, tmp_path, sample_jpeg_data):
        """Test processing image with None mime_type uses fallback."""
        image_file = tmp_path / "test.jpg"
        image_file.write_bytes(sample_jpeg_data)

        result = process_image_file(str(image_file), mime_type=None)

        assert "type" in result
        assert result["type"] == "image_url"
        # Should use 'image/jpeg' as fallback
        assert "data:image/jpeg;base64," in result["image_url"]["url"]

    @patch('llm_client.compress_image')
    def test_process_image_file_compression_fails_exits(self, mock_compress, tmp_path, sample_jpeg_data):
        """Test that failed compression followed by oversized image exits."""
        # Create oversized data
        large_data = sample_jpeg_data * (MAX_RAW_SIZE // len(sample_jpeg_data) + 1000)
        image_file = tmp_path / "large.jpg"
        image_file.write_bytes(large_data)

        # Mock compression returns None (failure)
        mock_compress.return_value = None

        with pytest.raises(SystemExit) as excinfo:
            process_image_file(str(image_file))

        assert excinfo.value.code == 1

    def test_process_image_file_base64_size_check(self, tmp_path):
        """Test that base64 size exceeding limit causes exit."""
        # Create data that would exceed MAX_BASE64_SIZE after encoding
        # base64 encoding increases size by ~33%, so we need data > MAX_BASE64_SIZE/1.33
        from llm_client import MAX_BASE64_SIZE
        large_data = b'x' * (MAX_BASE64_SIZE + 1000)
        image_file = tmp_path / "huge.jpg"
        image_file.write_bytes(large_data)

        with patch('llm_client.compress_image', return_value=None):
            with pytest.raises(SystemExit) as excinfo:
                process_image_file(str(image_file))

            assert excinfo.value.code == 1


class TestCompressImage:

    def test_compress_image_failure_returns_none(self):
        """Test that compression failure returns None."""
        result = compress_image("nonexistent.jpg", b"data", 1000)
        assert result is None

    @patch('subprocess.run')
    @patch('tempfile.NamedTemporaryFile')
    @patch('os.path.exists')
    def test_compress_image_png_to_jpeg_success(self, mock_exists, mock_tempfile, mock_run, sample_jpeg_data):
        """Test successful PNG to JPEG compression."""
        # Create a smaller compressed version
        compressed_data = sample_jpeg_data[:len(sample_jpeg_data) // 2]

        # Mock temporary file
        mock_temp = MagicMock()
        mock_temp.name = '/tmp/test.jpg'
        mock_tempfile.return_value.__enter__.return_value = mock_temp

        # Mock subprocess success
        mock_run.return_value = MagicMock(returncode=0)

        # Mock file operations
        def exists_side_effect(path):
            return path == '/tmp/test.jpg'
        mock_exists.side_effect = exists_side_effect

        with patch('builtins.open', create=True) as mock_open:
            mock_file = MagicMock()
            mock_file.read.return_value = compressed_data
            mock_open.return_value.__enter__.return_value = mock_file

            with patch('os.unlink'):
                result = compress_image("test.png", b"large_data", 1000)

        assert result == compressed_data
        # Verify ImageMagick convert was called
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == 'convert'
        assert 'test.png' in call_args
        assert '-quality' in call_args

    @patch('subprocess.run')
    @patch('tempfile.NamedTemporaryFile')
    @patch('os.path.exists')
    def test_compress_image_jpeg_recompression(self, mock_exists, mock_tempfile, mock_run, sample_jpeg_data):
        """Test JPEG recompression with lower quality."""
        compressed_data = sample_jpeg_data[:len(sample_jpeg_data) // 2]

        mock_temp = MagicMock()
        mock_temp.name = '/tmp/test.jpg'
        mock_tempfile.return_value.__enter__.return_value = mock_temp

        mock_run.return_value = MagicMock(returncode=0)

        def exists_side_effect(path):
            return path == '/tmp/test.jpg'
        mock_exists.side_effect = exists_side_effect

        with patch('builtins.open', create=True) as mock_open:
            mock_file = MagicMock()
            mock_file.read.return_value = compressed_data
            mock_open.return_value.__enter__.return_value = mock_file

            with patch('os.unlink'):
                result = compress_image("test.jpg", b"large_jpeg_data", 1000)

        assert result == compressed_data

    @patch('subprocess.run')
    @patch('tempfile.NamedTemporaryFile')
    @patch('os.path.exists')
    def test_compress_image_scaling_fallback(self, mock_exists, mock_tempfile, mock_run, sample_jpeg_data):
        """Test image scaling when quality reduction isn't enough."""
        # Make data large enough that quality reduction won't help
        large_data = sample_jpeg_data * 100
        compressed_data = sample_jpeg_data[:len(sample_jpeg_data) // 4]
        call_count = [0]

        def run_side_effect(*args, **kwargs):
            call_count[0] += 1
            return MagicMock(returncode=0)

        mock_run.side_effect = run_side_effect

        mock_temp = MagicMock()
        mock_temp.name = '/tmp/test.jpg'
        mock_tempfile.return_value.__enter__.return_value = mock_temp

        def exists_side_effect(path):
            return path == '/tmp/test.jpg'
        mock_exists.side_effect = exists_side_effect

        with patch('builtins.open', create=True) as mock_open:
            # Return small data only for scaled versions (which have -resize in command)
            def read_side_effect():
                # Check if we're in a scaling attempt by checking call count
                # PNG compression tries qualities 85,70,50,30 (4 attempts) before scaling
                if call_count[0] > 4:
                    return compressed_data
                return large_data  # Still too large

            mock_file = MagicMock()
            mock_file.read.side_effect = read_side_effect
            mock_open.return_value.__enter__.return_value = mock_file

            with patch('os.unlink'):
                result = compress_image("test.png", large_data, 1000)

        assert result == compressed_data
        # Verify scaling was attempted (more than just quality attempts)
        assert call_count[0] > 4

    @patch('subprocess.run')
    def test_compress_image_subprocess_timeout(self, mock_run):
        """Test handling of subprocess timeout during compression."""
        mock_run.side_effect = subprocess.TimeoutExpired('convert', 30)

        result = compress_image("test.png", b"data", 1000)

        assert result is None

    @patch('subprocess.run')
    def test_compress_image_convert_not_found(self, mock_run):
        """Test handling when ImageMagick convert is not available."""
        mock_run.side_effect = FileNotFoundError("convert not found")

        result = compress_image("test.jpg", b"data", 1000)

        assert result is None

    @patch('subprocess.run')
    @patch('tempfile.NamedTemporaryFile')
    @patch('os.path.exists', return_value=False)
    def test_compress_image_temp_file_not_created(self, mock_exists, mock_tempfile, mock_run):
        """Test handling when temporary file is not created."""
        mock_temp = MagicMock()
        mock_temp.name = '/tmp/test.jpg'
        mock_tempfile.return_value.__enter__.return_value = mock_temp

        mock_run.return_value = MagicMock(returncode=0)

        result = compress_image("test.png", b"data", 1000)

        assert result is None

    @patch('subprocess.run')
    @patch('tempfile.NamedTemporaryFile')
    @patch('os.path.exists')
    def test_compress_image_tries_multiple_quality_levels(self, mock_exists, mock_tempfile, mock_run, sample_jpeg_data):
        """Test that compression tries multiple quality levels."""
        # All attempts fail to get small enough
        mock_temp = MagicMock()
        mock_temp.name = '/tmp/test.jpg'
        mock_tempfile.return_value.__enter__.return_value = mock_temp

        mock_run.return_value = MagicMock(returncode=0)
        mock_exists.return_value = True

        with patch('builtins.open', create=True) as mock_open:
            # Always return data that's still too large
            mock_file = MagicMock()
            mock_file.read.return_value = sample_jpeg_data
            mock_open.return_value.__enter__.return_value = mock_file

            with patch('os.unlink'):
                result = compress_image("test.png", sample_jpeg_data, 100)  # Very small limit

        # Should return None after all attempts fail
        assert result is None
        # Verify multiple quality levels were tried
        assert mock_run.call_count > 1


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

    @patch('llm_client.subprocess.run')
    @patch('os.path.exists', return_value=True)
    def test_read_file_content_pdf_with_text(self, mock_exists, mock_run, tmp_path):
        """Test PDF processing with text extraction."""
        pdf_file = tmp_path / "test.pdf"

        # Mock pdftotext command
        mock_run.return_value = MagicMock(returncode=0, stdout="PDF content here")

        result = read_file_content(str(pdf_file))

        assert result["type"] == "text"
        assert "PDF content here" in result["content"]

    @patch('llm_client.extract_embedded_images')
    @patch('llm_client.subprocess.run')
    def test_read_file_content_pdf_fallback_to_images(self, mock_run, mock_extract, tmp_path):
        """Test PDF fallback to image processing."""
        pdf_file = tmp_path / "test.pdf"

        # Mock pdftotext failure with minimal text
        mock_run.return_value = MagicMock(returncode=0, stdout="   ")
        mock_extract.return_value = None

        with patch('llm_client.convert_pdf_to_images') as mock_convert:
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

        with patch('llm_client.process_image_file') as mock_process:
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


class TestExtractEmbeddedImages:

    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('glob.glob')
    @patch('llm_client.process_image_file')
    def test_extract_embedded_images_single_image_success(self, mock_process, mock_glob, mock_exists, mock_run, tmp_path):
        """Test successful extraction of a single embedded image."""
        # Mock pdfimages found
        mock_exists.return_value = True

        # Mock successful extraction
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        # Mock extracted file
        extracted_file = str(tmp_path / "extracted-000.jpg")
        mock_glob.return_value = [extracted_file]

        # Mock process_image_file
        mock_process.return_value = {
            "type": "image_url",
            "image_url": {"url": "data:image/jpeg;base64,test"}
        }

        with patch('tempfile.TemporaryDirectory') as mock_tempdir:
            mock_tempdir.return_value.__enter__.return_value = str(tmp_path)

            result = extract_embedded_images("test.pdf", all_pages=False)

        assert result["type"] == "image_url"
        mock_process.assert_called_once_with(extracted_file, "image/jpg")

        # Verify pdfimages was called with first page only flags
        call_args = mock_run.call_args[0][0]
        assert '-f' in call_args
        assert '-l' in call_args
        assert '1' in call_args

    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('glob.glob')
    @patch('llm_client.process_image_file')
    def test_extract_embedded_images_multiple_images_all_pages(self, mock_process, mock_glob, mock_exists, mock_run, tmp_path):
        """Test extraction of multiple images with all_pages=True."""
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        # Mock multiple extracted files
        files = [str(tmp_path / f"extracted-00{i}.jpg") for i in range(3)]
        mock_glob.return_value = files

        mock_process.return_value = {
            "type": "image_url",
            "image_url": {"url": "data:image/jpeg;base64,test"}
        }

        with patch('tempfile.TemporaryDirectory') as mock_tempdir:
            mock_tempdir.return_value.__enter__.return_value = str(tmp_path)

            result = extract_embedded_images("test.pdf", all_pages=True)

        assert result["type"] == "multi_image"
        assert len(result["images"]) == 3
        assert mock_process.call_count == 3

        # Verify pdfimages was called without page limit flags
        call_args = mock_run.call_args[0][0]
        assert '-f' not in call_args

    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_extract_embedded_images_pdfimages_not_found(self, mock_exists, mock_run):
        """Test handling when pdfimages is not installed."""
        # Mock pdfimages not found in common locations
        mock_exists.return_value = False

        # Mock 'which' command failing
        mock_run.side_effect = subprocess.CalledProcessError(1, 'which')

        result = extract_embedded_images("test.pdf")

        assert result is None

    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('glob.glob')
    def test_extract_embedded_images_no_images_found(self, mock_glob, mock_exists, mock_run, tmp_path):
        """Test when pdfimages runs but finds no embedded images."""
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        # No files extracted
        mock_glob.return_value = []

        with patch('tempfile.TemporaryDirectory') as mock_tempdir:
            mock_tempdir.return_value.__enter__.return_value = str(tmp_path)

            result = extract_embedded_images("test.pdf")

        assert result is None

    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_extract_embedded_images_pdfimages_fails(self, mock_exists, mock_run):
        """Test handling of pdfimages execution failure."""
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(returncode=1, stderr="Error processing PDF")

        with patch('tempfile.TemporaryDirectory') as mock_tempdir:
            mock_tempdir.return_value.__enter__.return_value = "/tmp/test"

            extract_result = extract_embedded_images("test.pdf")

        assert extract_result is None

    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_extract_embedded_images_timeout(self, mock_exists, mock_run):
        """Test handling of pdfimages timeout."""
        mock_exists.return_value = True
        mock_run.side_effect = subprocess.TimeoutExpired('pdfimages', 15)

        with patch('tempfile.TemporaryDirectory') as mock_tempdir:
            mock_tempdir.return_value.__enter__.return_value = "/tmp/test"

            result = extract_embedded_images("test.pdf")

        assert result is None

    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('glob.glob')
    @patch('llm_client.HAS_PIL', False)
    def test_extract_embedded_images_pbm_without_pil(self, mock_glob, mock_exists, mock_run, tmp_path):
        """Test PBM conversion fallback to ImageMagick when PIL not available."""
        mock_exists.return_value = True

        # Mock pdfimages extraction success
        def run_side_effect(*args, **kwargs):
            cmd = args[0][0] if args else ""
            if 'pdfimages' in str(cmd):
                return MagicMock(returncode=0)
            elif 'convert' in str(cmd):
                return MagicMock(returncode=0)
            return MagicMock(returncode=1)

        mock_run.side_effect = run_side_effect

        pbm_file = str(tmp_path / "extracted-000.pbm")
        mock_glob.return_value = [pbm_file]

        with patch('tempfile.TemporaryDirectory') as mock_tempdir:
            mock_tempdir.return_value.__enter__.return_value = str(tmp_path)

            with patch('llm_client.process_image_file') as mock_process:
                mock_process.return_value = {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,test"}
                }

                result = extract_embedded_images("test.pdf")

        # Should still succeed with ImageMagick fallback
        assert result is not None


class TestConvertPdfToImages:

    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('os.unlink')
    def test_convert_pdf_to_images_single_page(self, mock_unlink, mock_exists, mock_run, tmp_path, sample_jpeg_data):
        """Test converting a single page PDF to image."""
        # Mock pdftoppm found
        mock_exists.return_value = True

        # Mock successful conversion
        mock_run.return_value = MagicMock(returncode=0)

        # Create mock generated image
        temp_image = str(tmp_path / "temp-1.png")
        with open(temp_image, 'wb') as f:
            f.write(sample_jpeg_data)

        def exists_side_effect(path):
            return path == temp_image or '/bin/pdftoppm' in path

        mock_exists.side_effect = exists_side_effect

        with patch('tempfile.NamedTemporaryFile') as mock_tempfile:
            mock_temp = MagicMock()
            mock_temp.name = str(tmp_path / "temp.png")
            mock_tempfile.return_value.__enter__.return_value = mock_temp

            with patch('builtins.open', create=True) as mock_open:
                mock_file = MagicMock()
                mock_file.read.return_value = sample_jpeg_data
                mock_open.return_value.__enter__.return_value = mock_file

                result = convert_pdf_to_images("test.pdf", max_pages=1)

        assert result["type"] == "image_url"
        assert "image_url" in result

        # Verify pdftoppm was called with correct arguments
        call_args = mock_run.call_args[0][0]
        assert '-png' in call_args
        assert '-r' in call_args
        assert '100' in call_args  # DPI
        assert '-l' in call_args
        assert '1' in call_args  # max_pages

    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('os.unlink')
    def test_convert_pdf_to_images_multiple_pages(self, mock_unlink, mock_exists, mock_run, tmp_path, sample_jpeg_data):
        """Test converting multiple pages to images."""
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        # Create mock generated images for 3 pages
        temp_images = [str(tmp_path / f"temp-{i}.png") for i in range(1, 4)]
        for img_path in temp_images:
            with open(img_path, 'wb') as f:
                f.write(sample_jpeg_data)

        def exists_side_effect(path):
            return path in temp_images or '/bin/pdftoppm' in path

        mock_exists.side_effect = exists_side_effect

        with patch('tempfile.NamedTemporaryFile') as mock_tempfile:
            mock_temp = MagicMock()
            mock_temp.name = str(tmp_path / "temp.png")
            mock_tempfile.return_value.__enter__.return_value = mock_temp

            with patch('builtins.open', create=True) as mock_open:
                mock_file = MagicMock()
                mock_file.read.return_value = sample_jpeg_data
                mock_open.return_value.__enter__.return_value = mock_file

                result = convert_pdf_to_images("test.pdf", max_pages=5)

        assert result["type"] == "multi_image"
        assert len(result["images"]) == 3

    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_convert_pdf_to_images_pdftoppm_not_found(self, mock_exists, mock_run):
        """Test handling when pdftoppm is not installed."""
        # Mock pdftoppm not found
        mock_exists.return_value = False
        mock_run.side_effect = subprocess.CalledProcessError(1, 'which')

        with patch('tempfile.NamedTemporaryFile') as mock_tempfile:
            mock_temp = MagicMock()
            mock_temp.name = "/tmp/temp.png"
            mock_tempfile.return_value.__enter__.return_value = mock_temp

            # This raises Exception which then gets caught and turned into SystemExit
            with pytest.raises(SystemExit):
                convert_pdf_to_images("test.pdf", max_pages=1)

    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_convert_pdf_to_images_timeout(self, mock_exists, mock_run):
        """Test handling of pdftoppm timeout."""
        mock_exists.return_value = True
        mock_run.side_effect = subprocess.TimeoutExpired('pdftoppm', 60)

        with pytest.raises(SystemExit):
            convert_pdf_to_images("test.pdf", max_pages=1)

    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_convert_pdf_to_images_conversion_fails(self, mock_exists, mock_run):
        """Test handling of conversion failure."""
        mock_exists.return_value = True
        mock_run.side_effect = subprocess.CalledProcessError(1, 'pdftoppm', stderr="Error")

        with pytest.raises(SystemExit):
            convert_pdf_to_images("test.pdf", max_pages=1)

    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_convert_pdf_to_images_no_images_generated(self, mock_exists, mock_run, tmp_path):
        """Test handling when no images are generated."""
        # Mock successful pdftoppm run but no images created
        def run_side_effect(*args, **kwargs):
            return MagicMock(returncode=0)

        mock_run.side_effect = run_side_effect

        # Mock that pdftoppm exists but generated images don't
        def exists_side_effect(path):
            if '/pdftoppm' in path or 'pdftoppm' == os.path.basename(path):
                return True
            # Generated images don't exist
            return False

        mock_exists.side_effect = exists_side_effect

        with patch('tempfile.NamedTemporaryFile') as mock_tempfile:
            mock_temp = MagicMock()
            mock_temp.name = str(tmp_path / "temp.png")
            mock_tempfile.return_value.__enter__.return_value = mock_temp

            # This raises Exception which then gets caught and turned into SystemExit
            with pytest.raises(SystemExit):
                convert_pdf_to_images("test.pdf", max_pages=1)

    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('os.unlink')
    def test_convert_pdf_to_images_compression_with_pngquant(self, mock_unlink, mock_exists, mock_run, tmp_path, sample_jpeg_data):
        """Test image compression using pngquant for large images."""
        # Make data large enough to trigger compression
        large_data = sample_jpeg_data * (MAX_RAW_SIZE // len(sample_jpeg_data) + 100)

        def run_side_effect(*args, **kwargs):
            cmd = args[0][0] if args else ""
            if 'pdftoppm' in str(cmd):
                return MagicMock(returncode=0)
            elif 'pngquant' in str(cmd):
                # Simulate pngquant success
                return MagicMock(returncode=0)
            return MagicMock(returncode=1)

        mock_run.side_effect = run_side_effect

        temp_image = str(tmp_path / "temp-1.png")
        compressed_image = str(tmp_path / "temp-1_compressed.png")

        def exists_side_effect(path):
            if path == temp_image:
                return True
            if path == compressed_image:
                return True
            return '/bin/pdftoppm' in path

        mock_exists.side_effect = exists_side_effect

        with patch('tempfile.NamedTemporaryFile') as mock_tempfile:
            mock_temp = MagicMock()
            mock_temp.name = str(tmp_path / "temp.png")
            mock_tempfile.return_value.__enter__.return_value = mock_temp

            with patch('builtins.open', create=True) as mock_open:
                call_count = [0]

                def read_side_effect():
                    call_count[0] += 1
                    # First call returns large data, second call returns compressed
                    if call_count[0] == 1:
                        return large_data
                    return sample_jpeg_data

                mock_file = MagicMock()
                mock_file.read.side_effect = read_side_effect
                mock_open.return_value.__enter__.return_value = mock_file

                result = convert_pdf_to_images("test.pdf", max_pages=1)

        # Should succeed with compression
        assert result is not None
