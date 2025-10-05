#!/usr/bin/env python3
"""
Grok API client script for processing text and images.

This script provides a command-line interface to interact with the Grok API,
supporting text prompts and analysis of various file types including PDFs,
images, and documents.

Requirements:
- GROK_API_KEY environment variable or ~/.env file
- ImageMagick (for image compression)
- Poppler tools (for PDF processing): pdftotext, pdftoppm, pdfimages
"""

import os
import sys
import argparse
import urllib.request
import urllib.parse
import json
import base64
import mimetypes
import subprocess
import tempfile
from typing import Optional, Dict, Any, List, Union

class GrokError(Exception):
    """Base exception for Grok API client errors"""
    pass

class FileProcessingError(GrokError):
    """Raised when file processing fails"""
    pass

class APIError(GrokError):
    """Raised when API calls fail"""
    pass

# Constants
MAX_RAW_SIZE = 7_500_000  # ~7.5MB raw = ~10MB base64
MAX_BASE64_SIZE = 10_000_000  # 10MB base64 limit
DEFAULT_PDF_DPI = 100
PDF_EXTRACTION_TIMEOUT = 15
CONVERSION_TIMEOUT = 60
COMPRESSION_TIMEOUT = 30
MIN_MEANINGFUL_TEXT = 10
ENV_FILE_PATH = "~/.env"
DEFAULT_MODEL = "grok-4-fast-reasoning"
VISION_MODEL = "grok-2-vision-1212"
API_URL = "https://api.x.ai/v1/chat/completions"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Supported file extensions
IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif']
COMPRESSED_FORMATS = ['.png', '.bmp', '.tiff', '.tif', '.pbm', '.ppm', '.pgm']

def process_image_file(file_path: str, mime_type: Optional[str] = None) -> Dict[str, Any]:
    """Process image file and return appropriate format for Grok API with size optimization"""
    try:
        with open(file_path, 'rb') as f:
            file_data = f.read()

        if len(file_data) > MAX_RAW_SIZE:
            print(f"Image too large ({len(file_data):,} bytes), compressing...", file=sys.stderr)

            # Try to compress the image using various methods
            compressed_data = compress_image(file_path, file_data, MAX_RAW_SIZE)
            if compressed_data:
                file_data = compressed_data
            else:
                # Final hard check - fail if still too large
                print(f"Error: Image still too large after compression ({len(file_data):,} bytes raw, would be {int(len(file_data) * 1.33):,} bytes base64)", file=sys.stderr)
                print(f"Maximum allowed: {MAX_RAW_SIZE:,} bytes raw ({MAX_BASE64_SIZE:,} bytes base64 limit)", file=sys.stderr)
                sys.exit(1)

        base64_data = base64.b64encode(file_data).decode('utf-8')

        # Double check base64 size
        if len(base64_data) > MAX_BASE64_SIZE:
            print(f"Error: Base64 image size ({len(base64_data):,} bytes) exceeds {MAX_BASE64_SIZE:,} bytes limit", file=sys.stderr)
            sys.exit(1)

        return {
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime_type or 'image/jpeg'};base64,{base64_data}",
                "detail": "high"
            }
        }
    except Exception as e:
        print(f"Error processing image file '{file_path}': {e}", file=sys.stderr)
        sys.exit(1)

def compress_image(file_path: str, original_data: bytes, max_size: int) -> Optional[bytes]:
    """Try various image compression methods to reduce file size

    Args:
        file_path: Path to the image file
        original_data: Original image data as bytes
        max_size: Maximum allowed size in bytes

    Returns:
        Compressed image data as bytes, or None if compression failed
    """
    file_ext = os.path.splitext(file_path)[1].lower()

    try:
        # Method 1: Try converting to JPEG with quality reduction (if not already JPEG)
        if file_ext in COMPRESSED_FORMATS:
            for quality in [85, 70, 50, 30]:
                try:
                    # Use ImageMagick convert if available
                    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                        temp_path = tmp_file.name

                    result = subprocess.run(['convert', file_path, '-quality', str(quality), temp_path],
                                          capture_output=True, text=True, timeout=COMPRESSION_TIMEOUT)

                    if result.returncode == 0 and os.path.exists(temp_path):
                        with open(temp_path, 'rb') as f:
                            compressed_data = f.read()
                        os.unlink(temp_path)

                        if len(compressed_data) <= max_size:
                            print(f"Compressed to JPEG quality {quality}: {len(compressed_data):,} bytes", file=sys.stderr)
                            return compressed_data
                    else:
                        if os.path.exists(temp_path):
                            os.unlink(temp_path)

                except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                    continue

        # Method 2: For JPEG files, try re-compressing with lower quality
        elif file_ext in ['.jpg', '.jpeg']:
            for quality in [70, 50, 30, 20]:
                try:
                    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                        temp_path = tmp_file.name

                    result = subprocess.run(['convert', file_path, '-quality', str(quality), temp_path],
                                          capture_output=True, text=True, timeout=COMPRESSION_TIMEOUT)

                    if result.returncode == 0 and os.path.exists(temp_path):
                        with open(temp_path, 'rb') as f:
                            compressed_data = f.read()
                        os.unlink(temp_path)

                        if len(compressed_data) <= max_size:
                            print(f"Recompressed JPEG to quality {quality}: {len(compressed_data):,} bytes", file=sys.stderr)
                            return compressed_data
                    else:
                        if os.path.exists(temp_path):
                            os.unlink(temp_path)

                except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                    continue

        # Method 3: Try scaling down the image
        for scale in ['75%', '50%', '25%']:
            try:
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                    temp_path = tmp_file.name

                result = subprocess.run(['convert', file_path, '-resize', scale, '-quality', '70', temp_path],
                                      capture_output=True, text=True, timeout=COMPRESSION_TIMEOUT)

                if result.returncode == 0 and os.path.exists(temp_path):
                    with open(temp_path, 'rb') as f:
                        compressed_data = f.read()
                    os.unlink(temp_path)

                    if len(compressed_data) <= max_size:
                        print(f"Scaled to {scale} and compressed: {len(compressed_data):,} bytes", file=sys.stderr)
                        return compressed_data
                else:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)

            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                continue

        print("Warning: Could not compress image below size limit", file=sys.stderr)
        return None

    except Exception as e:
        print(f"Error during image compression: {e}", file=sys.stderr)
        return None

def extract_embedded_images(file_path, all_pages=False):
    """Try to extract embedded images from PDF using pdfimages (faster than conversion)"""
    import tempfile

    try:
        # Try to find pdfimages in common locations
        pdfimages_paths = ['/opt/homebrew/bin/pdfimages', '/usr/bin/pdfimages', '/usr/local/bin/pdfimages']
        pdfimages_cmd = None
        for path in pdfimages_paths:
            if os.path.exists(path):
                pdfimages_cmd = path
                break

        if not pdfimages_cmd:
            # Try to find it in PATH
            try:
                result = subprocess.run(['which', 'pdfimages'], capture_output=True, text=True, check=True)
                pdfimages_cmd = result.stdout.strip()
            except subprocess.CalledProcessError:
                print("pdfimages not found, will use conversion fallback", file=sys.stderr)
                return None

        # Create temporary directory for extracted images
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_prefix = os.path.join(temp_dir, 'extracted')

            # Extract images (with timeout)
            print("Attempting to extract embedded images...", file=sys.stderr)
            # Extract only first page by default
            pdfimages_args = [pdfimages_cmd, '-j', '-p']
            if not all_pages:
                pdfimages_args.extend(['-f', '1', '-l', '1'])  # First page only
            pdfimages_args.extend([file_path, temp_prefix])

            result = subprocess.run(pdfimages_args, capture_output=True, text=True, timeout=15)

            if result.returncode == 0:
                # Look for extracted images
                import glob
                extracted_files = glob.glob(temp_prefix + '*')

                if extracted_files:
                    # Sort to get files in page order
                    extracted_files.sort()

                    # Helper function to convert and process a single image file
                    def process_extracted_image(img_file):
                        _, ext = os.path.splitext(img_file)
                        ext_lower = ext[1:].lower() if ext else ""

                        # Convert unsupported formats (pbm, ppm, pgm) to PNG
                        if ext_lower in ['pbm', 'ppm', 'pgm']:
                            try:
                                from PIL import Image, ImageOps
                                png_file = img_file + '.png'
                                img = Image.open(img_file)
                                # Convert 1-bit images to 8-bit grayscale for better compatibility
                                if img.mode in ('1', 'L'):
                                    img = img.convert('L')
                                elif img.mode not in ('RGB', 'RGBA'):
                                    img = img.convert('RGB')

                                # Check if image might be inverted (mostly black background)
                                if img.mode == 'L':
                                    pixels = list(img.getdata())
                                    avg_brightness = sum(pixels) / len(pixels)
                                    # If image is very dark (avg < 50), it might be inverted
                                    if avg_brightness < 50:
                                        img = ImageOps.invert(img)

                                img.save(png_file, 'PNG', optimize=True)
                                img_file = png_file
                                mime_type = "image/png"
                            except ImportError:
                                # Fall back to ImageMagick convert
                                png_file = img_file + '.png'
                                result = subprocess.run(['convert', img_file, png_file],
                                                      capture_output=True, text=True, timeout=15, check=True)
                                if os.path.exists(png_file):
                                    img_file = png_file
                                    mime_type = "image/png"
                            except Exception as e:
                                print(f"Warning: Error converting {ext_lower.upper()}: {e}", file=sys.stderr)
                                mime_type = "image/png"  # Try PNG mime type anyway
                        else:
                            mime_type = f"image/{ext_lower}" if ext_lower else "image/jpeg"

                        return process_image_file(img_file, mime_type)

                    if all_pages and len(extracted_files) > 1:
                        # Process multiple images
                        print(f"Found {len(extracted_files)} embedded image(s), processing all pages", file=sys.stderr)
                        images = []
                        for img_file in extracted_files:
                            images.append(process_extracted_image(img_file))
                        return {"type": "multi_image", "images": images}
                    else:
                        # Process only first image
                        image_file = extracted_files[0]
                        print(f"Found {len(extracted_files)} embedded image(s), using first page: {os.path.basename(image_file)}", file=sys.stderr)
                        return process_extracted_image(image_file)
                else:
                    print("No embedded images extracted", file=sys.stderr)
                    return None
            else:
                print(f"pdfimages failed: {result.stderr}", file=sys.stderr)
                return None

    except subprocess.TimeoutExpired:
        print("Image extraction timed out", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error extracting embedded images: {e}", file=sys.stderr)
        return None

def convert_pdf_to_images(file_path, max_pages=5):
    """Convert multiple PDF pages to images and return combined content"""

    try:
        # Create temporary file for the images
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
            temp_image_path = tmp_file.name

        # Convert multiple pages of PDF to PNG (limit to max_pages to avoid huge documents)
        # Try to find pdftoppm in common locations
        pdftoppm_paths = ['/opt/homebrew/bin/pdftoppm', '/usr/bin/pdftoppm', '/usr/local/bin/pdftoppm']
        pdftoppm_cmd = None
        for path in pdftoppm_paths:
            if os.path.exists(path):
                pdftoppm_cmd = path
                break

        if not pdftoppm_cmd:
            # Try to find it in PATH
            try:
                result = subprocess.run(['which', 'pdftoppm'], capture_output=True, text=True, check=True)
                pdftoppm_cmd = result.stdout.strip()
            except subprocess.CalledProcessError:
                raise Exception("pdftoppm not found. Please install poppler-utils.")

        # Use lower DPI (100 instead of default 300) to reduce processing time and file size
        # Add short timeout to prevent hanging on problematic PDFs
        pdftoppm_args = [pdftoppm_cmd, '-png', '-r', '100', '-f', '1']
        if max_pages is not None:
            pdftoppm_args.extend(['-l', str(max_pages)])
            print(f"Converting PDF to PNG at 100 DPI (max {max_pages} pages)...", file=sys.stderr)
        else:
            print(f"Converting PDF to PNG at 100 DPI (all pages)...", file=sys.stderr)
        pdftoppm_args.extend([file_path, temp_image_path[:-4]])

        result = subprocess.run(pdftoppm_args, capture_output=True, text=True, check=True, timeout=60)

        # Collect all generated images
        print(f"PDF conversion completed, collecting generated images...", file=sys.stderr)
        image_content = []
        page_num = 1

        while True:
            actual_image_path = temp_image_path[:-4] + f'-{page_num}.png'
            print(f"Looking for image: {actual_image_path}", file=sys.stderr)
            if not os.path.exists(actual_image_path):
                print(f"No more images found, stopping at page {page_num}", file=sys.stderr)
                break

            # Read the generated image and check size
            with open(actual_image_path, 'rb') as f:
                file_data = f.read()

            # Hard limit: 10MB base64 = ~7.5MB raw file
            max_raw_size = 7_500_000  # ~7.5MB raw = ~10MB base64

            if len(file_data) > max_raw_size:
                print(f"Image too large ({len(file_data):,} bytes), compressing...", file=sys.stderr)
                # Try to compress using pngquant if available, otherwise reduce DPI further
                try:
                    # Create a compressed version
                    compressed_path = actual_image_path.replace('.png', '_compressed.png')

                    # Try pngquant first (best compression for text)
                    pngquant_result = subprocess.run(['pngquant', '--force', '--output', compressed_path, actual_image_path],
                                                   capture_output=True)

                    if pngquant_result.returncode == 0 and os.path.exists(compressed_path):
                        # Use compressed version if it's smaller
                        with open(compressed_path, 'rb') as f:
                            compressed_data = f.read()
                        if len(compressed_data) < len(file_data):
                            file_data = compressed_data
                            print(f"Compressed to {len(file_data):,} bytes", file=sys.stderr)
                        os.unlink(compressed_path)
                    else:
                        # Fallback: try progressively lower DPI until we get under the limit
                        for dpi in [100, 75, 50]:
                            print(f"Pngquant not available, trying DPI {dpi}...", file=sys.stderr)
                            low_dpi_path = actual_image_path.replace('.png', f'_dpi{dpi}.png')
                            try:
                                subprocess.run([pdftoppm_cmd, '-png', '-r', str(dpi), '-f', str(page_num), '-l', str(page_num),
                                              file_path, low_dpi_path[:-4]],
                                             capture_output=True, text=True, check=True, timeout=30)

                                low_dpi_actual = low_dpi_path[:-4] + f'-{page_num}.png'
                                if os.path.exists(low_dpi_actual):
                                    with open(low_dpi_actual, 'rb') as f:
                                        test_data = f.read()
                                    os.unlink(low_dpi_actual)
                                    print(f"DPI {dpi} version: {len(test_data):,} bytes", file=sys.stderr)
                                    if len(test_data) <= max_raw_size:
                                        file_data = test_data
                                        break
                                    elif dpi == 50:
                                        # This is our last attempt
                                        file_data = test_data
                            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                                continue

                except (subprocess.CalledProcessError, FileNotFoundError):
                    # If compression fails, we still need to check if it's under the limit
                    print("Warning: Could not compress image", file=sys.stderr)

            # Final hard check - fail if still too large
            if len(file_data) > max_raw_size:
                print(f"Error: Image still too large after compression ({len(file_data):,} bytes raw, would be {int(len(file_data) * 1.33):,} bytes base64)", file=sys.stderr)
                print(f"Maximum allowed: {max_raw_size:,} bytes raw (10MB base64 limit)", file=sys.stderr)
                sys.exit(1)

            base64_data = base64.b64encode(file_data).decode('utf-8')

            # Double check base64 size
            if len(base64_data) > 10_000_000:  # 10MB
                print(f"Error: Base64 image size ({len(base64_data):,} bytes) exceeds 10MB limit", file=sys.stderr)
                sys.exit(1)

            image_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{base64_data}",
                    "detail": "high"
                }
            })

            # Clean up temporary file
            os.unlink(actual_image_path)
            page_num += 1

        if not image_content:
            raise Exception("No images were generated from PDF")

        print(f"Converted {len(image_content)} pages to images for analysis", file=sys.stderr)

        # Return first image for single image processing, or combine for multi-page
        if len(image_content) == 1:
            return image_content[0]
        else:
            # For multiple pages, we need to handle this in the API call
            return {
                "type": "multi_image",
                "images": image_content
            }

    except subprocess.TimeoutExpired:
        print(f"Error: PDF conversion timed out. The PDF may be corrupted or extremely complex.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Error converting PDF to images: {e}", file=sys.stderr)
        if e.stderr:
            print(f"Error details: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error during PDF conversion: {e}", file=sys.stderr)
        sys.exit(1)

def read_file_content(file_path, all_pages=False):
    """Read file content and return appropriate format for Grok API"""
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' not found", file=sys.stderr)
        sys.exit(1)

    mime_type, _ = mimetypes.guess_type(file_path)
    file_ext = os.path.splitext(file_path)[1].lower()

    try:
        # Handle PDFs with text extraction, fallback to image
        if file_ext == '.pdf':
            try:
                # First try text extraction
                # Try to find pdftotext in common locations
                pdftotext_paths = ['/opt/homebrew/bin/pdftotext', '/usr/bin/pdftotext', '/usr/local/bin/pdftotext']
                pdftotext_cmd = None
                for path in pdftotext_paths:
                    if os.path.exists(path):
                        pdftotext_cmd = path
                        break

                if not pdftotext_cmd:
                    # Try to find it in PATH
                    try:
                        which_result = subprocess.run(['which', 'pdftotext'], capture_output=True, text=True, check=True)
                        pdftotext_cmd = which_result.stdout.strip()
                    except subprocess.CalledProcessError:
                        raise Exception("pdftotext not found. Please install poppler-utils.")

                result = subprocess.run([pdftotext_cmd, file_path, '-'],
                                      capture_output=True, text=True, check=True)
                text_content = result.stdout.strip()

                # Check if meaningful text was extracted (more than just whitespace/control chars)
                meaningful_text = ''.join(c for c in text_content if c.isprintable() and not c.isspace())

                if len(meaningful_text) < 10:  # Less than 10 printable characters suggests scanned PDF
                    print(f"PDF appears to be scanned (minimal text extracted: {len(meaningful_text)} chars). Trying image extraction first...", file=sys.stderr)
                    # Try extracting embedded images first (faster for PDFs with embedded images)
                    extracted_image = extract_embedded_images(file_path, all_pages=all_pages)
                    if extracted_image:
                        return extracted_image
                    print(f"No embedded images found. Converting to images for vision analysis...", file=sys.stderr)
                    max_pages = None if all_pages else 1
                    return convert_pdf_to_images(file_path, max_pages=max_pages)
                else:
                    return {"type": "text", "content": text_content}

            except subprocess.CalledProcessError as e:
                print(f"Text extraction failed: {e}. Trying image extraction first, then conversion...", file=sys.stderr)
                # Try extracting embedded images first (faster for PDFs with embedded images)
                extracted_image = extract_embedded_images(file_path, all_pages=all_pages)
                if extracted_image:
                    return extracted_image
                max_pages = None if all_pages else 1
                return convert_pdf_to_images(file_path, max_pages=max_pages)

        # Handle image files
        elif file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif']:
            return process_image_file(file_path, mime_type)

        # For other files, try to read as text first
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                return {"type": "text", "content": content}
        except UnicodeDecodeError:
            # If text reading fails, treat as binary (images)
            return process_image_file(file_path, mime_type)
    except Exception as e:
        print(f"Error reading file '{file_path}': {e}", file=sys.stderr)
        sys.exit(1)

def load_env_file():
    """Load environment variables from ~/.env file"""
    env_file = os.path.expanduser("~/.env")
    if os.path.exists(env_file):
        try:
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        # Handle both "export KEY=value" and "KEY=value" formats
                        if line.startswith('export '):
                            line = line[7:]  # Remove 'export ' prefix

                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"\'')  # Remove quotes
                        if key and not os.getenv(key):  # Only set if not already in environment
                            os.environ[key] = value
        except Exception as e:
            print(f"Warning: Could not read ~/.env file: {e}", file=sys.stderr)

def call_grok_api(prompt, model="grok-4-fast-reasoning", file_path=None, all_pages=False, auto_vision=True):
    api_key = os.getenv("GROK_API_KEY")
    if not api_key:
        # Try loading from ~/.env file
        load_env_file()
        api_key = os.getenv("GROK_API_KEY")

    if not api_key:
        print("Error: GROK_API_KEY not found in environment or ~/.env file", file=sys.stderr)
        sys.exit(1)

    url = "https://api.x.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # Build message content
    if file_path:
        file_content = read_file_content(file_path, all_pages=all_pages)
        if file_content["type"] == "text":
            # For text files, append to the prompt
            full_prompt = f"{prompt}\n\nFile content:\n{file_content['content']}"
            data = {
                "messages": [
                    {"role": "user", "content": full_prompt}
                ],
                "model": model,
                "stream": False
            }
        else:
            # For binary files (images), use multimodal format with vision model
            if auto_vision and model == "grok-4-fast-reasoning":
                print("Switching to vision model for image analysis...", file=sys.stderr)
                model = "grok-2-vision-1212"

            # Handle multi-image content (from multi-page PDFs)
            if file_content.get("type") == "multi_image":
                content = [{"type": "text", "text": prompt}]
                content.extend(file_content["images"])
            else:
                content = [
                    {"type": "text", "text": prompt},
                    file_content
                ]

            data = {
                "messages": [
                    {
                        "role": "user",
                        "content": content
                    }
                ],
                "model": model,
                "stream": False
            }
    else:
        data = {
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "model": model,
            "stream": False
        }

    try:
        json_data = json.dumps(data).encode('utf-8')

        req = urllib.request.Request(url, data=json_data, headers=headers, method='POST')

        with urllib.request.urlopen(req) as response:
            response_data = response.read().decode('utf-8')
            result = json.loads(response_data)
            return result["choices"][0]["message"]["content"]

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else ''
        print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        if error_body:
            print(f"Response body: {error_body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error making API request: {e}", file=sys.stderr)
        sys.exit(1)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"Error parsing API response: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Call Grok API with a prompt")
    parser.add_argument("prompt", help="The input prompt to send to Grok")
    parser.add_argument("--model", default="grok-4-fast-reasoning",
                       help="The model to use (default: grok-4-fast-reasoning)")
    parser.add_argument("--file", help="Optional file to include (PDFs auto-fallback text→vision, text files use text model, images use vision model)")
    parser.add_argument("--all-pages", action="store_true",
                       help="Process all pages of PDF (default: first page only)")

    args = parser.parse_args()

    result = call_grok_api(args.prompt, args.model, args.file, args.all_pages)
    print(result)

if __name__ == "__main__":
    main()
