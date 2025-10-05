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

try:
    from titlecase import titlecase # type: ignore
except ImportError:
    # Fallback if titlecase not available
    def titlecase(text):
        return text.title()

def setup_logging():
    """Setup logging to /tmp/invoice_renamer.log with rotation to keep file size manageable"""
    log_file = '/tmp/invoice_renamer.log'

    # Check if log file exists and is too large (>100KB), truncate to last 50KB
    if os.path.exists(log_file):
        file_size = os.path.getsize(log_file)
        max_size = 100 * 1024  # 100KB
        if file_size > max_size:
            # Read the last portion of the file
            keep_size = 50 * 1024  # Keep last 50KB
            with open(log_file, 'rb') as f:
                f.seek(-keep_size, 2)  # Seek from end
                data = f.read()
                # Find first complete line
                first_newline = data.find(b'\n')
                if first_newline > 0:
                    data = data[first_newline + 1:]

            # Write truncated data back
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

def call_grok_api(prompt, file_path, all_pages=False):
    """Call grok.py script to extract invoice information"""
    logger = logging.getLogger(__name__)
    logger.info(f"Calling Grok API for file: {file_path}")
    logger.debug(f"Prompt: {prompt[:200]}...")

    try:
        cmd = [
            os.path.expanduser('~/.pyenv/shims/python3'),
            os.path.join(os.path.dirname(__file__), 'grok.py'),
            prompt,
            '--file', file_path
        ]
        if all_pages:
            cmd.append('--all-pages')

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        logger.debug(f"Grok API response: {result.stdout}")
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"Error calling Grok API: {e}")
        if e.stderr:
            logger.error(f"Error details: {e.stderr}")
            # Check for specific error types and provide helpful messages
            if "SSL: CERTIFICATE_VERIFY_FAILED" in e.stderr:
                logger.warning("SSL certificate verification failed")
            elif "exceeds our limit" in e.stderr and "bytes" in e.stderr:
                logger.warning("Image file too large for processing")
        raise  # Re-raise to let caller handle
    except FileNotFoundError:
        logger.error("grok.py script not found in the same directory")
        raise  # Re-raise to let caller handle

def extract_invoice_info(file_path, all_pages=False):
    """Extract business name and date from invoice using Grok"""
    logger = logging.getLogger(__name__)
    logger.info(f"Extracting invoice info from: {file_path}")

    prompt = """Extract the following information from this document:
1. Business name - Follow these priority rules:
   - Use the most recognizable ISSUING company/bank name
   - For credit card statements: Use the issuing bank (e.g., "American Express", "Chase", "Citibank") - NOT the card product name
   - For store credit cards: Use the store name (e.g., "Target", "Best Buy") rather than the backing bank
   - For co-branded cards: Use the issuing bank (e.g., "Chase" for Chase Sapphire, not "Sapphire")
   - For subsidiaries/billing entities: Use the parent company name if it's more recognizable (e.g., "Tesla" instead of "Blue Skies Solar II, LLC")
   - For utility bills: Use the main utility company name
   - For subscription services: Use the service name (e.g., "Netflix", "Spotify")
   - For bank statements: Use the bank name (e.g., "USAA", "Chase", "Wells Fargo")
   - Prioritize the brand the customer would recognize over legal billing entities
2. Document type (REQUIRED - use ONE word to classify):
   - "Invoice" - for bills, invoices requesting payment
   - "Statement" - for bank statements, credit card statements, account statements, insurance/annuity statements (if the document says "statement" on it, use this)
   - "Receipt" - for proof of payment, transaction receipts (NOT trade confirmations)
   - "Confirmation" - for trade confirmations, order confirmations, transaction confirmations
   - "Notice" - for notifications, letters, policy changes, account updates
   - "Letter" - for general correspondence
   - "Report" - for financial reports, summaries (only use if document explicitly says "report" and not "statement")
   - "Map" - for property maps, site plans, layout diagrams
   - IMPORTANT: If the document contains the word "statement" prominently, classify it as "Statement" not "Report"
   - Choose the most specific type that applies
3. Invoice/statement date
4. Invoice number (if available):
   - Look for "Invoice #", "Invoice No.", "Bill #", "Account #", "Reference #", etc.
   - Extract just the number/identifier part
   - For other types of invoices: leave this null if no clear invoice number
5. Patient or animal name (only for medical/veterinary invoices):
   - For medical invoices: Extract the patient's name if clearly identified
   - For veterinary invoices: Look carefully for animal/pet names in:
     * "Animal:" field or column
     * "Pet Name:" field
     * "Patient:" field (in vet contexts)
     * Table columns labeled "Animal", "Pet", or "Patient"
     * Any clearly identified animal/pet name in the document
   - For other types of invoices: leave this null
6. Account details (for bank statements, credit card statements, notices, and letters):
   - Account type: Look for the SPECIFIC account type category (not generic or product names):
     * Bank accounts: "Checking", "Savings", "Money Market", "CD", "IRA"
     * Credit cards: "Credit Card" (or specific tier like "Platinum", "Gold" if clearly labeled as such)
     * Insurance/Investment accounts: Use specific types like "Annuity", "VUL", "Life Insurance", "Brokerage", "401k" (NOT generic terms like "Investment Account" or "Account")
     * If only generic "Account" or "Investment Account" is found, leave this null
   - Last 4 digits: Extract the last 4 digits of the account/card number (look for patterns like "xxxx1234", "ending in 1234", "account ending in 1234", "2-51000" means last 4 is "1000")
   - Extract these even from notices/letters if they reference a specific account
   - IMPORTANT: If this is a portfolio summary or overview showing MULTIPLE accounts (2 or more different account numbers):
     * Set account_type to "Portfolio"
     * Set account_last_4 to null
   - For single account documents: extract the specific account type and last 4 digits
   - For non-financial account documents: leave these null

Return the response in this exact JSON format:
{
  "business_name": "Company Name Here",
  "document_type": "Type Here",
  "invoice_date": "YYYY-MM-DD",
  "invoice_number": "Number Here or null",
  "patient_animal_name": "Name Here or null",
  "account_type": "Account Type Here or null",
  "account_last_4": "Last 4 digits or null"
}

If you cannot find any piece of information, use null for that field."""

    try:
        response = call_grok_api(prompt, file_path, all_pages=all_pages)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.error(f"Failed to call Grok API: {e}")
        # Return fallback data instead of crashing
        return {
            'business_name': 'Unknown',
            'document_type': 'Document',
            'invoice_date': None,
            'invoice_number': None,
            'patient_animal_name': None,
            'account_type': None,
            'account_last_4': None
        }

    # Try to extract JSON from the response
    try:
        # Look for JSON in the response
        json_match = re.search(r'\{[^}]*"business_name"[^}]*\}', response, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            parsed_info = json.loads(json_str)
        else:
            # Fallback: try to parse the entire response as JSON
            parsed_info = json.loads(response)

        logger.info(f"Extracted info: {parsed_info}")

        # Log a warning if we have partial bank statement info (one field but not the other)
        # Exception: Portfolio statements don't need account_last_4
        has_account_type = parsed_info.get('account_type') is not None
        has_account_last_4 = parsed_info.get('account_last_4') is not None
        account_type_value = parsed_info.get('account_type')
        is_portfolio = account_type_value and account_type_value.lower() == 'portfolio'
        if has_account_type != has_account_last_4 and not is_portfolio:
            logger.warning(f"Partial bank statement data: account_type={parsed_info.get('account_type')}, account_last_4={parsed_info.get('account_last_4')}")

        # Validate that document_type was provided
        if not parsed_info.get('document_type'):
            logger.warning("Document type not provided by API, defaulting to 'Document'")
            parsed_info['document_type'] = 'Document'

        return parsed_info
    except json.JSONDecodeError as e:
        logger.error(f"Could not parse Grok response as JSON: {e}")
        logger.error(f"Response was: {response}")
        logger.warning("Using fallback values due to JSON parsing error")

        # Return fallback data structure instead of failing
        return {
            'business_name': 'Unknown',
            'document_type': 'Document',
            'invoice_date': None,
            'invoice_number': None,
            'patient_animal_name': None,
            'account_type': None,
            'account_last_4': None
        }

def clean_filename(text, limit_words=None):
    """Clean text to be safe for filename use and apply proper capitalization"""
    if not text:
        return "Unknown"

    # Remove or replace problematic characters
    cleaned = re.sub(r'[<>:"/\\|?*]', '', text)  # Remove illegal filename chars
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

    return cleaned if cleaned else "Unknown"

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

def rename_invoice(file_path, dry_run=False, move_to=None, all_pages=False):
    """Rename invoice file based on extracted information and optionally move to target directory"""
    logger = logging.getLogger(__name__)
    logger.info(f"Starting rename process for: {file_path}")

    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        print(f"Error: File '{file_path}' not found", file=sys.stderr)
        return False

    logger.debug(f"Processing: {file_path}")

    # Extract information from invoice
    info = extract_invoice_info(file_path, all_pages=all_pages)

    business_name = clean_filename(info.get('business_name'), limit_words=4)
    document_type = clean_filename(info.get('document_type')) if info.get('document_type') else 'Document'
    invoice_date = format_date(info.get('invoice_date'))
    invoice_number = info.get('invoice_number')
    if invoice_number:
        # If invoice_number looks like an account number (long digits), take last 4 digits
        invoice_number_cleaned = re.sub(r'[^\d]', '', invoice_number)  # Keep only digits
        if len(invoice_number_cleaned) >= 4:
            invoice_number = invoice_number_cleaned[-4:]  # Take last 4 digits
        else:
            invoice_number = invoice_number_cleaned
        invoice_number = clean_filename(invoice_number) if invoice_number else None
    else:
        invoice_number = None
    patient_animal_name = clean_filename(info.get('patient_animal_name')) if info.get('patient_animal_name') else None
    account_type = clean_filename(info.get('account_type')) if info.get('account_type') else None
    account_last_4 = info.get('account_last_4')
    if account_last_4:
        # Ensure only the last 4 digits are used
        account_last_4_cleaned = re.sub(r'[^\d]', '', account_last_4)  # Keep only digits
        if len(account_last_4_cleaned) >= 4:
            account_last_4 = account_last_4_cleaned[-4:]  # Take last 4 digits
        else:
            account_last_4 = account_last_4_cleaned  # If fewer than 4, use as-is
        account_last_4 = clean_filename(account_last_4) if account_last_4 else None
    else:
        account_last_4 = None

    logger.info(f"Extracted business name: {business_name}")
    logger.info(f"Extracted document type: {document_type}")
    logger.info(f"Extracted date: {info.get('invoice_date')} -> {invoice_date}")
    if invoice_number:
        logger.info(f"Extracted invoice number: {invoice_number}")
    if patient_animal_name:
        logger.info(f"Extracted patient/animal name: {patient_animal_name}")
    if account_type:
        logger.info(f"Extracted account type: {account_type}")
    if account_last_4:
        logger.info(f"Extracted account last 4: {account_last_4}")

    # Get file extension
    file_dir = os.path.dirname(file_path)
    file_ext = os.path.splitext(file_path)[1]

    # Create new filename with document type, patient/animal name and invoice number if available
    # Format: Business Name [Account-Type] Document-Type [Last4] [- Patient/Animal] [Invoice#] Date
    # For bank-related documents, insert account type before document type
    if account_type:
        if account_type.lower() == 'portfolio' or not account_last_4:
            # Portfolio statement or account type without last 4 digits
            filename_parts = [business_name, account_type, document_type]
        else:
            # Single account with type and last 4 digits
            filename_parts = [business_name, account_type, document_type, account_last_4]
    else:
        filename_parts = [business_name, document_type]

    if patient_animal_name:
        filename_parts.append(f"- {patient_animal_name}")

    # Only include invoice number if we don't have account information
    # (statements typically use account numbers instead of invoice numbers)
    if invoice_number and not account_type:
        filename_parts.append(invoice_number)

    # Only include date if it's valid (not 00000000)
    if invoice_date and invoice_date != "00000000":
        filename_parts.append(invoice_date)

    new_filename = f"{' '.join(filename_parts)}{file_ext}"

    # Determine target directory
    target_dir = move_to if move_to else file_dir
    if move_to and not os.path.exists(move_to):
        if dry_run:
            logger.info(f"Target directory does not exist (would be created): {move_to}")
        else:
            os.makedirs(move_to, exist_ok=True)
            logger.info(f"Created target directory: {move_to}")

    # Check if target file exists and make name unique if needed
    base_new_file_path = os.path.join(target_dir, new_filename)
    new_file_path = base_new_file_path

    # If target exists and it's not the same file, add numeric suffix before date
    counter = 2
    while os.path.exists(new_file_path) and os.path.abspath(new_file_path) != os.path.abspath(file_path):
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

        # Safety check to avoid infinite loop
        if counter > 100:
            logger.error("Too many duplicate files, giving up")
            print(f"Error: Too many files with similar names exist", file=sys.stderr)
            return False

    new_filename = os.path.basename(new_file_path)
    logger.info(f"New filename: {new_filename}")

    if dry_run:
        logger.info("Dry run mode - file not actually renamed")
        if move_to:
            print(f"Would rename {os.path.basename(file_path)} to {new_filename} and move to {os.path.basename(target_dir)}")
        else:
            print(f"Would rename {os.path.basename(file_path)} to {new_filename}")
        return True

    # Check if target file already exists
    if os.path.exists(new_file_path):
        # Do case-sensitive filename comparison
        current_filename = os.path.basename(file_path)
        target_filename = os.path.basename(new_file_path)

        if current_filename == target_filename:
            logger.info("File already has the correct name")
            if move_to and target_dir != file_dir:
                # File has correct name but needs to be moved
                try:
                    if not dry_run:
                        shutil.move(file_path, new_file_path)
                        print(f"Moved {target_filename} to {os.path.basename(target_dir)}")
                    else:
                        print(f"Would move {target_filename} to {os.path.basename(target_dir)}")
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
            # On case-insensitive filesystems, we need to do a two-step rename
            logger.info("Performing case-only rename")
            try:
                # Create unique temporary name based on original filename and timestamp
                file_base = os.path.splitext(file_path)[0]
                file_ext = os.path.splitext(file_path)[1]

                # Create a hash from the original and target paths for uniqueness
                unique_hash = hashlib.md5(f"{file_path}->{new_file_path}".encode()).hexdigest()[:8]
                temp_path = f"{file_base}.tmp_{unique_hash}{file_ext}"

                logger.debug(f"Using temporary path: {temp_path}")

                # Step 1: Rename to temporary name
                os.rename(file_path, temp_path)
                # Step 2: Rename to final name
                os.rename(temp_path, new_file_path)
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
        else:
            logger.error(f"Target file already exists: {new_file_path}")
            print(f"Error: Target file '{new_file_path}' already exists", file=sys.stderr)
            return False

    # Rename/move the file
    try:
        if move_to:
            # Use shutil.move for cross-directory moves
            shutil.move(file_path, new_file_path)
            logger.info(f"Successfully moved and renamed: {file_path} -> {new_file_path}")
            print(f"Renamed {os.path.basename(file_path)} to {os.path.basename(new_file_path)} and moved to {os.path.basename(target_dir)}")
        else:
            os.rename(file_path, new_file_path)
            logger.info(f"Successfully renamed: {file_path} -> {new_file_path}")
            print(f"Renamed {os.path.basename(file_path)} to {os.path.basename(new_file_path)}")
        return True
    except OSError as e:
        logger.error(f"Error renaming/moving file: {e}")
        print(f"Error renaming/moving file: {e}", file=sys.stderr)
        return False

def main():
    # Setup logging first
    logger = setup_logging()
    logger.info("=== Invoice Renamer Started ===")

    parser = argparse.ArgumentParser(description="Rename invoice files based on business name and date")
    parser.add_argument("file", help="Invoice file to rename")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without actually renaming")
    parser.add_argument("--move-to", help="Target directory to move the renamed file to")
    parser.add_argument("--all-pages", action="store_true", help="Process all pages of PDF (default: first page only)")

    try:
        args = parser.parse_args()
        logger.info(f"Arguments: file={args.file}, dry_run={args.dry_run}, move_to={args.move_to}, all_pages={args.all_pages}")

        success = rename_invoice(args.file, args.dry_run, args.move_to, args.all_pages)
        logger.info(f"=== Invoice Renamer Finished - Success: {success} ===")

        # Only exit with error code if it's a critical failure, not just processing errors
        if success:
            sys.exit(0)
        else:
            # This might be a recoverable error (like file not found, duplicate name), so don't use error code
            sys.exit(0)
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
