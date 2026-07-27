import os
import sys
from unittest.mock import patch

# Import the functions to test from invoice_renamer.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from invoice_renamer import rename_invoice


# ==================== VALIDATION TESTS ====================

class TestRenameInvoiceDocumentTypeSanitization:
    """Test document type-specific sanitization rules."""

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_receipt_removes_invoice_number(self, mock_extract, tmp_path):
        """Test that receipts don't include invoice numbers."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        info = {
            'business_name': 'Store Name',
            'document_type': 'Receipt',
            'invoice_date': '2024-01-15',
            'invoice_number': '9999',  # Should be removed
            'patient_animal_name': None,
            'account_type': None,
            'account_last_4': None
        }
        mock_extract.return_value = info

        result = rename_invoice(str(test_file))

        assert result is True
        # Invoice number should not appear
        expected = tmp_path / "Store Name Receipt 20240115.pdf"
        assert expected.exists()

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_confirmation_removes_invoice_number(self, mock_extract, tmp_path):
        """Test that confirmations don't include invoice numbers."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        info = {
            'business_name': 'Brokerage',
            'document_type': 'Confirmation',
            'invoice_date': '2024-01-15',
            'invoice_number': '8888',  # Should be removed
            'patient_animal_name': None,
            'account_type': None,
            'account_last_4': None
        }
        mock_extract.return_value = info

        result = rename_invoice(str(test_file))

        assert result is True
        expected = tmp_path / "Brokerage Confirmation 20240115.pdf"
        assert expected.exists()

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_invoice_type_removes_account_info(self, mock_extract, tmp_path):
        """Test that invoices don't include account info."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        info = {
            'business_name': 'Company',
            'document_type': 'Invoice',
            'invoice_date': '2024-01-15',
            'invoice_number': '1234',
            'patient_animal_name': None,
            'account_type': 'Credit Card',  # Should be removed
            'account_last_4': '5678'  # Should be removed
        }
        mock_extract.return_value = info

        result = rename_invoice(str(test_file))

        assert result is True
        # Account info should not appear
        expected = tmp_path / "Company Invoice 1234 20240115.pdf"
        assert expected.exists()

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_statement_keeps_account_info(self, mock_extract, tmp_path):
        """Test that statements preserve account info."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        info = {
            'business_name': 'Bank',
            'document_type': 'Statement',
            'invoice_date': '2024-01-15',
            'invoice_number': None,
            'patient_animal_name': None,
            'account_type': 'Checking',
            'account_last_4': '1234'
        }
        mock_extract.return_value = info

        result = rename_invoice(str(test_file))

        assert result is True
        expected = tmp_path / "Bank Checking Statement 1234 20240115.pdf"
        assert expected.exists()

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_report_keeps_account_info(self, mock_extract, tmp_path):
        """Test that reports preserve account info (e.g. Fidelity account reports)."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        info = {
            'business_name': 'Fidelity',
            'document_type': 'Report',
            'invoice_date': '2026-01-31',
            'invoice_number': None,
            'patient_animal_name': None,
            'account_type': 'Rollover IRA',
            'account_last_4': '9876'
        }
        mock_extract.return_value = info

        result = rename_invoice(str(test_file))

        assert result is True
        expected = tmp_path / "Fidelity Rollover IRA Report 9876 20260131.pdf"
        assert expected.exists()


class TestRenameInvoiceAccountNumberValidation:
    """Test account number validation and cleanup."""

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_valid_4_digit_account(self, mock_extract, tmp_path):
        """Test valid 4-digit account number."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        info = {
            'business_name': 'Bank',
            'document_type': 'Statement',
            'invoice_date': '2024-01-15',
            'invoice_number': None,
            'patient_animal_name': None,
            'account_type': 'Savings',
            'account_last_4': '1234'
        }
        mock_extract.return_value = info

        result = rename_invoice(str(test_file))

        assert result is True
        expected = tmp_path / "Bank Savings Statement 1234 20240115.pdf"
        assert expected.exists()

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_long_account_truncates_to_4(self, mock_extract, tmp_path):
        """Test long account number gets truncated to last 4."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        info = {
            'business_name': 'Bank',
            'document_type': 'Statement',
            'invoice_date': '2024-01-15',
            'invoice_number': None,
            'patient_animal_name': None,
            'account_type': 'Checking',
            'account_last_4': '1234567890'  # Long number
        }
        mock_extract.return_value = info

        result = rename_invoice(str(test_file))

        assert result is True
        # Should take last 4: 7890
        expected = tmp_path / "Bank Checking Statement 7890 20240115.pdf"
        assert expected.exists()

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_short_account_cleared(self, mock_extract, tmp_path):
        """Test short account number (< 4 digits) gets cleared."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        info = {
            'business_name': 'Bank',
            'document_type': 'Statement',
            'invoice_date': '2024-01-15',
            'invoice_number': None,
            'patient_animal_name': None,
            'account_type': 'Checking',
            'account_last_4': '12'  # Too short
        }
        mock_extract.return_value = info

        result = rename_invoice(str(test_file))

        assert result is True
        # Account info should be cleared
        expected = tmp_path / "Bank Statement 20240115.pdf"
        assert expected.exists()

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_account_with_non_digits(self, mock_extract, tmp_path):
        """Test account number with non-digit characters."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        info = {
            'business_name': 'Bank',
            'document_type': 'Statement',
            'invoice_date': '2024-01-15',
            'invoice_number': None,
            'patient_animal_name': None,
            'account_type': 'Savings',
            'account_last_4': 'xx-1234'  # Has non-digits
        }
        mock_extract.return_value = info

        result = rename_invoice(str(test_file))

        assert result is True
        # Should extract just digits: 1234
        expected = tmp_path / "Bank Savings Statement 1234 20240115.pdf"
        assert expected.exists()

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_alphanumeric_account_id(self, mock_extract, tmp_path):
        """Test short alphanumeric account identifiers are kept."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        info = {
            'business_name': 'Bank',
            'document_type': 'Statement',
            'invoice_date': '2024-01-15',
            'invoice_number': None,
            'patient_animal_name': None,
            'account_type': 'Brokerage',
            'account_last_4': 'A12B'
        }
        mock_extract.return_value = info

        result = rename_invoice(str(test_file))

        assert result is True
        expected = tmp_path / "Bank Brokerage Statement A12B 20240115.pdf"
        assert expected.exists()

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_alphanumeric_invoice_number(self, mock_extract, tmp_path):
        """Test short alphanumeric invoice numbers are included."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        info = {
            'business_name': 'Vendor',
            'document_type': 'Invoice',
            'invoice_date': '2024-01-15',
            'invoice_number': 'ACS-12B4',
            'patient_animal_name': None,
            'account_type': None,
            'account_last_4': None
        }
        mock_extract.return_value = info

        result = rename_invoice(str(test_file))

        assert result is True
        expected = tmp_path / "Vendor Invoice ACS12B4 20240115.pdf"
        assert expected.exists()

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_amex_abbreviation(self, mock_extract, tmp_path):
        """Test American Express is abbreviated to Amex in filenames."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        info = {
            'business_name': 'American Express',
            'document_type': 'Statement',
            'invoice_date': '2024-01-15',
            'invoice_number': None,
            'patient_animal_name': None,
            'account_type': 'Credit Card',
            'account_last_4': '1000'
        }
        mock_extract.return_value = info

        result = rename_invoice(str(test_file))

        assert result is True
        expected = tmp_path / "Amex CC Statement 1000 20240115.pdf"
        assert expected.exists()
