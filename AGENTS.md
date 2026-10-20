# Agent instructions: osx-file-renamer

Shared rules (pull before work, tests and lint, secrets, commit attribution)
live in `~/.config/agents/AGENTS.md`. If that file is not loaded (cloud or CI
sessions), the short version is: `git pull --ff-only` first, run the tests
below before committing, never commit secrets, and end agent commits with a
`Co-Authored-By: <Tool> (<model>) <email>` trailer.

## Which coding agent

Use Claude Code with Opus 5.5 for any naming-rule, `document_families.py`, or
prompt change. Those are guarded by the golden tests in `tests/`, and small
edits regress them easily. Grok Build is fine for xAI model-id or LiteLLM
wiring changes, and as a second opinion.

After a pull that touches `pyproject.toml` or other install metadata:
`make install-dev` (or `pip install -e ".[dev]"`).

## Read when the task needs it

- `README.md` — install, commands, API keys, logging, and macOS shortcut usage.
- `docs/architecture.md` — before editing `invoice_renamer.py`, `llm_client.py`, or `document_families.py`.
- `docs/future-optimizations.md` — only for a speed or cost task.

Do not put those docs in `.grok/rules/` or `.claude/rules/`. Every markdown file there is injected on every turn.

## Gates

- Python 3.11+. Imports stay at the top of the file. No unused imports, and nothing between import statements. Use named constants instead of hardcoded timeouts and limits.
- `make lint` and `make test` before every commit. Flake8 max line length is 180 (ignores E201, E202, E402, W503). markdownlint MD013 allows 300 characters per line in this file.
- A behavior change bumps `version` in `pyproject.toml`. Include this file in the same commit when it changes.
- A new top-level module, `py-modules` change, or entry point is invisible to the Shortcuts command until `/usr/local/bin/python3 -m pip install -e .`. Confirm the import from `/tmp` with that interpreter. A passing pytest run from the repo is not enough.

## Naming invariants

Python builds the filename. The model returns facts. On a text PDF, `document_families` overwrites the model. The shared prompt does not repeat those rules. Grammar:

`Vendor [AccountType] Topic [AccountId] [- Party] [RefId] Date.ext`

- `document_title` is a qualifier (premise, subtype, form name), not the filename. Subtype types keep `{qualifier} {type}` (Trade Confirmation). Otherwise the qualifier replaces the type (Barn).
- Premise-style labels are dropped for banks, tolls, and transit. A postal service address is not a premise. A qualifier made only of words from that address (Apt, Apt 102B, Gulf Blvd) is dropped.
- A labeled service location (Barn, Apt 2B) still replaces the type. Bare "Apt" is never a topic. Hex-shaped unit codes (2B, 102B) are not hash fragments.
- Short vendors (Amex, BofA, Chase). Account id is last-4, a short alphanumeric, or a printed 3-digit number (112). A leading-0 short id is a zero-padded tail. A store's in-house charge account is not a Credit Card. Lowercase extensions. Priority is Vendor, then Topic, then AccountId, then Date.
- Hyphenated brokerage `AAA-BBBBB-C-D` uses the last 4 of the 5-digit body (609-92865-1-7 → 2865). Portfolio overviews keep a primary-account last-4 when known.
- Bills with an invoice number, a due date, and new charges stay Invoice even when they list a payment received.
- Insurance copies the labeled POLICY line (Workers Compensation, or "NJ Auto 7101" → Auto). That line's id is the account id. A bank account being debited is not.
- Party is one named patient or animal. Omit it when two or more animals have charges.
- The original filename is a weak signal and a code fallback for a missing qualifier or last-4. Portal invoice-id names (`INV-DF-US-PT0…`) and base64 download tokens are not titles. A UUID fragment (Team ID, tenant id) is not an account id. Use the invoice reference last-4.
- A labeled Account Number, including one past page 2, fills last-4. The neighboring routing number is not the account id.
- A scanned check is `Check <number> <date>`, or `Checks <date>` for several. No payer or vendor. A check date a decade old (handwritten 26 read as 2016) is shifted into the last year.
- Completions use temperature 0 (`LLM_TEMPERATURE`). Known dual brands collapse in `FILENAME_ABBREVIATIONS` (Sheraton Sand Key Resort → Sheraton, Advantage Propane → Paraco).
- A new issuer is a parser plus a redacted dump in `tests/fixtures/naming/`, not another prompt paragraph. Photos and scans have no `pdftotext` output, so families no-op and the vision model still names them.

## Where things live

- Log: `/tmp/invoice_renamer.log` on Unix (platform temp on Windows). INFO level, daily rotation, current day plus one backup. A lost API error must land in that log, not only as exit code 1.
- Command the shortcut runs: `/usr/local/bin/invoice-renamer`.
- API keys: the environment or `~/.env`.
