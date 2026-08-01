#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess
import json
import re
from datetime import datetime
import logging
import hashlib
import shutil
import glob
import tempfile
import PIL.Image
try:
    from titlecase import titlecase  # type: ignore[import-untyped]
except ImportError:
    # Fallback if titlecase not available
    def titlecase(text):
        return text.title()
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HAS_PILLOW_HEIF = True
except ImportError:
    HAS_PILLOW_HEIF = False


PDF_CONVERSION_TIMEOUT = 60
CONVERTIBLE_IMAGE_EXTENSIONS = ['.heic', '.jpg', '.jpeg', '.png', '.webp', '.tiff', '.tif', '.bmp', '.gif']
CONVERTIBLE_DOC_EXTENSIONS = ['.docx']
CONVERTIBLE_EXTENSIONS = CONVERTIBLE_IMAGE_EXTENSIONS + CONVERTIBLE_DOC_EXTENSIONS

# ---------------------------------------------------------------------------
# Naming contract
#
# LLM extracts FACTS only. Python owns the filename grammar (see
# _select_display_topic / _build_filename_parts). Do not teach assembly rules
# in the prompt beyond "return these fields."
#
# Grammar:
#   Vendor [AccountType] Topic [AccountId] [- Party] [RefId] Date.ext
#
# Topic is produced from (document_type, document_title/qualifier):
#   - no qualifier → document_type
#   - Confirmation/Certificate/Permit + qualifier → "{qualifier} {type}"
#   - otherwise qualifier replaces type (after stripping redundant type/vendor words)
#
# document_title JSON key = optional short QUALIFIER (premise, subtype, form name).
# ---------------------------------------------------------------------------

# Fact-extraction prompt — keep short; assembly policy lives in code.
INVOICE_EXTRACTION_PROMPT = """Extract facts from this document as JSON. Do NOT invent a filename — code builds it from these fields.
Priority facts: short Vendor, Type, short Account id, Date. Keep values SHORT and recognizable.

1. business_name — short brand, not legal entity (max ~3–4 words):
   Amex not American Express; BofA not Bank of America; Chase not JPMorgan Chase Bank N.A.
   Store cards → store name; co-brand when prominent (JetBlue); parent if more recognizable (Tesla).
   Government: IRS, SSA, Medicare, USPS, NJ DMV, township name. Else top-of-page short name.

2. document_type — REQUIRED, exactly ONE of:
   Invoice | Quote | Statement | Receipt | Confirmation | Notice | Letter | Report |
   Form | Contract | Policy | Certificate | Permit | Map | Itinerary | Test
   - Statement if "statement" is prominent (not Report)
   - Confirmation for trade/order/booking confirmations (not Receipt)
   - Receipt for proof of payment / "payment received"
   - Quote for estimates/proposals not yet requesting payment
   - Report only if the document explicitly says report

3. invoice_date — YYYY-MM-DD when visible (check content pages, not only cover).
   Receipts: transaction date. Invoices/statements: invoice/statement/bill date.
   Notices/forms: header date or tax/form year. Always extract if visible.

4. invoice_number — short doc ref only (Invoice #, Bill #, Case #, Permit #). null if none.
   Never full account/card numbers.

5. patient_animal_name — medical patient or vet pet name only; else null.

6. account_type — specific category when known, else null:
   Checking, Savings, Money Market, CD, IRA, Credit Card (or Platinum/Gold if labeled as tier),
   Annuity, VUL, Life Insurance, Brokerage, 401k.
   Multi-account overview (2+ different account numbers) → "Portfolio".
   null for generic "Account" / "Investment Account" only.

7. account_last_4 — last 4 digits or short alphanumeric id for a SINGLE account/card
   (also utility/telecom service accounts even when account_type is null).
   Portfolio or no account → null. Never full account numbers.

8. document_title — optional SHORT qualifier (not a full filename). Use when it adds meaning beyond type:
   - Confirmation subtype: Trade, Order, Booking, Reservation
   - Utility/telecom premise label only (not street address): "130 WEST ST BARN" → "Barn";
     "… **COGEN**" → "Cogen"; "Apt 2B" / Unit B / Garage → that short label
   - Non-routine subject: Tax Delinquent, W-2, Lease, EOB, Building Permit, Auto Policy
   - Multi-item summary: short synthesis (e.g. Auto Property Insurance)
   null when Vendor + type is enough (routine invoice, receipt, itinerary, plain bank/CC statement).
   Do not restate the type ("Invoice Document", "Travel Itinerary" → null). Max 5 words, title case.
   Do not repeat vendor words. Do not invent a premise label that is not on the document.

9. USDF dressage scorecards only (else all three null). Set document_type to "Test":
   - usdf_test_name: omit the word "Level" — e.g. "USDF Introductory A", "USDF Training 1",
     "USDF First 1", "USDF Prix St Georges"
   - usdf_rider_number: entry/competitor digits only (Entry No. / number before horse name)
   - usdf_rider_name: rider full name (not horse)

Return ONLY this JSON (null for anything missing):
{
  "business_name": "Short Vendor",
  "document_type": "Type",
  "document_title": "Qualifier or null",
  "invoice_date": "YYYY-MM-DD",
  "invoice_number": "Short Id or null",
  "patient_animal_name": "Name or null",
  "account_type": "Type or null",
  "account_last_4": "Last4 or null",
  "usdf_test_name": null,
  "usdf_rider_number": null,
  "usdf_rider_name": null
}"""

# Short-name abbreviations applied after extraction (case-insensitive whole-phrase match)
FILENAME_ABBREVIATIONS = [
    (re.compile(r'^American Express$', re.IGNORECASE), 'Amex'),
    (re.compile(r'^American Express National Bank$', re.IGNORECASE), 'Amex'),
    (re.compile(r'^Bank of America$', re.IGNORECASE), 'BofA'),
    (re.compile(r'^JPMorgan Chase(?: Bank)?(?:,? N\.?A\.?)?$', re.IGNORECASE), 'Chase'),
    (re.compile(r'^J\.?\s*P\.?\s*Morgan Chase(?: Bank)?(?:,? N\.?A\.?)?$', re.IGNORECASE), 'Chase'),
    (re.compile(r'^Wells Fargo(?: Bank)?$', re.IGNORECASE), 'Wells Fargo'),
    (re.compile(r'^Citibank(?: N\.?A\.?)?$', re.IGNORECASE), 'Citi'),
    (re.compile(r'^Credit Card$', re.IGNORECASE), 'CC'),
    (re.compile(r'^Social Security Administration$', re.IGNORECASE), 'SSA'),
    (re.compile(r'^Internal Revenue Service$', re.IGNORECASE), 'IRS'),
]
MAX_ACCOUNT_ID_LEN = 8  # longer ids look like full account numbers — trim to last 4

# Original filenames that are camera/scanner defaults or bare numbers carry no useful signal
GENERIC_FILENAME_PATTERNS = [
    r'^(img|image|photo|pic|scan|doc|document|file|untitled|screenshot|dsc|test|temp|tmp|sample|example|output)\s*\d*$',
    r'^\d+$',
]
# Noise tokens stripped from filename hints (not useful as topic words)
_FILENAME_NOISE_WORDS = frozenset({
    'file', 'pdf', 'jpg', 'jpeg', 'png', 'heic', 'download', 'downloads', 'copy', 'final',
    'new', 'img', 'image', 'photo', 'pic', 'scan', 'doc', 'document', 'untitled', 'screenshot',
    'dsc', 'edited', 'export', 'attachment', 'attachments', 'test', 'temp', 'tmp', 'sample',
    'example', 'output',
})
# Account/product words often present in names; not document topics by themselves
_FILENAME_ACCOUNT_WORDS = frozenset({
    'cc', 'credit', 'card', 'checking', 'savings', 'brokerage', 'margin', 'ira', 'roth',
    'portfolio', '401k', 'hsa', 'fsa', 'cash', 'money', 'market', 'cd',
})
# Words that name a document *kind* (or near-synonyms). Never promote these into document_title
# from a filename — they either restate document_type or conflict with content-based type
# (e.g. "Quest Billing" when the PDF is a payment Receipt → keep type Receipt, not title Billing).
# Confirmation subtypes (Trade, Order, Booking, Reservation) are intentionally NOT listed here.
_FILENAME_TYPE_SYNONYMS = frozenset({
    'billing', 'bill', 'bills', 'invoice', 'invoices', 'receipt', 'receipts', 'statement',
    'statements', 'notice', 'notices', 'letter', 'letters', 'report', 'reports', 'form',
    'forms', 'contract', 'contracts', 'policy', 'policies', 'certificate', 'certificates',
    'permit', 'permits', 'quote', 'quotes', 'estimate', 'estimates', 'itinerary', 'map',
    'maps', 'payment', 'payments', 'paid', 'remittance', 'remit', 'stub', 'summary',
    'document', 'documents', 'file', 'scan', 'copy',
})
# Filler words that don't add meaning if they are all that remains of a title
_GENERIC_TITLE_WORDS = frozenset({
    'travel', 'document', 'documents', 'general', 'official', 'the', 'a', 'an',
    'and', 'of', 'for', 'to', 'in', 'at', 'by', 'with', 'from', 'on',
})


def _split_filename_tokens(name):
    """Split camelCase / digit boundaries so glued names become readable words.

    Examples:
      TradeConfirmation07312026 → Trade Confirmation 07312026
      Amex_CC_Statement → Amex CC Statement
    """
    name = re.sub(r'[_\-.\+]+', ' ', name)
    # lower→Upper boundary (TradeConfirmation)
    name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
    # ACRONYM then Capitalized word (HTMLParser → HTML Parser)
    name = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', name)
    # letter↔digit boundaries (Confirmation0731, 2024Invoice)
    name = re.sub(r'([a-zA-Z])(\d)', r'\1 \2', name)
    name = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', name)
    return re.sub(r'\s+', ' ', name).strip()


def _strip_filename_date_tokens(name):
    """Remove leading/trailing date-like tokens commonly baked into downloads."""
    # Leading ISO / compact dates (Shortcuts, mail clients)
    name = re.sub(r'^\d{4}[-_]\d{2}[-_]\d{2}[_\-\s]*', '', name)
    name = re.sub(r'^\d{8}[_\-\s]*', '', name)
    # Trailing compact dates: MMDDYYYY, YYYYMMDD, MMDDYY, YYYYMMDD-ish 6–8 digits
    name = re.sub(r'[\s_\-]*\d{8}$', '', name)
    name = re.sub(r'[\s_\-]*\d{6}$', '', name)
    # Trailing ISO date
    name = re.sub(r'[\s_\-]*\d{4}[-_]\d{2}[-_]\d{2}$', '', name)
    return name.strip()


def _original_filename_hint(file_path):
    """Build a human-readable hint from the original filename, or None if it's not useful.

    Strips date prefixes/suffixes (often added by Shortcuts/automations), splits camelCase
    and digit boundaries, then filters out generic camera/scanner names.
    """
    name = os.path.splitext(os.path.basename(file_path))[0]
    name = _strip_filename_date_tokens(name)
    name = _split_filename_tokens(name)
    # Date tokens may reappear after camelCase/digit splits (e.g. TradeConfirmation07312026)
    name = _strip_filename_date_tokens(name)
    name = re.sub(r'\s+', ' ', name).strip()
    if not name or len(name) < 4:
        return None
    for pattern in GENERIC_FILENAME_PATTERNS:
        if re.match(pattern, name, re.IGNORECASE):
            return None
    return name


def _build_extraction_prompt(filename_hint=None):
    """Build the extraction prompt; optionally note the original filename as a weak signal."""
    if not filename_hint:
        return INVOICE_EXTRACTION_PROMPT
    hint_block = (
        f'The file\'s original name was "{filename_hint}". '
        'Use it as a weak signal for vendor, type, or document_title when consistent with content '
        '(e.g. "Trade Confirmation" → type Confirmation, document_title Trade). '
        'Content wins on conflict (page says payment received → Receipt even if named Billing). '
        'Do not invent a premise/location label from the filename alone.\n\n'
    )
    return hint_block + INVOICE_EXTRACTION_PROMPT


def _raw_qualifier(info):
    """Return the optional qualifier from model output (document_title, or alias qualifier)."""
    if not info:
        return None
    for key in ('document_title', 'qualifier'):
        val = info.get(key)
        if val is None:
            continue
        text = str(val).strip()
        if text and text.lower() != 'null':
            return text
    return None


def _topic_words_from_filename_hint(filename_hint, business_name=None, document_type=None):
    """Extract distinctive qualifier words from a filename hint.

    Drops vendor words, document-type words/synonyms, account labels, dates/numbers, and noise.
    Returns a title-cased string or None if nothing useful remains.
    """
    if not filename_hint:
        return None
    # Re-normalize in case a raw basename was passed
    words = _split_filename_tokens(_strip_filename_date_tokens(filename_hint)).split()
    if not words:
        return None

    drop = (
        set(_FILENAME_NOISE_WORDS)
        | set(_GENERIC_TITLE_WORDS)
        | set(_FILENAME_ACCOUNT_WORDS)
        | set(_FILENAME_TYPE_SYNONYMS)
    )
    if business_name:
        drop |= {w.lower() for w in str(business_name).split() if w}
    if document_type:
        drop |= {w.lower() for w in str(document_type).split() if w}

    kept = []
    for word in words:
        lower = word.lower()
        if lower in drop:
            continue
        if re.fullmatch(r'\d+', word):
            continue
        if re.fullmatch(r'\d{4}[-_]\d{2}[-_]\d{2}', word):
            continue
        # Skip tiny tokens (e.g. leftover "CC" after account-word filtering edge cases)
        if len(re.sub(r'[^a-zA-Z0-9]', '', word)) < 3:
            continue
        kept.append(word)

    if not kept:
        return None
    # Cap length; title-case for consistency with LLM titles
    topic = ' '.join(kept[:5])
    try:
        topic = titlecase(topic)
    except Exception:
        topic = topic.title()
    return topic if topic else None


def _apply_filename_hint_fallback(info, filename_hint):
    """Fill missing qualifier from the original filename when the LLM left it null.

    Safety net only — code assembly owns how the qualifier becomes the Topic segment.
    Never overwrites a model-provided document_title/qualifier.

    Does NOT promote type-synonym leftovers like "Billing" when the model already classified
    the file as Receipt — content wins over a wrong/outdated name.

    To avoid treating bare fixture/placeholder names (original.pdf, nodoc.pdf) as topics,
    require either:
      - the document type appears in the filename (Trade Confirmation → Confirmation), or
      - the hint is multi-word after normalization (Tax Delinquent, Order Confirmation)
    and then at least one distinctive topic word remains after stripping vendor/type/noise.
    """
    if not info or not filename_hint:
        return info
    if _raw_qualifier(info):
        return info

    hint_norm = _split_filename_tokens(_strip_filename_date_tokens(filename_hint))
    hint_words = [w for w in hint_norm.split() if w]
    if not hint_words:
        return info

    type_words = {w.lower() for w in str(info.get('document_type') or '').split() if w}
    hint_lower = {w.lower() for w in hint_words}
    has_type_signal = bool(type_words & hint_lower)
    is_multiword = len(hint_words) >= 2
    if not has_type_signal and not is_multiword:
        return info

    topic = _topic_words_from_filename_hint(
        filename_hint,
        business_name=info.get('business_name'),
        document_type=info.get('document_type'),
    )
    if topic:
        info['document_title'] = topic
        logging.getLogger(__name__).info(
            f"Filled document_title from filename hint: {topic!r} (hint={filename_hint!r})"
        )
    return info


def send_notification(title, message):
    """Send a macOS notification via osascript"""
    logger = logging.getLogger(__name__)
    try:
        safe_title = title.replace('"', '\\"')
        safe_message = message.replace('"', '\\"')
        subprocess.run(
            ['osascript', '-e', f'display notification "{safe_message}" with title "{safe_title}"'],
            capture_output=True, timeout=5
        )
        logger.info(f"Notification sent: {title} — {message}")
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning(f"Could not send notification: {e}")


# Focused date extraction prompt
DATE_EXTRACTION_PROMPT = """Look carefully at this document and find the date.
For receipts: Look for the transaction date/time near the top (may be in the header, labeled "Date", or near business info).
For invoices/statements: Look for "Invoice Date", "Statement Date", "Bill Date", etc.
For notices/letters: Look for the date at the top of the document.

Return ONLY the date in YYYY-MM-DD format. If you see a date like "11/3/25", interpret it as MM/DD/YY and convert to YYYY-MM-DD (e.g., "2025-11-03").
If no date is visible, return "NONE"."""


USDF_PAGE2_PROMPT = """This image is the front cover of a USDF/USEF dressage test booklet. Extract:
- Test name (e.g. "2023 USDF INTRODUCTORY LEVEL – TEST A") — abbreviate to omit "Level":
  "USDF Introductory A", "USDF Training 1", "USDF First 1", "USDF Second 2", "USDF Third 3"
  CRITICAL: Never include the word "Level" in the test name.
- Entry/competitor number — digits only (e.g. "16", "81", "28", "99").
  Look in these places:
  * A box or field labeled "Entry No." or "No."
  * The "Name and Number of Horse" field — the number appears BEFORE the horse name,
    e.g. "16 Fiddy" means entry number is "16" and horse name is "Fiddy"
  IMPORTANT: Extract ONLY the entry number digits. Do not combine with nearby date digits.
- Rider's full name from the "Name of Rider" field (not the horse name)
- Competition date visible on this cover

Return ONLY this JSON (no markdown, no code block):
{
  "business_name": "USDF",
  "document_type": "Test",
  "document_title": null,
  "invoice_date": "YYYY-MM-DD or null",
  "invoice_number": null,
  "patient_animal_name": null,
  "account_type": null,
  "account_last_4": null,
  "usdf_test_name": "USDF Test Name or null",
  "usdf_rider_number": "digits only or null",
  "usdf_rider_name": "Full Name or null"
}"""


def _find_soffice_cmd():
    """Find LibreOffice soffice command for DOCX conversion"""
    for path in [
        '/Applications/LibreOffice.app/Contents/MacOS/soffice',
        '/opt/homebrew/bin/soffice',
        '/usr/local/bin/soffice',
        '/usr/bin/soffice',
        '/usr/local/bin/libreoffice',
        '/usr/bin/libreoffice',
    ]:
        if os.path.exists(path):
            return path
    for cmd in ['soffice', 'libreoffice']:
        try:
            result = subprocess.run(['which', cmd], capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            continue
    return None


def _convert_image_to_pdf_imagemagick(file_path, temp_pdf_path):
    """Convert image to PDF using ImageMagick as fallback"""
    logger = logging.getLogger(__name__)
    try:
        result = subprocess.run(
            ['convert', file_path, temp_pdf_path],
            capture_output=True, text=True, timeout=PDF_CONVERSION_TIMEOUT
        )
        if result.returncode == 0 and os.path.exists(temp_pdf_path):
            logger.info(f"Converted image to PDF via ImageMagick: {temp_pdf_path}")
            return temp_pdf_path, True
        logger.error(f"ImageMagick conversion failed: {result.stderr}")
        return None, False
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.error(f"ImageMagick conversion error: {e}")
        return None, False


def _convert_image_to_pdf(file_path, temp_pdf_path):
    """Convert image file to PDF using Pillow, falling back to ImageMagick"""
    logger = logging.getLogger(__name__)
    file_ext = os.path.splitext(file_path)[1].lower()

    if file_ext == '.heic' and not HAS_PILLOW_HEIF:
        logger.warning("pillow-heif not installed; trying ImageMagick for HEIC conversion")
        return _convert_image_to_pdf_imagemagick(file_path, temp_pdf_path)

    try:
        img = PIL.Image.open(file_path)
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')
        img.save(temp_pdf_path, 'PDF', resolution=150)
        logger.info(f"Converted image to PDF via Pillow: {temp_pdf_path}")
        return temp_pdf_path, True
    except Exception as e:
        logger.warning(f"Pillow conversion failed: {e}; trying ImageMagick")
        return _convert_image_to_pdf_imagemagick(file_path, temp_pdf_path)


def _convert_docx_to_pdf(file_path, temp_pdf_path):
    """Convert DOCX to PDF using LibreOffice"""
    logger = logging.getLogger(__name__)
    soffice_cmd = _find_soffice_cmd()
    if not soffice_cmd:
        logger.error("LibreOffice (soffice) not found - required for DOCX conversion")
        print("Error: LibreOffice is required to convert DOCX files. Install from https://www.libreoffice.org/", file=sys.stderr)
        return None, False

    try:
        temp_dir = os.path.dirname(temp_pdf_path)
        result = subprocess.run(
            [soffice_cmd, '--headless', '--convert-to', 'pdf', '--outdir', temp_dir, file_path],
            capture_output=True, text=True, timeout=PDF_CONVERSION_TIMEOUT
        )
        if result.returncode != 0:
            logger.error(f"LibreOffice conversion failed: {result.stderr}")
            return None, False

        input_basename = os.path.splitext(os.path.basename(file_path))[0]
        libreoffice_output = os.path.join(temp_dir, f"{input_basename}.pdf")
        if not os.path.exists(libreoffice_output):
            logger.error(f"LibreOffice produced no output at {libreoffice_output}")
            return None, False

        shutil.move(libreoffice_output, temp_pdf_path)
        logger.info(f"Converted DOCX to PDF via LibreOffice: {temp_pdf_path}")
        return temp_pdf_path, True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.error(f"LibreOffice conversion error: {e}")
        return None, False


def convert_to_pdf(file_path):
    """Convert an image or DOCX file to a temporary PDF for analysis and output.

    Returns (pdf_path, is_temp) where is_temp=True means pdf_path is a temporary
    file that will be renamed/moved by the caller. Returns (None, False) on failure.
    Returns (file_path, False) if no conversion is needed.
    """
    logger = logging.getLogger(__name__)
    file_ext = os.path.splitext(file_path)[1].lower()

    if file_ext not in CONVERTIBLE_EXTENSIONS:
        return file_path, False

    logger.info(f"Converting {file_ext} to PDF: {os.path.basename(file_path)}")
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        temp_pdf_path = tmp.name

    if file_ext in CONVERTIBLE_IMAGE_EXTENSIONS:
        return _convert_image_to_pdf(file_path, temp_pdf_path)
    else:
        return _convert_docx_to_pdf(file_path, temp_pdf_path)


def setup_logging():
    """Setup logging to /tmp (or platform-specific temp) with rotation to keep file size manageable"""
    # Use /tmp on Unix-like systems, fall back to platform temp on others
    if os.path.exists('/tmp') and os.path.isdir('/tmp'):  # nosec B108
        log_file = '/tmp/invoice_renamer.log'  # nosec B108
    else:
        log_file = os.path.join(tempfile.gettempdir(), 'invoice_renamer.log')

    # Check if log file exists and is too large (>100KB), truncate to last 50KB
    if os.path.exists(log_file):
        file_size = os.path.getsize(log_file)
        max_size = 100 * 1024  # 100KB
        if file_size > max_size:
            # Read the last portion of the file
            keep_size = 50 * 1024  # Keep last 50KB
            data = None
            with open(log_file, 'rb') as f:
                f.seek(-keep_size, 2)  # Seek from end
                data = f.read()
                # Find first complete line
                first_newline = data.find(b'\n')
                if first_newline > 0:
                    data = data[first_newline + 1:]

            # Write truncated data back (file is already closed from previous block)
            if data is not None:
                with open(log_file, 'wb') as f:
                    f.write(b'=== LOG TRUNCATED TO PREVENT EXCESSIVE SIZE ===\n')
                    f.write(data)

    logging.basicConfig(
        filename=log_file,
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)


def call_llm_api(prompt, file_path, all_pages=False):
    """Call LLM via llm_client in-process (avoids Python/LiteLLM cold start per retry).

    Falls back to subprocess if in-process import fails. llm_client may call sys.exit
    on hard errors; that is converted to RuntimeError so the renamer can fall back.
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Calling LLM API for file: {file_path}")
    logger.debug(f"Prompt: {prompt[:200]}...")

    try:
        # Import in-process so retries reuse the already-loaded LiteLLM stack and
        # llm_client's file-content cache (pdftotext / pdftoppm not re-run).
        from llm_client import call_llm_api as _llm_call

        logger.info("Calling llm_client in-process")
        try:
            result = _llm_call(prompt, file_path=file_path, all_pages=all_pages)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
            logger.error(f"llm_client exited with code {code}")
            raise RuntimeError(f"llm_client failed with exit code {code}") from e

        if result is None:
            return None
        text = result.strip() if isinstance(result, str) else str(result).strip()
        logger.debug(f"LLM API response: {text[:500] if text else text}")
        return text
    except ImportError as e:
        logger.warning(f"In-process llm_client import failed ({e}); falling back to subprocess")
        return _call_llm_api_subprocess(prompt, file_path, all_pages)
    except RuntimeError:
        raise
    except Exception as e:
        logger.error(f"Error calling LLM API in-process: {e}")
        raise


def _call_llm_api_subprocess(prompt, file_path, all_pages=False):
    """Subprocess fallback for calling llm_client.py"""
    logger = logging.getLogger(__name__)
    try:
        python_executable = sys.executable
        cmd = [
            python_executable,
            os.path.join(os.path.dirname(__file__), 'llm_client.py'),
            prompt,
            '--file', file_path
        ]
        if all_pages:
            cmd.append('--all-pages')

        logger.info(f"Calling llm_client.py with Python: {python_executable}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        if result.stderr:
            for line in result.stderr.split('\n'):
                if 'Using LLM model:' in line:
                    logger.info(line.strip())
                elif line.strip():
                    logger.debug(f"llm_client: {line.strip()}")

        logger.debug(f"LLM API response: {result.stdout}")
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"Error calling LLM API: {e}")
        if e.stderr:
            logger.error(f"Error details: {e.stderr}")
            if "SSL: CERTIFICATE_VERIFY_FAILED" in e.stderr:
                logger.warning("SSL certificate verification failed")
            elif "exceeds our limit" in e.stderr and "bytes" in e.stderr:
                logger.warning("Image file too large for processing")
        raise
    except FileNotFoundError:
        logger.error("llm_client.py script not found in the same directory")
        raise


def _create_fallback_info():
    """Create fallback invoice info dict when extraction fails"""
    logger = logging.getLogger(__name__)
    current_date = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"Using fallback info with current date: {current_date}")
    return {
        'business_name': 'Unknown',
        'document_type': 'Document',
        'invoice_date': current_date,
        'invoice_number': None,
        'patient_animal_name': None,
        'account_type': None,
        'account_last_4': None
    }


def _call_llm_for_invoice_info(file_path, all_pages=False, filename_hint=None):
    """Call LLM API to extract invoice information"""
    logger = logging.getLogger(__name__)
    try:
        prompt = _build_extraction_prompt(filename_hint)
        response = call_llm_api(prompt, file_path, all_pages=all_pages)
        return response
    except (subprocess.CalledProcessError, FileNotFoundError, RuntimeError, Exception) as e:
        logger.error(f"Failed to call LLM API: {e}")
        # Log detailed environment info for debugging
        logger.error("UNKNOWN_DOCUMENT_FALLBACK: LLM API call failed")
        logger.error(f"  Python executable: {sys.executable}")
        logger.error(f"  File path: {file_path}")
        logger.error(f"  Exception type: {type(e).__name__}")
        logger.error(f"  Exception details: {e}")
        if isinstance(e, subprocess.CalledProcessError):
            logger.error(f"  Return code: {e.returncode}")
            logger.error(f"  Stdout: {e.stdout}")
            logger.error(f"  Stderr: {e.stderr}")
        return None


def _parse_llm_response(response):
    """Parse JSON from LLM response"""
    logger = logging.getLogger(__name__)
    if response is None:
        return None

    try:
        # Look for JSON in the response (must contain business_name or usdf_test_name)
        json_match = re.search(r'\{[^}]*"(?:business_name|usdf_test_name)"[^}]*\}', response, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            parsed_info = json.loads(json_str)
        else:
            # Fallback: try to parse the entire response as JSON
            parsed_info = json.loads(response)

        logger.info(f"Extracted info: {parsed_info}")
        return parsed_info
    except json.JSONDecodeError as e:
        logger.error(f"Could not parse LLM response as JSON: {e}")
        logger.error(f"Response was: {response}")
        logger.error("UNKNOWN_DOCUMENT_FALLBACK: JSON parsing failed")
        logger.error(f"  Response length: {len(response) if response else 0}")
        logger.error(f"  Response preview: {response[:500] if response else 'None'}")
        return None


def _retry_date_extraction(file_path, all_pages=False):
    """Retry date extraction with focused prompt"""
    logger = logging.getLogger(__name__)
    logger.info("Date not extracted, attempting focused date extraction...")

    try:
        date_response = call_llm_api(DATE_EXTRACTION_PROMPT, file_path, all_pages=all_pages)
        date_response = date_response.strip()
        # Check if it looks like a date (YYYY-MM-DD format)
        if re.match(r'\d{4}-\d{2}-\d{2}', date_response):
            logger.info(f"Focused extraction found date: {date_response}")
            return date_response
        else:
            logger.info(f"Focused extraction did not find a valid date: {date_response}")
            return None
    except Exception as e:
        logger.warning(f"Focused date extraction failed: {e}")
        return None


def _validate_invoice_data(parsed_info):
    """Validate and log warnings for invoice data"""
    logger = logging.getLogger(__name__)

    # Warn when account_type is present without an id (incomplete bank/CC pair).
    # last4 without type is fine (utility bills, etc.). Portfolio never needs last4.
    has_account_type = parsed_info.get('account_type') is not None
    has_account_last_4 = parsed_info.get('account_last_4') is not None
    account_type_value = parsed_info.get('account_type')
    is_portfolio = account_type_value and account_type_value.lower() == 'portfolio'
    if has_account_type and not has_account_last_4 and not is_portfolio:
        logger.warning(
            f"Partial bank statement data: account_type={parsed_info.get('account_type')}, "
            f"account_last_4={parsed_info.get('account_last_4')}"
        )

    # Validate that document_type was provided
    if not parsed_info.get('document_type'):
        logger.warning("Document type not provided by API, defaulting to 'Document'")
        parsed_info['document_type'] = 'Document'


def _find_pdftoppm():
    """Find pdftoppm command in common locations"""
    for path in ['/opt/homebrew/bin/pdftoppm', '/usr/bin/pdftoppm', '/usr/local/bin/pdftoppm']:
        if os.path.exists(path):
            return path
    try:
        result = subprocess.run(['which', 'pdftoppm'], capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def _extract_usdf_page2_rotated(pdf_path):
    """Extract page 2 from a USDF scorecard PDF, rotate 90° CCW, return temp JPEG path.

    The test booklet cover is stapled rotated on page 2; rotating corrects orientation for OCR.
    Caller is responsible for deleting the returned temp file.
    """
    logger = logging.getLogger(__name__)
    pdftoppm_cmd = _find_pdftoppm()
    if not pdftoppm_cmd:
        logger.warning("pdftoppm not found; cannot extract USDF page 2")
        return None

    tmpdir = tempfile.mkdtemp(prefix='usdf_p2_')
    try:
        temp_prefix = os.path.join(tmpdir, 'page')
        subprocess.run(
            [pdftoppm_cmd, '-f', '2', '-l', '2', '-jpeg', '-r', '200', pdf_path, temp_prefix],
            capture_output=True, timeout=PDF_CONVERSION_TIMEOUT
        )
        candidates = glob.glob(os.path.join(tmpdir, 'page*.jpg'))
        if not candidates:
            logger.warning("pdftoppm produced no output for USDF page 2")
            return None

        img = PIL.Image.open(sorted(candidates)[0])
        rotated = img.rotate(90, expand=True)
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False, prefix='usdf_rotated_') as f:
            rotated_path = f.name
        rotated.save(rotated_path, 'JPEG', quality=95)
        logger.info(f"Extracted and rotated USDF page 2: {rotated_path}")
        return rotated_path
    except Exception as e:
        logger.error(f"Failed to extract/rotate USDF page 2: {e}")
        return None
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def extract_invoice_info(file_path, all_pages=False, filename_hint=None):
    """Extract business name and date from invoice using LLM"""
    logger = logging.getLogger(__name__)
    logger.info(f"Extracting invoice info from: {file_path}")
    if filename_hint:
        logger.info(f"Using original filename as hint: {filename_hint}")

    # Call LLM API
    response = _call_llm_for_invoice_info(file_path, all_pages, filename_hint)
    if response is None:
        return _create_fallback_info()

    # Parse JSON response
    parsed_info = _parse_llm_response(response)
    if parsed_info is None:
        return _create_fallback_info()

    # USDF test: if rider info is incomplete, extract page 2 rotated 90° and re-OCR the cover
    if (parsed_info.get('usdf_test_name') and
            not all_pages and
            (not parsed_info.get('usdf_rider_name') or not parsed_info.get('usdf_rider_number'))):
        logger.info("USDF test detected with incomplete rider info; extracting page 2 rotated for OCR")
        page2_path = _extract_usdf_page2_rotated(file_path)
        if page2_path:
            try:
                retry_response = call_llm_api(USDF_PAGE2_PROMPT, page2_path)
                if retry_response:
                    retry_info = _parse_llm_response(retry_response)
                    if retry_info:
                        # Merge: don't lose fields that page 1 found but page 2 missed
                        for field in ('usdf_test_name', 'usdf_rider_number', 'usdf_rider_name', 'invoice_date'):
                            if not retry_info.get(field) and parsed_info.get(field):
                                retry_info[field] = parsed_info[field]
                        parsed_info = retry_info
            finally:
                try:
                    os.unlink(page2_path)
                except OSError:
                    pass

    # If date is missing, try a focused follow-up query to extract it
    if not parsed_info.get('invoice_date'):
        date = _retry_date_extraction(file_path, all_pages)
        if date:
            parsed_info['invoice_date'] = date
        else:
            # If still no date found, use current date as fallback
            current_date = datetime.now().strftime("%Y-%m-%d")
            parsed_info['invoice_date'] = current_date
            logger.info(f"No date detected, using current date as fallback: {current_date}")

    # Validate and log warnings
    _validate_invoice_data(parsed_info)

    return parsed_info


def _apply_filename_abbreviations(text):
    """Apply known short-name abbreviations for concise filenames."""
    if not text:
        return text
    for pattern, short in FILENAME_ABBREVIATIONS:
        if pattern.match(text):
            return short
    return text


def clean_filename(text, limit_words=None):
    """Clean text to be safe for filename use and apply proper capitalization"""
    if not text:
        return "Unknown"

    # Remove or replace problematic characters
    cleaned = re.sub(r'[<>:"/\\|?*,]', '', text)  # Remove illegal filename chars
    cleaned = re.sub(r'\s+', ' ', cleaned)        # Normalize whitespace
    cleaned = cleaned.strip()                     # Remove leading/trailing space

    # Convert to proper capitalization if text is mostly uppercase
    # Skip titlecase for short names (likely acronyms like USAA, IBM, etc.)
    letter_chars = [c for c in cleaned if c.isalpha()]
    if letter_chars and sum(1 for c in letter_chars if c.isupper()) > len(letter_chars) * 0.7:
        if len(cleaned) >= 5:  # Only apply titlecase to names 5+ characters
            cleaned = titlecase(cleaned)

    # Limit to specified number of words if requested
    if limit_words:
        words = cleaned.split()
        if len(words) > limit_words:
            cleaned = ' '.join(words[:limit_words])

        # Remove trailing articles/conjunctions/prepositions/common business terms
        trailing_words = ['and', 'or', 'of', 'the', 'a', 'an', 'for', 'to', 'in', 'at', 'by', 'with', 'company', 'inc', 'llc', 'ltd', 'corp', 'corporation']
        words = cleaned.split()
        while words and words[-1].lower() in trailing_words:
            words.pop()
        if words:
            cleaned = ' '.join(words)

    # Limit length
    if len(cleaned) > 50:
        cleaned = cleaned[:50].rstrip()

    # Shorten known verbose vendor/terms for concise filenames
    cleaned = _apply_filename_abbreviations(cleaned)

    return cleaned if cleaned else "Unknown"


def _normalize_account_id(value):
    """Normalize account identifier for filenames: short, low-PII, alphanumeric OK.

    - If 4+ digits present (e.g. xxxx1234, xx-1234, full numbers): keep last 4 digits only
    - Else short alphanumeric refs (e.g. A12B): keep as-is up to MAX_ACCOUNT_ID_LEN
    - Too short or empty: None
    """
    if not value or value == "null":
        return None
    raw = str(value).strip()
    digits = re.sub(r'[^\d]', '', raw)
    alnum = re.sub(r'[^A-Za-z0-9]', '', raw)
    if not alnum:
        return None
    # Prefer last 4 digits when enough digits exist (masks / full account numbers)
    if len(digits) >= 4:
        return digits[-4:]
    # Pure digit strings shorter than 4 are not useful as last-4 identifiers
    if alnum.isdigit():
        return None
    # Short alphanumeric account refs without a 4-digit suffix
    if len(alnum) > MAX_ACCOUNT_ID_LEN:
        return alnum[-4:]
    if len(alnum) < 2:
        return None
    return alnum


def _normalize_invoice_number(value):
    """Normalize invoice/doc reference: short alphanumeric OK; long digit strings → last 4."""
    if not value or value == "null":
        return None
    # Allow hyphen in middle of id then strip for safety — keep alnum only for FS
    cleaned = re.sub(r'[^A-Za-z0-9]', '', str(value))
    if not cleaned:
        return None
    if cleaned.isdigit():
        if len(cleaned) < 2:
            return None
        # Long pure-digit refs look like account numbers — last 4 only
        if len(cleaned) > MAX_ACCOUNT_ID_LEN:
            return cleaned[-4:]
        return cleaned
    if len(cleaned) > MAX_ACCOUNT_ID_LEN:
        return cleaned[:MAX_ACCOUNT_ID_LEN]
    if len(cleaned) < 2:
        return None
    return cleaned


def format_date(date_str):
    """Convert date string to YYYYMMDD format"""
    if not date_str:
        return "00000000"

    # Try different date formats
    date_formats = [
        "%Y-%m-%d",      # 2024-09-23
        "%m/%d/%Y",      # 09/23/2024
        "%m-%d-%Y",      # 09-23-2024
        "%d/%m/%Y",      # 23/09/2024
        "%Y/%m/%d",      # 2024/09/23
        "%B %d, %Y",     # September 23, 2024
        "%b %d, %Y",     # Sep 23, 2024
        "%d %B %Y",      # 23 September 2024
        "%d %b %Y",      # 23 Sep 2024
    ]

    for fmt in date_formats:
        try:
            date_obj = datetime.strptime(date_str, fmt)
            # Validate that the date is reasonable (not in far future/past)
            now = datetime.now()
            if date_obj.year < 1900 or date_obj.year > now.year + 10:
                continue
            return date_obj.strftime("%Y%m%d")
        except ValueError:
            continue

    # If no format matches, try to extract YYYY-MM-DD pattern with validation
    match = re.search(r'(\d{4})-?(\d{2})-?(\d{2})', date_str)
    if match:
        try:
            year, month, day = map(int, match.groups())
            # Basic date validation
            if 1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= datetime.now().year + 10:
                # Additional day validation for months with < 31 days
                days_in_month = [31, 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
                if day <= days_in_month:
                    return f"{year:04d}{month:02d}{day:02d}"
        except (ValueError, IndexError):
            pass

    return "00000000"


def _sanitize_document_fields(info):
    """Sanitize account and invoice fields based on document type"""
    # Clean up any "null" strings returned by API - convert to None
    for key in info:
        if info[key] == "null":
            info[key] = None

    # Only include account details for document types that reference financial accounts
    account_detail_types = ['Statement', 'Report', 'Notice', 'Letter', 'Policy', 'Contract']
    if info.get('document_type') not in account_detail_types:
        info['account_type'] = None
        info['account_last_4'] = None

    # For receipts and confirmations, don't treat numbers as invoice numbers
    if info.get('document_type') in ['Receipt', 'Confirmation']:
        info['invoice_number'] = None


def _clean_and_validate_fields(info):
    """Clean and validate individual fields from invoice info"""
    business_name = clean_filename(info.get('business_name'), limit_words=4)
    document_type = clean_filename(info.get('document_type')) if info.get('document_type') else 'Document'
    raw_title = _raw_qualifier(info)
    document_title = clean_filename(raw_title, limit_words=5) if raw_title else None
    invoice_date = format_date(info.get('invoice_date'))

    # Process invoice number (short alphanumeric OK; long digit strings trimmed)
    invoice_number = _normalize_invoice_number(info.get('invoice_number'))
    if invoice_number:
        invoice_number = clean_filename(invoice_number)

    # Process patient/animal name
    patient_animal_name = clean_filename(info.get('patient_animal_name')) if info.get('patient_animal_name') else None

    # Process account type
    account_type = clean_filename(info.get('account_type')) if info.get('account_type') else None

    # Process account identifier (last 4 digits or short alphanumeric — low PII)
    account_last_4 = _normalize_account_id(info.get('account_last_4'))
    if account_last_4:
        account_last_4 = clean_filename(account_last_4)
    elif info.get('account_last_4'):
        # Had a value but it was invalid/too short — drop incomplete account pair
        account_type = None
    else:
        account_last_4 = None

    usdf_test_name = clean_filename(info.get('usdf_test_name')) if info.get('usdf_test_name') else None
    usdf_rider_number = clean_filename(info.get('usdf_rider_number')) if info.get('usdf_rider_number') else None
    usdf_rider_name = clean_filename(info.get('usdf_rider_name')) if info.get('usdf_rider_name') else None

    return {
        'business_name': business_name,
        'document_type': document_type,
        'document_title': document_title,
        'invoice_date': invoice_date,
        'invoice_number': invoice_number,
        'patient_animal_name': patient_animal_name,
        'account_type': account_type,
        'account_last_4': account_last_4,
        'usdf_test_name': usdf_test_name,
        'usdf_rider_number': usdf_rider_number,
        'usdf_rider_name': usdf_rider_name,
    }


# Assembly policy: types where qualifier is a subtype that keeps the type word
# ("Trade" + Confirmation → "Trade Confirmation"). All other types use qualifier
# as the full Topic segment (e.g. premise "Barn" replaces Statement).
_TYPES_KEEP_SUBTYPE_WITH_TYPE = frozenset({
    'confirmation', 'certificate', 'permit',
})
# Account categories that are not useful as a middle filename token
_EXCLUDED_ACCOUNT_TYPES = frozenset({
    'life insurance', 'annuity', 'vul',
})


def _select_display_topic(business_name, document_type, document_title):
    """Turn (type, qualifier) into the Topic segment of the filename.

    Policy (owned entirely by code — the LLM only supplies facts):
      - no qualifier → document_type
      - qualifier restates type / vendor / filler only → document_type
      - type in {Confirmation, Certificate, Permit} → "{qualifier} {type}" when type not already in qualifier
      - otherwise → qualifier alone (replaces type; e.g. utility premise "Barn")

    Examples:
      ("Alaska Cruise", "Itinerary", "Travel Itinerary") → "Itinerary"
      ("Acme Insurance", "Policy", "Automobile Policy Packet") → "Automobile Policy Packet"
      ("IRS", "Notice", "Tax Delinquent Notice") → "Tax Delinquent"
      ("Fidelity", "Confirmation", "Trade") → "Trade Confirmation"
      ("National Grid", "Statement", "Barn") → "Barn"
    """
    dtype = document_type or 'Document'
    if not document_title:
        return dtype

    title = document_title.strip()
    if not title:
        return dtype

    title_l = title.lower()
    dtype_l = dtype.lower()
    if title_l == dtype_l:
        return dtype

    title_words = title.split()
    type_words = dtype.split()

    # Drop type phrase when it is a whole-word suffix ("Travel Itinerary" + Itinerary → "Travel")
    # Do not strip type words from the middle (keep "Automobile Policy Packet" intact)
    if type_words and len(title_words) >= len(type_words):
        suffix = [w.lower() for w in title_words[-len(type_words):]]
        if suffix == [w.lower() for w in type_words]:
            title_words = title_words[:-len(type_words)]

    # Drop words already present in the vendor/business name
    vendor_words = {w.lower() for w in (business_name or '').split() if w}
    if vendor_words:
        title_words = [w for w in title_words if w.lower() not in vendor_words]

    remaining = ' '.join(title_words).strip()
    if not remaining:
        return dtype

    # Leftover that is only filler ("Travel") is not worth including
    if all(w.lower() in _GENERIC_TITLE_WORDS for w in remaining.split()):
        return dtype

    if remaining.lower() == dtype_l:
        return dtype

    # Subtype types: keep the head noun so "Trade" stays "Trade Confirmation"
    remaining_words_l = {w.lower() for w in remaining.split()}
    type_words_l = {w.lower() for w in type_words}
    if dtype_l in _TYPES_KEEP_SUBTYPE_WITH_TYPE and not type_words_l.issubset(remaining_words_l):
        return f"{remaining} {dtype}"

    return remaining


def _build_filename_parts(fields, file_ext):
    """Assemble the final filename from cleaned fields (deterministic naming grammar).

    Grammar: Vendor [AccountType] Topic [AccountId] [- Party] [RefId] Date.ext
    USDF scorecards use a separate path when usdf_test_name is set.
    """
    # Always use lowercase extensions (.pdf, .jpg, etc.)
    file_ext = (file_ext or '').lower()
    if file_ext and not file_ext.startswith('.'):
        file_ext = f'.{file_ext}'
    business_name = fields['business_name']
    document_type = fields['document_type']
    document_title = fields.get('document_title')
    invoice_date = fields['invoice_date']
    invoice_number = fields['invoice_number']
    patient_animal_name = fields['patient_animal_name']
    account_type = fields['account_type']
    account_last_4 = fields['account_last_4']
    usdf_test_name = fields.get('usdf_test_name')
    usdf_rider_number = fields.get('usdf_rider_number')
    usdf_rider_name = fields.get('usdf_rider_name')

    # USDF domain pack: "<test name> [- <rider number>] [- <rider name>] <date>"
    if usdf_test_name:
        date_part = f" {invoice_date}" if invoice_date and invoice_date != "00000000" else ""
        if usdf_rider_number and usdf_rider_name:
            new_filename = f"{usdf_test_name} - {usdf_rider_number} - {usdf_rider_name}{date_part}{file_ext}"
        elif usdf_rider_name:
            new_filename = f"{usdf_test_name} - {usdf_rider_name}{date_part}{file_ext}"
        elif usdf_rider_number:
            new_filename = f"{usdf_test_name} - {usdf_rider_number}{date_part}{file_ext}"
        else:
            new_filename = f"{usdf_test_name}{date_part}{file_ext}"
        return new_filename, invoice_date

    display_topic = _select_display_topic(business_name, document_type, document_title)

    # Account type is optional: utility/telecom often have last4 with no bank-style type.
    include_account_type = bool(
        account_type and account_type.lower() not in _EXCLUDED_ACCOUNT_TYPES
    )
    is_portfolio = include_account_type and account_type.lower() == 'portfolio'

    if is_portfolio:
        # Multi-account portfolio: type only, no last-4
        filename_parts = [business_name, account_type, display_topic]
    elif include_account_type and account_last_4:
        # Bank/CC style: type + last 4
        filename_parts = [business_name, account_type, display_topic, account_last_4]
    elif account_last_4:
        # Utility etc.: last-4 without a typed account category
        filename_parts = [business_name, display_topic, account_last_4]
    elif include_account_type:
        filename_parts = [business_name, account_type, display_topic]
    else:
        filename_parts = [business_name, display_topic]

    if patient_animal_name:
        filename_parts.append(f"- {patient_animal_name}")

    # Short invoice/doc id only when we don't already have an account identifier
    if invoice_number and not account_last_4:
        filename_parts.append(invoice_number)

    if invoice_date and invoice_date != "00000000":
        filename_parts.append(invoice_date)

    new_filename = f"{' '.join(filename_parts)}{file_ext}"
    return new_filename, invoice_date


def _handle_duplicate_filename(target_dir, new_filename, file_path, invoice_date, file_ext):
    """Handle duplicate filenames by adding counter before date"""
    logger = logging.getLogger(__name__)
    base_new_file_path = os.path.join(target_dir, new_filename)
    new_file_path = base_new_file_path

    # If target exists and it's not the same file, add numeric suffix before date
    counter = 2
    max_attempts = 100
    while os.path.exists(new_file_path) and os.path.abspath(new_file_path) != os.path.abspath(file_path):
        # Safety check at start of loop to prevent infinite iterations
        if counter > max_attempts:
            logger.error(f"Too many duplicate files (checked {max_attempts} variations), giving up")
            print("Error: Too many files with similar names exist", file=sys.stderr)
            return None

        # Extract parts to insert counter before date
        base_name = os.path.splitext(new_filename)[0]

        # If there's a valid date in the original filename construction, it should be at the end
        # Check if the filename was constructed with a date originally
        original_had_date = invoice_date and invoice_date != "00000000"

        if original_had_date and base_name.endswith(invoice_date):
            # Remove the date from the end
            name_without_date = base_name[:-len(invoice_date)].rstrip()
            # Add counter and date back
            unique_filename = f"{name_without_date} {counter} {invoice_date}{file_ext}"
        elif original_had_date:
            # Original construction had date, but it's not at the end for some reason
            # Add counter before what should be the date position
            unique_filename = f"{base_name} {counter}{file_ext}"
        else:
            # No date at end, just append counter at the end
            unique_filename = f"{base_name} {counter}{file_ext}"

        new_file_path = os.path.join(target_dir, unique_filename)
        counter += 1

    return new_file_path


def _handle_case_only_rename(file_path, new_file_path, move_to, target_dir):
    """Handle two-step rename for case-only changes on case-insensitive filesystems"""
    logger = logging.getLogger(__name__)
    current_filename = os.path.basename(file_path)
    target_filename = os.path.basename(new_file_path)

    logger.info("Performing case-only rename")
    temp_path = None
    try:
        # Create unique temporary name based on original filename and timestamp
        file_base = os.path.splitext(file_path)[0]
        file_ext = os.path.splitext(file_path)[1]

        # Create a hash from the original and target paths for uniqueness
        # MD5 is not used for security here, just for generating a unique filename
        unique_hash = hashlib.md5(f"{file_path}->{new_file_path}".encode(), usedforsecurity=False).hexdigest()[:8]  # nosec B324
        temp_path = f"{file_base}.tmp_{unique_hash}{file_ext}"

        logger.debug(f"Using temporary path: {temp_path}")

        # Step 1: Rename to temporary name
        os.rename(file_path, temp_path)
        # Step 2: Rename to final name
        try:
            os.rename(temp_path, new_file_path)
        except OSError as e:
            # Rollback: restore original filename
            logger.error(f"Step 2 failed, rolling back: {e}")
            try:
                os.rename(temp_path, file_path)
                logger.info("Successfully rolled back to original filename")
            except OSError as rollback_error:
                logger.error(f"CRITICAL: Rollback failed, file left at: {temp_path}. Error: {rollback_error}")
            raise
        logger.info(f"Successfully case-renamed: {file_path} -> {new_file_path}")
        if move_to:
            print(f"Renamed {current_filename} to {target_filename} and moved to {os.path.basename(target_dir)}")
        else:
            print(f"Renamed {current_filename} to {target_filename}")
        return True
    except OSError as e:
        logger.error(f"Error during case-only rename: {e}")
        print(f"Error renaming file: {e}", file=sys.stderr)
        return False


def _execute_rename(file_path, new_file_path, move_to, target_dir):
    """Execute the actual rename/move operation"""
    logger = logging.getLogger(__name__)
    current_filename = os.path.basename(file_path)
    target_filename = os.path.basename(new_file_path)
    file_dir = os.path.dirname(file_path)

    # Check if target file already exists
    if os.path.exists(new_file_path):
        # Do case-sensitive filename comparison
        if current_filename == target_filename:
            logger.info("File already has the correct name")
            if move_to and target_dir != file_dir:
                # File has correct name but needs to be moved
                try:
                    shutil.move(file_path, new_file_path)
                    print(f"Moved {target_filename} to {os.path.basename(target_dir)}")
                    return True
                except OSError as e:
                    logger.error(f"Error moving file: {e}")
                    print(f"Error moving file: {e}", file=sys.stderr)
                    return False
            else:
                print(f"File already correctly named: {target_filename}")
                return True
        elif current_filename.lower() == target_filename.lower():
            # Same filename but different case - this is a case-only rename
            return _handle_case_only_rename(file_path, new_file_path, move_to, target_dir)
        else:
            logger.error(f"Target file already exists: {new_file_path}")
            print(f"Error: Target file '{new_file_path}' already exists", file=sys.stderr)
            return False

    # Rename/move the file (shutil.move handles both same-dir renames and cross-filesystem moves)
    try:
        shutil.move(file_path, new_file_path)
        if move_to:
            logger.info(f"Successfully moved and renamed: {file_path} -> {new_file_path}")
            print(f"Renamed {current_filename} to {target_filename} and moved to {os.path.basename(target_dir)}")
        else:
            logger.info(f"Successfully renamed: {file_path} -> {new_file_path}")
            print(f"Renamed {current_filename} to {target_filename}")
        return True
    except FileExistsError:
        logger.error(f"Target file already exists (race condition): {new_file_path}")
        print(f"Error: Target file '{new_file_path}' already exists", file=sys.stderr)
        return False
    except OSError as e:
        logger.error(f"Error renaming/moving file: {e}")
        print(f"Error renaming/moving file: {e}", file=sys.stderr)
        return False


def rename_invoice(file_path, dry_run=False, move_to=None, all_pages=False):
    """Rename invoice file based on extracted information and optionally move to target directory.

    If the file is a convertible format (image or DOCX), it is first converted to PDF,
    the PDF is renamed to the descriptive name, and the original file is deleted.
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Starting rename process for: {file_path}")
    logger.info(f"Python environment: {sys.executable}")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Command line args: {sys.argv}")

    # Fresh content cache per rename (retries within this call still share the cache)
    try:
        from llm_client import clear_file_content_cache
        clear_file_content_cache()
    except ImportError:
        pass

    # Validate file exists
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        print(f"Error: File '{file_path}' not found", file=sys.stderr)
        return False

    logger.debug(f"Processing: {file_path}")

    original_ext = os.path.splitext(file_path)[1].lower()
    needs_conversion = original_ext in CONVERTIBLE_EXTENSIONS

    # Convert to PDF if needed (images/DOCX → PDF for both LLM extraction and output)
    temp_pdf_path = None
    processing_file = file_path

    if needs_conversion:
        logger.info(f"Converting {original_ext} to PDF before processing")
        converted_path, is_temp = convert_to_pdf(file_path)
        if converted_path is None:
            print(f"Error: Could not convert {os.path.basename(file_path)} to PDF", file=sys.stderr)
            return False
        processing_file = converted_path
        if is_temp:
            temp_pdf_path = converted_path

    # Extract and sanitize information from the (possibly converted) file
    filename_hint = _original_filename_hint(file_path)
    info = extract_invoice_info(processing_file, all_pages=all_pages, filename_hint=filename_hint)
    # Filename hint safety net — recover qualifier if the model left it null
    _apply_filename_hint_fallback(info, filename_hint)
    _sanitize_document_fields(info)
    fields = _clean_and_validate_fields(info)

    # USDF tests: competition date is always today; warn and override if date differs
    if fields.get('usdf_test_name'):
        today = datetime.now().strftime("%Y%m%d")
        extracted_date = fields['invoice_date']
        if extracted_date != today:
            logger.warning(f"USDF date mismatch: extracted {extracted_date}, expected today {today}; overriding")
            send_notification(
                "Invoice Renamer",
                f"USDF date mismatch for {os.path.basename(file_path)}: "
                f"scorecard shows {extracted_date}, using today {today}"
            )
            fields['invoice_date'] = today

    # Log extracted fields
    logger.info(f"Extracted business name: {fields['business_name']}")
    logger.info(f"Extracted document type: {fields['document_type']}")
    if fields.get('document_title'):
        logger.info(f"Extracted document title: {fields['document_title']}")
    logger.info(f"Extracted date: {info.get('invoice_date')} -> {fields['invoice_date']}")
    if fields['invoice_number']:
        logger.info(f"Extracted invoice number: {fields['invoice_number']}")
    if fields['patient_animal_name']:
        logger.info(f"Extracted patient/animal name: {fields['patient_animal_name']}")
    if fields['account_type']:
        logger.info(f"Extracted account type: {fields['account_type']}")
    if fields['account_last_4']:
        logger.info(f"Extracted account last 4: {fields['account_last_4']}")
    if fields.get('usdf_test_name'):
        logger.info(f"Extracted USDF test name: {fields['usdf_test_name']}")
    if fields.get('usdf_rider_number'):
        logger.info(f"Extracted USDF rider number: {fields['usdf_rider_number']}")
    if fields.get('usdf_rider_name'):
        logger.info(f"Extracted USDF rider name: {fields['usdf_rider_name']}")

    # Output is always .pdf for converted files; otherwise preserve original extension (lowercase)
    file_dir = os.path.dirname(file_path)
    output_ext = '.pdf' if needs_conversion else os.path.splitext(file_path)[1].lower()

    # Build filename
    new_filename, invoice_date = _build_filename_parts(fields, output_ext)

    # Determine target directory
    target_dir = move_to if move_to else file_dir
    if move_to and not os.path.exists(move_to):
        if dry_run:
            logger.info(f"Target directory does not exist (would be created): {move_to}")
        else:
            os.makedirs(move_to, exist_ok=True)
            logger.info(f"Created target directory: {move_to}")

    # Handle duplicate filenames (check against target dir, not temp PDF path)
    new_file_path = _handle_duplicate_filename(target_dir, new_filename, processing_file, invoice_date, output_ext)
    if new_file_path is None:
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            try:
                os.unlink(temp_pdf_path)
            except OSError:
                pass
        return False  # Too many duplicates

    new_filename = os.path.basename(new_file_path)
    logger.info(f"New filename: {new_filename}")

    # Handle dry run mode
    if dry_run:
        logger.info("Dry run mode - file not actually renamed")
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            try:
                os.unlink(temp_pdf_path)
            except OSError:
                pass
        action = "Would convert and rename" if needs_conversion else "Would rename"
        if move_to:
            print(f"{action} {os.path.basename(file_path)} to {new_filename} and move to {os.path.basename(target_dir)}")
        else:
            print(f"{action} {os.path.basename(file_path)} to {new_filename}")
        return True

    # Execute rename/move of the (possibly converted) PDF
    result = _execute_rename(processing_file, new_file_path, move_to, target_dir)

    if result and needs_conversion:
        # Delete the original source file now that the PDF has been renamed/moved
        try:
            os.unlink(file_path)
            logger.info(f"Deleted original file after conversion: {file_path}")
        except OSError as e:
            logger.warning(f"Could not delete original file {file_path}: {e}")
    elif not result and temp_pdf_path and os.path.exists(temp_pdf_path):
        # Rename failed — clean up the temp PDF so we don't leave orphans
        try:
            os.unlink(temp_pdf_path)
        except OSError:
            pass

    return result


def main():
    # Setup logging first
    logger = setup_logging()
    logger.info("=== Invoice Renamer Started ===")

    parser = argparse.ArgumentParser(description="Rename invoice files based on business name and date")
    parser.add_argument("file", help="Invoice file to rename")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without actually renaming")
    parser.add_argument("--move-to", help="Target directory to move the renamed file to")
    parser.add_argument("--all-pages", action="store_true",
                        help="Process all pages of PDF (default: first 2 pages — cover + content)")

    try:
        args = parser.parse_args()
        logger.info(f"Arguments: file={args.file}, dry_run={args.dry_run}, move_to={args.move_to}, all_pages={args.all_pages}")

        success = rename_invoice(args.file, args.dry_run, args.move_to, args.all_pages)
        logger.info(f"=== Invoice Renamer Finished - Success: {success} ===")

        if success:
            sys.exit(0)
        else:
            sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("Operation interrupted by user")
        print("\nOperation cancelled by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error in main: {e}")
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
