# Future optimizations (speed / cost)

Read this only when a rename feels slow or vision API cost is the task. Measure with path and timing logs before adding a dependency. Naming invariants that these changes must preserve are in `AGENTS.md`.

## Already done

- In-process `llm_client` (no Python/LiteLLM cold start per call).
- In-process file-content cache (date and USDF retries reuse extraction).
- Default pages 1–2 (cover plus content) for text and vision.
- Fast non-reasoning default model. Vision `detail: high` (override `LLM_IMAGE_DETAIL=low` for cheap bulk). JPEG page renders.
- Title, vendor, and type dedupe for shorter filenames.
- Slim fact-only extraction prompt. Naming grammar is owned by code.
- xAI prompt cache: extraction rules stay a byte prefix, the filename hint is last, and every xAI call sends the same `x-grok-conv-id`.
- Vision `detail: high` by default, because phone photos of stamped job forms need it.
- Image inputs: extract from the original photo, and convert to PDF only for the renamed output.

## Next candidates

1. **Path and timing logs.** Log which path ran (`pdftotext`, `pdfimages`, or `pdftoppm`) and the wall time for extract versus the API call.

2. **Optional local OCR.** Tesseract is not used today. The vision model reads page images.
   It helps on clean upright black-and-white scans and phone docs with good contrast: rasterize pages 1–2, run `tesseract`, and if the text quality is high, use the text model and skip vision.
   It hurts on skewed photos, glare, low contrast, and heavy graphics.
   Keep it optional, gate it on confidence and length, and fall back to vision. Do not make Tesseract required for install.
   OCR the same pages the pipeline already selects.

3. **Demote `pdfimages`.** It often returns logos and icons rather than full pages, which wastes a vision call. Prefer `pdftoppm` page renders. Keep `pdfimages` only when a single large embedded image looks page-sized.

4. **Cheaper models.** Separate `LLM_MODEL` (text) from `LLM_VISION_MODEL`. A small local or budget cloud model can emit the structured JSON when quality is good enough. Reasoning models stay opt-in.

5. **Adaptive extra pages.** If vendor or date is missing after pages 1–2, fetch page 3 only. That generalizes the USDF page-2 retry. It is not a reason to default to `--all-pages`.

6. **Text-quality gate.** Thin embedded text layers currently take the text path at `MIN_MEANINGFUL_TEXT = 10`. Raise that threshold, or send the text plus the page-1 image, when the text looks sparse or garbled.

7. **Batch or daemon mode.** For folder renames, one long-lived process keeps LiteLLM warm across files.

8. **Shared Poppler path finder.** Binary discovery is duplicated in `invoice_renamer` and `llm_client`.
