import pytest
import os
import sys
from unittest.mock import patch

# Import the functions to test from invoice_renamer.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from invoice_renamer import rename_invoice, main


# ==================== INTEGRATION TESTS ====================

class TestRenameInvoiceBasic:
    """Test basic rename_invoice functionality."""

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_basic_invoice(self, mock_extract, tmp_path, sample_invoice_info):
        """Test basic invoice renaming."""
        # Create test file
        test_file = tmp_path / "original.pdf"
        test_file.write_text("test content")

        mock_extract.return_value = sample_invoice_info

        result = rename_invoice(str(test_file))

        assert result is True
        # Note: "Company" is a trailing word that gets removed by clean_filename
        # Expected: "Test Invoice 1234 20240115.pdf"
        expected_name = "Test Invoice 1234 20240115.pdf"
        assert (tmp_path / expected_name).exists()
        assert not test_file.exists()

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_with_statement_and_account(self, mock_extract, tmp_path, sample_statement_info):
        """Test statement renaming with account information."""
        test_file = tmp_path / "statement.pdf"
        test_file.write_text("test content")

        mock_extract.return_value = sample_statement_info

        result = rename_invoice(str(test_file))

        assert result is True
        # "Credit Card" is abbreviated to "CC" by clean_filename
        # Expected: "Chase Bank CC Statement 5678 20240115.pdf"
        expected_name = "Chase Bank CC Statement 5678 20240115.pdf"
        assert (tmp_path / expected_name).exists()

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_with_patient_name(self, mock_extract, tmp_path, sample_vet_invoice_info):
        """Test veterinary invoice with patient name."""
        test_file = tmp_path / "vet.pdf"
        test_file.write_text("test content")

        mock_extract.return_value = sample_vet_invoice_info

        result = rename_invoice(str(test_file))

        assert result is True
        # Expected: "Veterinary Clinic Invoice - Fluffy 9876 20240115.pdf"
        expected_name = "Veterinary Clinic Invoice - Fluffy 9876 20240115.pdf"
        assert (tmp_path / expected_name).exists()

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_without_date(self, mock_extract, tmp_path):
        """Test renaming when no date available."""
        test_file = tmp_path / "nodoc.pdf"
        test_file.write_text("test content")

        info = {
            'business_name': 'Company',
            'document_type': 'Invoice',
            'invoice_date': None,
            'invoice_number': '1234',
            'patient_animal_name': None,
            'account_type': None,
            'account_last_4': None
        }
        mock_extract.return_value = info

        result = rename_invoice(str(test_file))

        assert result is True
        # Expected: "Company Invoice 1234.pdf" (no date)
        expected_name = "Company Invoice 1234.pdf"
        assert (tmp_path / expected_name).exists()

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_portfolio_statement(self, mock_extract, tmp_path):
        """Test portfolio statement (account_last_4=None means account info not included)."""
        test_file = tmp_path / "portfolio.pdf"
        test_file.write_text("test content")

        info = {
            'business_name': 'Vanguard',
            'document_type': 'Statement',
            'invoice_date': '2024-03-31',
            'invoice_number': None,
            'patient_animal_name': None,
            'account_type': 'Portfolio',
            'account_last_4': None  # None means should_include_account is False
        }
        mock_extract.return_value = info

        result = rename_invoice(str(test_file))

        assert result is True
        # Since account_last_4 is None, account info is not included
        # Expected: "Vanguard Statement 20240331.pdf"
        expected_name = "Vanguard Statement 20240331.pdf"
        assert (tmp_path / expected_name).exists()

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_with_document_title(self, mock_extract, tmp_path):
        """Test that document_title is used in filename instead of generic document type."""
        test_file = tmp_path / "policy.pdf"
        test_file.write_text("test content")

        info = {
            'business_name': 'Acme Insurance',
            'document_type': 'Notice',
            'document_title': 'Automobile Policy Packet',
            'invoice_date': '2024-03-15',
            'invoice_number': None,
            'patient_animal_name': None,
            'account_type': None,
            'account_last_4': None
        }
        mock_extract.return_value = info

        result = rename_invoice(str(test_file))

        assert result is True
        expected_name = "Acme Insurance Automobile Policy Packet 20240315.pdf"
        assert (tmp_path / expected_name).exists()

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_dry_run_mode(self, mock_extract, tmp_path, sample_invoice_info, capsys):
        """Test dry run mode doesn't actually rename."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        mock_extract.return_value = sample_invoice_info

        result = rename_invoice(str(test_file), dry_run=True)

        assert result is True
        assert test_file.exists()  # Original still exists
        captured = capsys.readouterr()
        assert "Would rename" in captured.out


class TestRenameInvoiceDuplicateHandling:
    """Test duplicate filename handling and counter insertion."""

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_duplicate_adds_counter(self, mock_extract, tmp_path, sample_invoice_info):
        """Test that duplicate filenames get counter inserted."""
        # Create test file
        test_file = tmp_path / "original.pdf"
        test_file.write_text("test content")

        # Create existing file with target name (note: "Company" removed by clean_filename)
        existing = tmp_path / "Test Invoice 1234 20240115.pdf"
        existing.write_text("existing content")

        mock_extract.return_value = sample_invoice_info

        result = rename_invoice(str(test_file))

        assert result is True
        # Should add counter before date: "Test Invoice 1234 2 20240115.pdf"
        expected_name = "Test Invoice 1234 2 20240115.pdf"
        assert (tmp_path / expected_name).exists()
        assert existing.exists()  # Original unchanged

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_multiple_duplicates(self, mock_extract, tmp_path, sample_invoice_info):
        """Test handling of multiple duplicate files."""
        test_file = tmp_path / "original.pdf"
        test_file.write_text("test content")

        # Create multiple existing files (note: "Company" removed)
        (tmp_path / "Test Invoice 1234 20240115.pdf").write_text("v1")
        (tmp_path / "Test Invoice 1234 2 20240115.pdf").write_text("v2")
        (tmp_path / "Test Invoice 1234 3 20240115.pdf").write_text("v3")

        mock_extract.return_value = sample_invoice_info

        result = rename_invoice(str(test_file))

        assert result is True
        expected_name = "Test Invoice 1234 4 20240115.pdf"
        assert (tmp_path / expected_name).exists()

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_duplicate_without_date(self, mock_extract, tmp_path):
        """Test duplicate handling when no date in filename."""
        test_file = tmp_path / "original.pdf"
        test_file.write_text("test content")

        existing = tmp_path / "Company Invoice 1234.pdf"
        existing.write_text("existing")

        info = {
            'business_name': 'Company',
            'document_type': 'Invoice',
            'invoice_date': None,
            'invoice_number': '1234',
            'patient_animal_name': None,
            'account_type': None,
            'account_last_4': None
        }
        mock_extract.return_value = info

        result = rename_invoice(str(test_file))

        assert result is True
        # Counter appended at end: "Company Invoice 1234 2.pdf"
        expected_name = "Company Invoice 1234 2.pdf"
        assert (tmp_path / expected_name).exists()

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_too_many_duplicates(self, mock_extract, tmp_path, sample_invoice_info, capsys):
        """Test that too many duplicates causes failure."""
        test_file = tmp_path / "original.pdf"
        test_file.write_text("test content")

        mock_extract.return_value = sample_invoice_info

        # Mock os.path.exists to always return True (simulating infinite duplicates)
        with patch('os.path.exists') as mock_exists:
            def exists_side_effect(path):
                # Original file exists
                if path == str(test_file):
                    return True
                # All target paths exist (except when abspath comparison)
                if 'Test Invoice' in path:
                    return True
                return False

            mock_exists.side_effect = exists_side_effect

            # Need to also mock abspath to make the file path comparison work
            with patch('os.path.abspath') as mock_abspath:
                mock_abspath.side_effect = lambda p: f"/abs{p}"

                result = rename_invoice(str(test_file))

                assert result is False
                captured = capsys.readouterr()
                assert "Error: Too many files with similar names exist" in captured.err


class TestRenameInvoiceCaseOnlyRename:
    """Test case-only rename scenarios."""

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_case_only_change(self, mock_extract, tmp_path, capsys):
        """Test case-only rename on case-insensitive filesystem."""
        # On macOS (case-insensitive by default), "simple invoice" and "Simple Invoice"
        # appear to be the same file, so the code detects a collision and adds a counter
        test_file = tmp_path / "simple invoice 20240115.pdf"
        test_file.write_text("test content")

        info = {
            'business_name': 'Simple Company',  # Company removed, becomes "Simple"
            'document_type': 'Invoice',
            'invoice_date': '2024-01-15',
            'invoice_number': None,
            'patient_animal_name': None,
            'account_type': None,
            'account_last_4': None
        }
        mock_extract.return_value = info

        result = rename_invoice(str(test_file))

        assert result is True
        # On case-insensitive filesystems, file is detected as same and gets counter
        captured = capsys.readouterr()
        # The rename should happen, but might add a counter due to case-insensitivity
        assert "Renamed" in captured.out or "already correctly named" in captured.out

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_already_correct_name(self, mock_extract, tmp_path, capsys):
        """Test file that already has correct name."""
        test_file = tmp_path / "Test Invoice 20240115.pdf"
        test_file.write_text("test content")

        info = {
            'business_name': 'Test Company',  # Company removed, becomes "Test"
            'document_type': 'Invoice',
            'invoice_date': '2024-01-15',
            'invoice_number': None,
            'patient_animal_name': None,
            'account_type': None,
            'account_last_4': None
        }
        mock_extract.return_value = info

        result = rename_invoice(str(test_file))

        assert result is True
        captured = capsys.readouterr()
        assert "already correctly named" in captured.out


class TestRenameInvoiceMove:
    """Test move-to-directory functionality."""

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_move_to_existing_dir(self, mock_extract, tmp_path, sample_invoice_info):
        """Test moving to existing directory."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        test_file = source_dir / "test.pdf"
        test_file.write_text("test content")

        mock_extract.return_value = sample_invoice_info

        result = rename_invoice(str(test_file), move_to=str(target_dir))

        assert result is True
        expected = target_dir / "Test Invoice 1234 20240115.pdf"
        assert expected.exists()
        assert not test_file.exists()

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_move_to_nonexistent_dir(self, mock_extract, tmp_path, sample_invoice_info):
        """Test moving to nonexistent directory creates it."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        target_dir = tmp_path / "target"  # Doesn't exist yet

        test_file = source_dir / "test.pdf"
        test_file.write_text("test content")

        mock_extract.return_value = sample_invoice_info

        result = rename_invoice(str(test_file), move_to=str(target_dir))

        assert result is True
        assert target_dir.exists()
        expected = target_dir / "Test Invoice 1234 20240115.pdf"
        assert expected.exists()

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_move_to_nonexistent_dir_dry_run(self, mock_extract, tmp_path, sample_invoice_info, capsys):
        """Test dry run with nonexistent target directory."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        target_dir = tmp_path / "target"

        test_file = source_dir / "test.pdf"
        test_file.write_text("test content")

        mock_extract.return_value = sample_invoice_info

        result = rename_invoice(str(test_file), dry_run=True, move_to=str(target_dir))

        assert result is True
        assert not target_dir.exists()  # Not created in dry run
        assert test_file.exists()  # Not moved


class TestRenameInvoiceErrorHandling:
    """Test error handling in rename_invoice."""

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_file_not_found(self, mock_extract, capsys):
        """Test handling of nonexistent file."""
        result = rename_invoice("/nonexistent/file.pdf")

        assert result is False
        captured = capsys.readouterr()
        assert "Error: File" in captured.err
        assert "not found" in captured.err

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_os_error_during_rename(self, mock_extract, tmp_path, sample_invoice_info):
        """Test handling of OS errors during rename."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        mock_extract.return_value = sample_invoice_info

        with patch('invoice_renamer.shutil.move', side_effect=OSError("Permission denied")):
            result = rename_invoice(str(test_file))

            assert result is False

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_file_exists_race_condition(self, mock_extract, tmp_path, sample_invoice_info, capsys):
        """Test handling of race condition where file appears after check."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        mock_extract.return_value = sample_invoice_info

        with patch('invoice_renamer.shutil.move', side_effect=FileExistsError("File exists")):
            result = rename_invoice(str(test_file))

            assert result is False
            captured = capsys.readouterr()
            assert "already exists" in captured.err

    @patch('invoice_renamer.extract_invoice_info')
    def test_rename_invoice_shutil_move_error(self, mock_extract, tmp_path, sample_invoice_info):
        """Test handling of errors during shutil.move."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        test_file = source_dir / "test.pdf"
        test_file.write_text("test content")

        mock_extract.return_value = sample_invoice_info

        with patch('shutil.move', side_effect=OSError("Move failed")):
            result = rename_invoice(str(test_file), move_to=str(target_dir))

            assert result is False


# ==================== MAIN FUNCTION TESTS ====================

class TestMainEdgeCases:
    """Test edge cases for main function."""

    @patch('invoice_renamer.setup_logging')
    @patch('invoice_renamer.rename_invoice')
    @patch('sys.argv', ['invoice_renamer.py', '--dry-run', '--move-to', '/target', '--all-pages', '/path/to/file.pdf'])
    def test_main_all_flags_combined(self, mock_rename, mock_setup_logging):
        """Test main with all flags combined."""
        mock_rename.return_value = True

        with pytest.raises(SystemExit) as excinfo:
            main()

        assert excinfo.value.code == 0
        mock_rename.assert_called_once_with('/path/to/file.pdf', True, '/target', True)

    @patch('invoice_renamer.setup_logging')
    @patch('invoice_renamer.rename_invoice')
    @patch('sys.argv', ['invoice_renamer.py', 'file with spaces.pdf'])
    def test_main_filename_with_spaces(self, mock_rename, mock_setup_logging):
        """Test main with filename containing spaces."""
        mock_rename.return_value = True

        with pytest.raises(SystemExit) as excinfo:
            main()

        assert excinfo.value.code == 0
        mock_rename.assert_called_once_with('file with spaces.pdf', False, None, False)

    @patch('invoice_renamer.setup_logging')
    @patch('sys.argv', ['invoice_renamer.py', '--invalid-flag', 'file.pdf'])
    def test_main_invalid_flag(self, mock_setup_logging):
        """Test main with invalid flag."""
        with pytest.raises(SystemExit) as excinfo:
            main()

        assert excinfo.value.code == 2  # argparse error
