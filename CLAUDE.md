# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OSX File Renamer is a command-line tool that uses AI (LLM APIs via LiteLLM) to automatically rename invoice and document files based on their content. It analyzes documents to extract business names, document types, dates, and other metadata, then applies consistent naming conventions.

**Data Privacy Note**: This tool sends file contents to your chosen LLM provider for analysis. Supported providers include Anthropic (Claude), OpenAI (GPT), xAI (Grok), Google (Gemini), and 100+ others via LiteLLM. You choose your preferred provider by setting the appropriate API key.

## Development Environment

**Python Version**: 3.11+ required

The tool can be used in two ways:

1. **Installed command** (recommended for users): `make install` creates the `invoice-renamer` command available system-wide
2. **Direct execution** (for development): Run `python3 invoice_renamer.py` directly from the repo

Install dependencies:

```bash
make install      # Install as command (for end users and OSX shortcuts)
# or
make install-dev  # Install in editable mode with dev dependencies (for developers)
```

## Common Commands

### Running the Application

**Production Use (Installed Command):**

```bash
# One-time setup - installs to system Python and creates /usr/local/bin/invoice-renamer symlink
make install
sudo ln -sf "/Library/Frameworks/Python.framework/Versions/3.11/bin/invoice-renamer" /usr/local/bin/invoice-renamer

# Run from anywhere (including OSX shortcuts)
invoice-renamer ~/Downloads/file.pdf
invoice-renamer ~/Downloads/file.pdf --dry-run
invoice-renamer ~/Downloads/file.pdf --move-to /target/dir
```

**Development/Testing (Direct Execution):**

From the repo directory for quick testing without installation:

```bash
cd ~/Documents/Code/osx-file-renamer
python3 invoice_renamer.py path/to/file.pdf --dry-run
```

### Testing

```bash
# Run all tests
make test
# or: pytest -v

# Run specific test file
pytest tests/test_llm_main.py

# Run with coverage
make test-cov

# Run in parallel (faster)
make test-fast
```

### Linting

```bash
# Check code style
make lint
# or: flake8

# Configuration in .flake8:
# - Max line length: 180
# - Ignores: E201, E202, E402, E722
```

## Architecture

### Core Modules

#### invoice_renamer.py

- Main entry point and orchestration logic
- Extracts document metadata via llm_client.py subprocess calls
- Applies naming conventions and file operations
- Handles dry-run mode, file moves, and conflict resolution
- Logging with automatic rotation (logs to temp directory)

#### llm_client.py

- LLM API client for document analysis (supports Claude, GPT-4, Grok, Gemini, and 100+ models via LiteLLM)
- File processing pipeline: PDF → text (pdftotext) or image conversion → compression → API call
- Supports multiple file types: PDFs, images (JPG, PNG, GIF, BMP, WebP, TIFF), text
- Image compression to meet API size limits (10MB base64)
- Constants defined at top: MAX_RAW_SIZE, MAX_BASE64_SIZE, DEFAULT_MAX_PAGES (2), timeouts, DEFAULT_MODEL
- Custom exceptions: LLMClientError, FileProcessingError, APIError
- Automatically selects vision models when processing images
- In-process file-content cache so date/USDF retries reuse extraction work

### Key Architecture Patterns

1. **In-process LLM client**: invoice_renamer imports and calls llm_client in-process (avoids Python/LiteLLM cold start). Subprocess fallback remains if import fails. llm_client is still runnable standalone.

2. **PDF Processing Pipeline**:
   - Text extraction via pdftotext on pages 1–2 by default (fast path for text-based PDFs; `--all-pages` for full doc)
   - Fallback to image extraction via pdfimages (pages 1–2 by default)
   - Fallback to full PDF→JPEG conversion via pdftoppm (pages 1–2 by default; covers cover+content)
   - Image compression using ImageMagick / in-process helpers if needed

3. **File Type Detection**: Uses mimetypes module + extension checking to determine processing path

4. **Size Management**: Multi-stage compression pipeline (PIL optimization → ImageMagick quality reduction) to meet API limits

5. **Naming Convention**:

   ```
   Vendor [Account-Type] Topic [AccountId] [- Patient/Animal] [Invoice#] Date
   ```

   Short vendor names preferred (Amex, BofA, Chase). Account id is last-4 or short alphanumeric (low PII).
   Examples: "Amex CC Statement 1000 20240115.pdf", "Dr Smith Invoice ACS12B4 20240115.pdf"

### API Configuration

The tool uses LiteLLM for flexible LLM provider support. Configuration via environment variables in `~/.env` file:

**API Keys** (provider-specific, choose one or more):

- `ANTHROPIC_API_KEY` - For Claude models (Anthropic)
- `OPENAI_API_KEY` - For GPT models (OpenAI)
- `GOOGLE_API_KEY` - For Gemini models (Google)
- `GROK_API_KEY` - For Grok models (xAI)
- Other provider keys as supported by LiteLLM (100+ providers)

**Model Selection**:

- `LLM_MODEL` - Default model to use (optional, defaults to fast non-reasoning `xai/grok-4.20-0309-non-reasoning`)
- Examples: `claude-3-5-sonnet-20241022`, `gpt-4`, `gemini-pro`, `xai/grok-4.20-0309-non-reasoning`

**Model Auto-Selection**:

- Text models used for text-based PDFs and text files
- Vision models automatically selected for images and scanned PDFs
- Legacy model names automatically converted to LiteLLM format for backward compatibility

**Supported Model Families**:

- Claude: `claude-3-5-sonnet-20241022`, `claude-3-opus-20240229` (Anthropic)
- GPT: `gpt-4`, `gpt-4-turbo`, `gpt-4-vision-preview` (OpenAI)
- Gemini: `gemini-pro`, `gemini-pro-vision` (Google)
- Grok: `grok-4-1-fast-reasoning`, `grok-4-1-fast-non-reasoning`, `grok-beta` (xAI)
- 100+ more via LiteLLM (see <https://docs.litellm.ai/docs/providers>)

### External Dependencies

System tools required:

- ImageMagick (image compression/conversion)
- Poppler tools (pdftotext, pdftoppm, pdfimages)
- pngquant (optional, better compression)

Python packages: litellm, titlecase, pytest, pytest-mock, pytest-cov, pytest-xdist

### Future Optimizations (speed / cost)

If renames still feel slow or vision API cost becomes an issue, consider these in order of likely ROI. Prefer measuring with path/timing logs before adding dependencies.

**Already done (baseline):**

- In-process `llm_client` (no Python/LiteLLM cold start per call)
- In-process file-content cache (date/USDF retries reuse extraction)
- Default pages 1–2 (cover + content) for text and vision
- Fast non-reasoning default model; vision `detail: low`; JPEG page renders
- Title/vendor/type dedupe for shorter filenames

**Next candidates if still slow or expensive:**

1. **Path + timing logs** — Log which path ran (`pdftotext` / `pdfimages` / `pdftoppm`) and wall times for extract vs API. Makes real-world bottlenecks obvious before adding tools.

2. **Local OCR (Tesseract) as optional scan fast path** — Not used today; vision LLM “reads” page images instead.
   - *When it helps:* clean upright B&W scans / phone docs with good contrast → rasterize pages 1–2 → `tesseract` → if text quality high, use **text LLM** (cheap/fast) and skip vision.
   - *When it hurts:* skewed photos, glare, low contrast, heavy graphics — vision models usually win.
   - *Suggested design:* optional `tesseract` dependency; confidence/length gate; fall back to vision on weak OCR. Do **not** make Tesseract required for install.
   - *Does not replace:* page selection (pages 1–2 / adaptive page 2) — OCR the right pages first.

3. **Skip or demote `pdfimages`** — Often returns logos/icons, not full pages, wasting a vision call. Prefer `pdftoppm` page renders for fidelity; keep `pdfimages` only when a single large embedded image looks page-sized.

4. **Cheaper / faster models** — Separate `LLM_MODEL` (text) vs `LLM_VISION_MODEL` env vars; allow a tiny local or budget cloud model for structured JSON when quality is good enough. Keep reasoning models opt-in for hard cases.

5. **Adaptive extra pages** — If Vendor or date missing after pages 1–2, fetch page 3 only (generalize USDF page-2 retry) instead of `--all-pages`.

6. **Raise text-quality gate / hybrid path** — Thin embedded text layers (bad scanner OCR) currently take the text path with `MIN_MEANINGFUL_TEXT = 10`. Raise the threshold or send **text + page-1 image** when text looks sparse/garbage so names stay accurate without always using full vision.

7. **Batch / daemon mode** — For folder renames, keep one long-lived process so LiteLLM stays warm across files (bigger win than per-file micro-opts).

8. **Shared poppler path finder** — Duplicated binary discovery in `invoice_renamer` and `llm_client`; small cleanup only.

**Naming constraints to preserve when optimizing:**

- Short filenames: Amex not “American Express”; CC not “Credit Card”
- Low PII: last-4 or short alphanumeric account ids only
- Priority fields: Vendor → Topic → AccountId → Date
- Lowercase extensions always

## Project Rules

1. **Python Version**: Requires Python 3.11+
2. **Quality Gates**: Run `make lint` at end of task - fix all errors before completion
3. **Testing**: Run `make test` at end of task - fix all failures before completion
4. **Test Quality**: Never skip tests; no test failures acceptable
5. **Import Style**: Never import within functions - all imports at top of file
6. **Clean Imports**: No unused imports; nothing between import statements (no blank lines or code)
7. **Constants**: Use defined constants (e.g., timeouts) instead of hardcoded values

## Testing

Test files in `tests/` directory:

- `test_llm_main.py` - main llm_client.py functionality
- `test_llm_file_processing.py` - file processing pipeline
- `test_llm_api_interaction.py` - API calls and LiteLLM integration
- `test_llm_error_handling.py` - error scenarios
- `test_invoice_renamer.py` - invoice_renamer.py functionality
- `conftest.py` - shared fixtures (mock env, jpeg data, temp file cleanup)

Key fixtures: `sample_jpeg_data`, `temp_file_cleanup`, `mock_env_file`

## File Locations

- Logs: `/tmp/invoice_renamer.log` and `/tmp/invoice_debug.log` on Unix-like systems (falls back to platform temp on Windows)
- API key: Environment variable or `~/.env` file in home directory
- Installation: Uses system Python at `/usr/local/bin/python3` to install, creates command at `/Library/Frameworks/Python.framework/Versions/3.11/bin/invoice-renamer`, symlinked from `/usr/local/bin/invoice-renamer`
- OSX Shortcuts: Invoke as `invoice-renamer "Repeat Item (File Path)"` - the symlink in `/usr/local/bin` makes the command available in PATH
- If CLAUDE.md has changed, include it in the commit when code changes are committed
- when updating this project you should also bump the version in pyproject.toml
