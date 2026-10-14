# Architecture

Read this before editing `invoice_renamer.py`, `llm_client.py`, or `document_families.py`. Filename rules that must not regress live in `AGENTS.md`. Install, commands, and API keys live in `README.md`.

## Core modules

### invoice_renamer.py

- Main entry point and orchestration.
- Extracts document metadata through `llm_client` (in-process, with a subprocess fallback if the import fails).
- Applies the naming grammar and does the file operations.
- Handles dry-run, moves, and conflict resolution.
- Logs with daily rotation to the temp directory.

### document_families.py

- Labeled-line parsers for text PDFs. Each family returns facts that overwrite the model.
- Families: portal invoice, insurance, receipt, brokerage and bank statement date, account number, utility premise, vet patients.
- A new issuer is a parser plus a redacted text dump in `tests/fixtures/naming/`, not another prompt paragraph.
- Photos and scans have no `pdftotext` output, so these families no-op and the vision model still names them.

### llm_client.py

- LLM API client via LiteLLM (Claude, GPT, Grok, Gemini, and the other LiteLLM providers).
- Pipeline: PDF to text (`pdftotext`) or image conversion, then compression, then the API call.
- File types: PDFs, images (JPG, PNG, GIF, BMP, WebP, TIFF), and text.
- Image compression stays under the API size limits (10MB base64).
- Constants at the top: `MAX_RAW_SIZE`, `MAX_BASE64_SIZE`, `DEFAULT_MAX_PAGES` (2), timeouts, `DEFAULT_MODEL`.
- Exceptions: `LLMClientError`, `FileProcessingError`, `APIError`.
- Vision models are selected for images. An in-process file-content cache lets date and USDF retries reuse extraction.
- API retries: `API_MAX_RETRIES` (3) with exponential backoff from `API_RETRY_BASE_DELAY` (1s, 2s, 4s). `NON_RETRYABLE_API_ERRORS` (auth, bad request, not found) fail at once. The final error is chained to `SystemExit` so `invoice_renamer` logs it.

## Patterns

1. **In-process LLM client.** `invoice_renamer` imports and calls `llm_client` in-process. The subprocess fallback remains if that import fails. `llm_client` is still runnable standalone.

2. **PDF pipeline.** `pdftotext` on pages 1–2 for text PDFs (`--all-pages` for the full document). Fallback to `pdfimages` on pages 1–2, then to JPEG page renders via `pdftoppm` on pages 1–2. Compress with ImageMagick or the in-process helpers when needed.

3. **File type detection.** `mimetypes` plus the extension.

4. **Size management.** PIL optimization, then ImageMagick quality reduction, until the payload fits the API limit.

5. **Naming.** Labeled lines win, the model fills the rest, and Python owns the grammar. Topic policy is `_select_display_topic`. Premise labels are dropped for banks, tolls, and transit in `_should_drop_premise_qualifier`. The invariants are listed in `AGENTS.md`.

## API configuration

Keys and the model come from the environment or `~/.env`:

- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `GROK_API_KEY`, plus other LiteLLM provider keys.
- `LLM_MODEL` defaults to the fast non-reasoning `xai/grok-4.20-0309-non-reasoning`. Any LiteLLM model string works. The provider's current model list is the reference.
- Text models for text PDFs and text files. Vision models for images and scanned PDFs.
- Legacy Grok names (`grok-4-1-fast-*`, `grok-beta`) are mapped to current models in `llm_client.py`.

Provider list: <https://docs.litellm.ai/docs/providers>.

## External dependencies

- ImageMagick (compression and conversion)
- Poppler (`pdftotext`, `pdftoppm`, `pdfimages`)
- pngquant (optional)
- Python: litellm, titlecase, and the dev group pytest, pytest-mock, pytest-cov, pytest-xdist

## Tests

Pytest collects `tests/`. Golden naming fixtures are `tests/fixtures/naming/`. Shared fixtures (`sample_jpeg_data`, `temp_file_cleanup`, `mock_env_file`) live in `tests/conftest.py`.

## Install path

System Python `/usr/local/bin/python3` installs the command at `/Library/Frameworks/Python.framework/Versions/3.11/bin/invoice-renamer`, symlinked from `/usr/local/bin/invoice-renamer`. Shortcuts invoke `invoice-renamer` with the repeated file path. That symlink is what puts the command on `PATH`.
