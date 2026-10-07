"""Document-family extractors for text PDFs.

Labeled lines decide policy coverage, account id, statement date, service
location, and patient names. Those facts overwrite the model. The model is
asked only for what a label cannot decide: short vendor, document type when
no heading decides it, and a qualifier when none is printed.

A new issuer is a new parser plus a golden text dump, not another paragraph
in the shared prompt.
"""
import logging
import re
from datetime import datetime

MAX_ACCOUNT_ID_LEN = 8
# Edward Jones / similar: AAA-BBBBB-C-D — last-4 of the 5-digit body, not the check-digit tail
BROKERAGE_HYPHEN_ACCOUNT_RE = re.compile(r'^(?:\d{2,4}-)?(\d{5})-\d(?:-\d)?$')
YEAR_TOKEN_RE = re.compile(r'^(?:19|20)\d{2}$')
ACCOUNT_LABEL_COLUMN_SLACK = 8
# "Account Number" / "Account No." / "Account #" — not "Account Notice"
ACCOUNT_NUMBER_LABEL_RE = re.compile(
    r'(?i)\baccount\s*(?:number\b|no\.?\b|#)'
)
# Labeled insurance product lines. Longest phrases first so
# "Workers Compensation" is not shortened to a later token.
POLICY_COVERAGE_PHRASES = (
    ("workers' compensation", 'Workers Compensation'),
    ("worker's compensation", 'Workers Compensation'),
    ('workers compensation', 'Workers Compensation'),
    ('commercial auto', 'Commercial Auto'),
    ('personal automobile', 'Auto'),
    ('personal auto', 'Auto'),
    ('homeowners', 'Homeowners'),
    ('homeowner', 'Homeowners'),
    ("renter's", 'Renters'),
    ('renters', 'Renters'),
    ('condominium', 'Condo'),
    ('inland marine', 'Inland Marine'),
    ('motorcycle', 'Motorcycle'),
    ('umbrella', 'Umbrella'),
    ('automobile', 'Auto'),
    ('dwelling', 'Dwelling'),
    ('flood', 'Flood'),
    ('condo', 'Condo'),
    ('boat', 'Boat'),
    ('auto', 'Auto'),
    ('life', 'Life'),
)
# "Policy Being Billed" / "Policy Type" / "POLICY" — not the word "policies"
POLICY_LABEL_RE = re.compile(
    r'(?i)\b(?:policy(?!ies\b)(?:\s+being\s+billed|\s+type|\s+name)?|line\s+of\s+business)\b'
)
# Draft account on an insurance bill: "bank account ending in 0529"
PAYMENT_ACCOUNT_ENDING_RE = re.compile(
    r'(?i)\b(?:bank|checking|savings|debit|payment)\s+account\s+ending\s+in\s+(\d{4})\b'
)
POLICY_LOOKAHEAD_LINES = 4

# Labeled statement dates beat billing-period ranges. Stronger labels win.
# Bare "as of" only at line start so "Reward Dollars as of …" is not the statement date.
LABELED_STATEMENT_DATE_RE = re.compile(
    r'(?P<label>'
    r'statement\s*(?:closing\s*)?date'
    r'|closing\s*date'
    r'|bill\s*date'
    r'|as\s*of\s*date'
    r'|(?:^|\n)\s*as\s*of'
    r')\s*[:\-]?\s*'
    r'(?P<date>'
    r'\d{1,2}/\d{1,2}/\d{2,4}'
    r'|\d{4}-\d{2}-\d{2}'
    r'|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}'
    r'|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}'
    r')',
    re.IGNORECASE | re.MULTILINE,
)
LABELED_STATEMENT_DATE_RANK = {
    'statement date': 1,
    'statement closing date': 1,
    'closing date': 1,
    'bill date': 2,
    'as of date': 3,
    'as of': 4,
}
PERIOD_RANGE_RES = (
    re.compile(
        r'(?P<start>\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\s*(?:[-–—]|to)\s*'
        r'(?P<end>\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})',
        re.IGNORECASE,
    ),
    re.compile(
        r'(?P<start>[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})\s*(?:[-–—]|to)\s*'
        r'(?P<end>[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})',
        re.IGNORECASE,
    ),
    re.compile(
        r'(?P<start>\d{1,2}/\d{1,2}/\d{2,4})\s*(?:[-–—]|to)\s*'
        r'(?P<end>\d{1,2}/\d{1,2}/\d{2,4})',
    ),
    re.compile(
        r'(?P<start>\d{4}-\d{2}-\d{2})\s*(?:[-–—]|to)\s*'
        r'(?P<end>\d{4}-\d{2}-\d{2})',
    ),
)
PERIOD_DATE_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y", "%m/%d/%y",
    "%d/%m/%Y", "%d/%m/%y",
    "%B %d, %Y", "%b %d, %Y",
    "%B %d %Y", "%b %d %Y",
    "%d %B %Y", "%d %b %Y",
)
STATEMENT_HEAD_CHARS = 2500

# Types that keep a service/financial account id. Receipts do not.
ACCOUNT_DETAIL_TYPES = frozenset({
    'statement', 'report', 'notice', 'letter', 'policy', 'contract',
    'invoice', 'confirmation',
})

# Standalone proof of payment. A bill that also says "receipt" still has one of these.
BILL_SIGNAL_RE = re.compile(
    r'(?i)\b(?:'
    r'invoice\s*(?:number|#|no\b\.?)'
    r'|amount\s+due'
    r'|balance\s+due'
    r'|total\s+due'
    r'|due\s+date'
    r'|new\s+charges'
    r'|min(?:imum)?\s+due'
    r'|remittance'
    r'|policy\s+being\s+billed'
    r'|insurance\s+bill'
    r')\b'
)
RECEIPT_HEADING_RE = re.compile(r'(?i)(?:^|\n)\s*receipt\b')

# Utility/telecom premise. The value still has to look like a premise, not a street.
SERVICE_LOCATION_RE = re.compile(
    r'(?i)\b(?:service\s+location|premise(?:\s+(?:id|name))?|'
    r'meter\s+(?:location|site)|service\s+address)\b'
)

PATIENT_LINE_RE = re.compile(
    r'(?i)\b(?:patient|animal|pet|horse)\s*(?:name)?\s*[:#\-]\s*'
    r"([A-Za-z][A-Za-z'.-]*(?:\s+[A-Za-z][A-Za-z'.-]*){0,2})"
)
GENERIC_PATIENT_LABELS = frozenset({
    'horse', 'horses', 'pony', 'ponies', 'dog', 'dogs', 'cat', 'cats',
    'pet', 'pets', 'patient', 'patients', 'animal', 'animals', 'equine',
    'foal', 'colt', 'filly', 'mare', 'gelding', 'stallion',
})


def account_last4(value):
    """Last-4 or short alphanumeric account id. None when too short.

    Hyphenated brokerage AAA-BBBBB-C-D (609-92865-1-7) keeps the last 4 of
    the 5-digit body (2865), not the check-digit tail.
    """
    if not value or value == "null":
        return None
    raw = str(value).strip()
    compact = re.sub(r'\s+', '', raw)
    hyphenated = BROKERAGE_HYPHEN_ACCOUNT_RE.fullmatch(compact)
    if hyphenated:
        return hyphenated.group(1)[-4:]
    digits = re.sub(r'[^\d]', '', raw)
    alnum = re.sub(r'[^A-Za-z0-9]', '', raw)
    if not alnum:
        return None
    if len(digits) >= 4:
        return digits[-4:]
    if alnum.isdigit():
        return None
    if len(alnum) > MAX_ACCOUNT_ID_LEN:
        return alnum[-4:]
    if len(alnum) < 2:
        return None
    return alnum


def _qualifier(info):
    """document_title, or the qualifier alias, or None."""
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


def _parse_loose_date_token(token):
    """Parse a single date token into YYYY-MM-DD, or None."""
    if not token:
        return None
    cleaned = re.sub(r'\s+', ' ', str(token).strip())
    for fmt in PERIOD_DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _statement_date_label_rank(label):
    """Lower rank wins when several labeled dates are present."""
    key = re.sub(r'\s+', ' ', (label or '').strip().lower())
    return LABELED_STATEMENT_DATE_RANK.get(key, 99)


def parse_labeled_statement_date(text):
    """Labeled Statement/Closing/Bill/As-of Date as YYYY-MM-DD, or None.

    Explicit labels beat billing-period ranges. Closing Date / Statement Date
    beat incidental rewards "as of" snapshots. Does not match Due Date.
    """
    if not text:
        return None
    head = text[:STATEMENT_HEAD_CHARS]
    best = None  # (rank, position, date)
    for match in LABELED_STATEMENT_DATE_RE.finditer(head):
        parsed = _parse_loose_date_token(match.group('date'))
        if not parsed:
            continue
        candidate = (_statement_date_label_rank(match.group('label')), match.start(), parsed)
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    return best[2] if best else None


def parse_statement_period_range(text):
    """Return (start, end) as YYYY-MM-DD from a header period range, or (None, None)."""
    if not text:
        return None, None
    head = text[:STATEMENT_HEAD_CHARS]
    for pattern in PERIOD_RANGE_RES:
        match = pattern.search(head)
        if not match:
            continue
        start = _parse_loose_date_token(match.group('start'))
        end = _parse_loose_date_token(match.group('end'))
        if not end:
            continue
        if start and end < start:
            continue
        return start, end
    return None, None


def parse_statement_period_end(text):
    """Statement period END as YYYY-MM-DD, or None."""
    _, end = parse_statement_period_range(text)
    return end


def apply_statement_date(info, text, is_account_category):
    """Prefer a labeled statement date, else correct a period-start pick.

    is_account_category is invoice_renamer's account-category check so the
    Statement vs Report gate stays in one place. Returns True when the date changes.
    """
    logger = logging.getLogger(__name__)
    if not info or not text:
        return False
    dtype = str(info.get('document_type') or '').strip().lower()
    account_type = info.get('account_type')
    is_financial_statement = (
        dtype in ('statement', 'report')
        or is_account_category(dtype)
        or (account_type and is_account_category(account_type))
    )
    if not is_financial_statement:
        return False

    current = info.get('invoice_date')
    labeled = parse_labeled_statement_date(text)
    if labeled:
        if current != labeled:
            logger.info(
                f"Preferring labeled statement date {labeled} over extracted date {current!r}"
            )
            info['invoice_date'] = labeled
            return True
        return False

    period_start, period_end = parse_statement_period_range(text)
    if not period_end:
        return False
    if not current:
        logger.info(f"Using statement period end {period_end} (no date extracted)")
        info['invoice_date'] = period_end
        return True
    if period_start and current == period_start and current != period_end:
        logger.info(
            f"Preferring statement period end {period_end} over period start {current!r}"
        )
        info['invoice_date'] = period_end
        return True
    return False


def _digit_run_at_column(line, column, slack=ACCOUNT_LABEL_COLUMN_SLACK):
    """4+ digit run whose start is closest to column, or None."""
    best = None
    best_dist = None
    for match in re.finditer(r'\d{4,}', line):
        dist = abs(match.start() - column)
        if best is None or dist < best_dist:
            best = match.group(0)
            best_dist = dist
    if best is None or best_dist > slack:
        return None
    return best


def parse_labeled_account_number(text):
    """Digit string of a labeled Account Number, or None.

    A footer table puts the routing number in a different column. Inline
    "Account Number: 363240448011" works too. "Account Notice" does not match.
    """
    if not text:
        return None
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = ACCOUNT_NUMBER_LABEL_RE.search(line)
        if not match:
            continue
        inline = re.search(r'\d{4,}', line[match.end():])
        if inline:
            if account_last4(inline.group(0)):
                return inline.group(0)
            continue
        label_col = match.start()
        for follow in lines[index + 1:index + 4]:
            if not follow.strip():
                continue
            chosen = _digit_run_at_column(follow, label_col)
            if chosen and account_last4(chosen):
                return chosen
            break
    return None


def parse_labeled_account_last4(text):
    """Last 4 of a labeled Account Number, or None."""
    return account_last4(parse_labeled_account_number(text))


def is_padded_account_tail(model_value, full_digits):
    """True when the model zero-padded a short tail of the real account number.

    "011" and "0011" from 363240448011 are pads. A real last-4 that starts
    with 0 (Fidelity 0961) is not a pad of a different account.
    """
    raw = re.sub(r'\D', '', str(model_value or ''))
    if not raw or not full_digits:
        return False
    if len(raw) >= 4 and full_digits.endswith(raw) and raw == full_digits[-4:]:
        return False
    stripped = raw.lstrip('0')
    if not stripped or len(stripped) >= 4 or len(stripped) < 2:
        return False
    return full_digits.endswith(stripped)


def account_last4_should_read(info):
    """True when a labeled Account Number is allowed to fill or replace the id."""
    if not info:
        return False
    current_norm = account_last4(info.get('account_last_4'))
    if current_norm and not str(current_norm).startswith('0'):
        return False
    dtype = str(info.get('document_type') or '').strip().lower()
    if dtype not in ACCOUNT_DETAIL_TYPES and not info.get('account_type'):
        return False
    return True


def apply_account_last4(info, text):
    """Fill a missing or zero-padded account id from a labeled Account Number.

    A last-4 that does not start with 0 is left alone. Receipts are skipped.
    Returns True when the id changes.
    """
    logger = logging.getLogger(__name__)
    if not account_last4_should_read(info) or not text:
        return False
    current_norm = account_last4(info.get('account_last_4'))
    full_digits = parse_labeled_account_number(text)
    last4 = account_last4(full_digits)
    if not last4 or last4 == current_norm:
        return False
    if current_norm and not is_padded_account_tail(info.get('account_last_4'), full_digits):
        return False
    previous = info.get('account_last_4')
    info['account_last_4'] = last4
    if previous:
        logger.info(
            f"Replaced short account_last_4 {previous!r} with {last4} "
            "from PDF account-number label"
        )
    else:
        logger.info(f"Filled account_last_4 {last4} from PDF account-number label")
    return True


def parse_policy_product_line(line):
    """(coverage, policy_id or None) for one labeled policy product line.

    "NJ Auto 7101" → ("Auto", "7101"). "Workers Compensation" → ("Workers Compensation", None).
    Letterhead such as "United Services Automobile Association" does not match.
    A trailing vehicle year (Auto 2023) is not a policy id.
    """
    text = re.sub(r'\s+', ' ', (line or '').strip())
    if not text or len(text) > 80:
        return None
    stripped = re.sub(
        r'(?i)^(?:policy(?!ies\b)(?:\s+being\s+billed|\s+type|\s+name)?'
        r'|line\s+of\s+business|coverage)\s*[:\-]?\s+',
        '',
        text,
    )
    if stripped != text:
        text = stripped.strip()
    if not text or re.search(r'[$]|/\d', text):
        return None
    for phrase, display in POLICY_COVERAGE_PHRASES:
        match = re.fullmatch(
            rf'(?:[A-Z]{{2}}\s+)?{re.escape(phrase)}(?:\s+(?P<pid>[A-Za-z0-9-]{{3,12}}))?',
            text,
            flags=re.IGNORECASE,
        )
        if not match:
            continue
        pid = match.group('pid')
        if pid and (YEAR_TOKEN_RE.match(pid) or not re.search(r'\d', pid)):
            pid = None
        if pid:
            pid = account_last4(pid)
        return display, pid
    return None


def parse_labeled_policies(text):
    """Unique (coverage, policy_id) pairs from lines next to a policy label."""
    if not text:
        return []
    lines = text.splitlines()
    found = []
    seen = set()
    for index, line in enumerate(lines):
        if not POLICY_LABEL_RE.search(line):
            continue
        candidates = [line]
        checked = 0
        for follow in lines[index + 1:index + 1 + 8]:
            if not follow.strip():
                continue
            candidates.append(follow)
            checked += 1
            if checked >= POLICY_LOOKAHEAD_LINES:
                break
        for candidate in candidates:
            parsed = parse_policy_product_line(candidate)
            if not parsed:
                continue
            if parsed not in seen:
                seen.add(parsed)
                found.append(parsed)
            break
    return found


def payment_account_last4(text):
    """Last 4 of a bank/card account that will be debited, or None."""
    if not text:
        return None
    match = PAYMENT_ACCOUNT_ENDING_RE.search(text)
    if not match:
        return None
    return match.group(1)


def _title_names_coverage(title, coverage):
    """True when title already contains the coverage as a whole word."""
    if not title or not coverage:
        return False
    return re.search(rf'(?i)\b{re.escape(coverage)}\b', str(title)) is not None


def apply_insurance_policy(info, text):
    """Copy one labeled policy line over the model's title and account id.

    "NJ Auto 7101" becomes title Auto and id 7101. A bank account "ending in
    ####" is the payment account, not the policy id. Two distinct coverages
    are left for the model. Returns True when a field changes.
    """
    logger = logging.getLogger(__name__)
    if not info or not text:
        return False
    policies = parse_labeled_policies(text)
    if not policies:
        return False

    coverages = []
    for coverage, _pid in policies:
        if coverage not in coverages:
            coverages.append(coverage)
    ids = []
    for _coverage, pid in policies:
        if pid and pid not in ids:
            ids.append(pid)
    policy_id = ids[0] if len(coverages) == 1 and len(ids) == 1 else None
    payment = payment_account_last4(text)
    changed = False

    if len(coverages) == 1:
        coverage = coverages[0]
        current = _qualifier(info)
        if (current or '').strip().lower() != coverage.lower():
            logger.info(
                f"Filled document_title {coverage!r} from labeled policy line "
                f"(was {current!r})"
            )
            info['document_title'] = coverage
            if 'qualifier' in info:
                info['qualifier'] = coverage
            changed = True
        account_type = info.get('account_type')
        if _title_names_coverage(account_type, coverage):
            logger.info(
                f"Dropped account_type {account_type!r} (restates policy coverage)"
            )
            info['account_type'] = None
            changed = True
    else:
        logger.info(
            f"Multiple labeled policies {coverages!r}; leaving document_title unchanged"
        )

    current_id = account_last4(info.get('account_last_4'))
    if policy_id and current_id != policy_id:
        previous = info.get('account_last_4')
        info['account_last_4'] = policy_id
        logger.info(
            f"Using policy id {policy_id} from labeled policy line (was {previous!r})"
        )
        return True
    if payment and current_id == payment:
        logger.info(
            f"Dropped payment-account last-4 {current_id} "
            "(bank account being debited, not the policy)"
        )
        info['account_last_4'] = None
        return True
    return changed


def is_standalone_receipt(text):
    """True when the page is proof of payment and not a bill.

    "AUTO PAY ACCOUNT RECEIPT" on a page that also has Amount Due / Invoice #
    is still a bill. Receipt must be a heading, not a word in a sentence.
    """
    if not text:
        return False
    if BILL_SIGNAL_RE.search(text):
        return False
    return RECEIPT_HEADING_RE.search(text) is not None


def service_location_label(text):
    """Raw text after a service-location / premise label, or None.

    The caller decides whether it is a premise name (Barn) or a street address.
    """
    if not text:
        return None
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = SERVICE_LOCATION_RE.search(line)
        if not match:
            continue
        rest = line[match.end():].strip(' :-\t')
        candidate = rest
        if not candidate:
            for follow in lines[index + 1:index + 4]:
                if follow.strip():
                    candidate = follow.strip()
                    break
        if not candidate:
            continue
        candidate = re.sub(r'\s+', ' ', candidate).strip()
        candidate = re.split(r'[,|]', candidate)[0].strip()
        if 1 <= len(candidate) <= 40:
            return candidate
    return None


def labeled_patient_names(text):
    """Proper names from Patient/Animal/Pet/Horse labels, in order, de-duplicated."""
    if not text:
        return []
    found = []
    seen = set()
    for match in PATIENT_LINE_RE.finditer(text):
        name = match.group(1).strip()
        words = name.lower().split()
        if not words or all(word in GENERIC_PATIENT_LABELS for word in words):
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(name)
    return found
