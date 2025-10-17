import pytest
import sys
from unittest.mock import patch, MagicMock

import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from grok import main


class TestMain:

    @patch('grok.call_grok_api')
    @patch('sys.argv', ['grok.py', 'Test prompt'])
    def test_main_basic_args(self, mock_call_api, capsys):
        """Test main function with basic arguments."""
        mock_call_api.return_value = "Test response"

        main()

        mock_call_api.assert_called_once_with("Test prompt", "grok-4-fast-reasoning", None, False)
        captured = capsys.readouterr()
        assert captured.out == "Test response\n"

    @patch('grok.call_grok_api')
    @patch('sys.argv', ['grok.py', '--model', 'test-model', 'Test prompt with spaces'])
    def test_main_custom_model(self, mock_call_api, capsys):
        """Test main function with custom model."""
        mock_call_api.return_value = "Custom model response"

        main()

        mock_call_api.assert_called_once_with(
            "Test prompt with spaces",
            "test-model",
            None,
            False
        )

    @patch('grok.call_grok_api')
    @patch('sys.argv', ['grok.py', '--file', 'test.pdf', '--all-pages', 'Analyze this PDF'])
    def test_main_with_file_all_pages(self, mock_call_api, capsys):
        """Test main function with file and all-pages flag."""
        mock_call_api.return_value = "PDF analysis complete"

        main()

        mock_call_api.assert_called_once_with(
            "Analyze this PDF",
            "grok-4-fast-reasoning",
            "test.pdf",
            True
        )

    def test_main_no_args(self, capsys):
        """Test main function with no arguments shows usage."""
        with patch('sys.argv', ['grok.py']):
            with pytest.raises(SystemExit) as excinfo:
                main()

            assert excinfo.value.code == 2  # argparse error code

    @patch('grok.call_grok_api')
    @patch('sys.argv', ['grok.py', '--file', '/nonexistent/file.pdf', 'Test'])
    def test_main_file_not_found(self, mock_call_api, capsys):
        """Test main function when specified file doesn't exist."""
        mock_call_api.side_effect = SystemExit(1)

        with pytest.raises(SystemExit):
            main()

    @patch('sys.argv', ['grok.py', '--help'])
    def test_main_help_flag(self, capsys):
        """Test main function help output."""
        with pytest.raises(SystemExit) as excinfo:
            main()

        # Help should exit with code 0
        assert excinfo.value.code == 0

        captured = capsys.readouterr()
        assert "Call Grok API with a prompt" in captured.out

    @patch('grok.call_grok_api')
    @patch('sys.argv', ['grok.py', '--file', 'image.jpg', '--model', 'grok-2-vision-1212',
                        'Describe this image'])
    def test_main_vision_model(self, mock_call_api, capsys):
        """Test main function with vision model explicitly set."""
        mock_call_api.return_value = "Image description"

        main()

        mock_call_api.assert_called_once_with(
            "Describe this image",
            "grok-2-vision-1212",
            "image.jpg",
            False
        )

    @patch('grok.call_grok_api')
    @patch('sys.argv', ['grok.py', 'Test', '--model', 'nonexistent-model'])
    def test_main_invalid_model(self, mock_call_api, capsys):
        """Test main function with invalid model (handled by API)."""
        mock_call_api.return_value = "Response from any model"

        main()

        mock_call_api.assert_called_once_with(
            "Test",
            "nonexistent-model",
            None,
            False
        )

    @patch('grok.call_grok_api')
    @patch('sys.argv', ['grok.py', 'Multi word prompt with --file flag', '--file', 'doc.txt'])
    def test_main_multi_word_prompt_with_file(self, mock_call_api, capsys):
        """Test main function parsing multi-word prompts with file flag."""
        mock_call_api.return_value = "Document analyzed"

        main()

        mock_call_api.assert_called_once_with(
            "Multi word prompt with --file flag",
            "grok-4-fast-reasoning",
            "doc.txt",
            False
        )

    @patch('sys.argv', ['grok.py', '--file', 'test.pdf', '--model'])
    def test_main_missing_model_value(self, capsys):
        """Test main function error when model flag has no value."""
        with pytest.raises(SystemExit) as excinfo:
            main()

        # argparse error for missing argument value
        assert excinfo.value.code == 2

    @patch('grok.call_grok_api')
    @patch('sys.argv', ['grok.py', '', '--file', 'empty.txt'])
    def test_main_empty_prompt(self, mock_call_api, capsys):
        """Test main function with empty prompt."""
        mock_call_api.return_value = "Response to empty prompt"

        main()

        mock_call_api.assert_called_once_with(
            "",
            "grok-4-fast-reasoning",
            "empty.txt",
            False
        )
