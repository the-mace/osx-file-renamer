import pytest
import subprocess
from unittest.mock import patch, MagicMock

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from grok import call_grok_api, load_env_file


class TestErrorHandling:

    @patch('grok.os.getenv', return_value=None)
    def test_call_grok_api_no_api_key(self, mock_getenv):
        """Test API call failure when no API key is available."""
        with pytest.raises(SystemExit) as excinfo:
            call_grok_api("Test prompt")

        assert excinfo.value.code == 1

    @patch('grok.load_env_file')
    @patch('grok.os.getenv', return_value=None)
    def test_call_grok_api_no_api_key_after_env_file(self, mock_getenv, mock_load_env):
        """Test API call failure when env file doesn't contain API key."""
        with pytest.raises(SystemExit) as excinfo:
            call_grok_api("Test prompt")

        assert excinfo.value.code == 1
        mock_load_env.assert_called_once()

    @patch('urllib.request.urlopen')
    def test_call_grok_api_network_timeout(self, mock_urlopen):
        """Test handling of network timeouts."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Network timeout")

        with pytest.raises(SystemExit) as excinfo:
            call_grok_api("Test")

        assert excinfo.value.code == 1

    @patch('urllib.request.urlopen')
    def test_call_grok_api_http_error(self, mock_urlopen):
        """Test handling of HTTP errors from API."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.x.ai/v1/chat/completions",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=MagicMock()
        )

        with pytest.raises(SystemExit) as excinfo:
            call_grok_api("Test")

        assert excinfo.value.code == 1

    @patch('urllib.request.urlopen')
    def test_call_grok_api_server_error_500(self, mock_urlopen):
        """Test handling of server errors."""
        import urllib.error

        # Mock HTTPError with body content
        error_body = MagicMock()
        error_body.read.return_value = b'{"error": "Internal server error"}'
        error_body.fp = error_body

        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.x.ai/v1/chat/completions",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=error_body
        )

        with pytest.raises(SystemExit) as excinfo:
            call_grok_api("Test")

        assert excinfo.value.code == 1

    @patch('urllib.request.urlopen')
    def test_call_grok_api_rate_limit_error(self, mock_urlopen):
        """Test handling of rate limit errors."""
        import urllib.error

        error_body = MagicMock()
        error_body.read.return_value = b'{"error": "Rate limit exceeded"}'
        error_body.fp = error_body

        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.x.ai/v1/chat/completions",
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=error_body
        )

        with pytest.raises(SystemExit) as excinfo:
            call_grok_api("Test")

        assert excinfo.value.code == 1

    @patch('urllib.request.urlopen')
    def test_call_grok_api_invalid_json_response(self, mock_urlopen):
        """Test handling of non-JSON responses."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'<html>Not JSON</html>'
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        with pytest.raises(SystemExit) as excinfo:
            call_grok_api("Test")

        assert excinfo.value.code == 1

    @patch('urllib.request.urlopen')
    def test_call_grok_api_empty_response(self, mock_urlopen):
        """Test handling of empty responses."""
        mock_response = MagicMock()
        mock_response.read.return_value = b''
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        with pytest.raises(SystemExit) as excinfo:
            call_grok_api("Test")

        assert excinfo.value.code == 1

    @patch('urllib.request.urlopen')
    def test_call_grok_api_malformed_json_response(self, mock_urlopen):
        """Test handling of malformed JSON responses."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"choices": [{"message": }}}'  # Malformed JSON
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        with pytest.raises(SystemExit) as excinfo:
            call_grok_api("Test")

        assert excinfo.value.code == 1

    @patch('urllib.request.urlopen')
    def test_call_grok_api_missing_choices_key(self, mock_urlopen):
        """Test handling of responses without choices key."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"response": "missing choices"}'
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        with pytest.raises(SystemExit) as excinfo:
            call_grok_api("Test")

        assert excinfo.value.code == 1

    @patch('urllib.request.urlopen')
    def test_call_grok_api_empty_choices_array(self, mock_urlopen):
        """Test handling of responses with empty choices array."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"choices": []}'
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        with pytest.raises(SystemExit) as excinfo:
            call_grok_api("Test")

        assert excinfo.value.code == 1

    @patch('urllib.request.urlopen')
    def test_call_grok_api_missing_message_key(self, mock_urlopen):
        """Test handling of choices without message key."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"choices": [{"content": "missing message"}]}'
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        with pytest.raises(SystemExit) as excinfo:
            call_grok_api("Test")

        assert excinfo.value.code == 1

    @patch('urllib.request.urlopen')
    def test_call_grok_api_missing_content_key(self, mock_urlopen):
        """Test handling of messages without content key."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"choices": [{"message": {"other": "data"}}]}'
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        with pytest.raises(SystemExit) as excinfo:
            call_grok_api("Test")

        assert excinfo.value.code == 1

    @patch('grok.read_file_content')
    @patch('grok.os.getenv', return_value="test_key")
    @patch('urllib.request.urlopen')
    def test_call_grok_api_file_processing_error(self, mock_urlopen, mock_getenv, mock_read_file):
        """Test handling of file processing errors."""
        mock_read_file.side_effect = SystemExit(1)

        with pytest.raises(SystemExit) as excinfo:
            call_grok_api("Test", file_path="bad_file.xyz")

        assert excinfo.value.code == 1


class TestEnvFileErrorHandling:

    def test_load_env_file_with_read_error(self, tmp_path):
        """Test handling of file read errors."""
        env_file = tmp_path / ".env"
        env_file.write_text("GROK_API_KEY=test_key")

        with patch('os.path.expanduser', return_value=str(env_file)):
            with patch('builtins.open', side_effect=IOError("Permission denied")):
                # Should not crash, just log warning
                load_env_file()

    def test_load_env_file_with_invalid_format(self, tmp_path):
        """Test handling of malformed env file lines."""
        env_file = tmp_path / ".env"
        env_file.write_text('INVALID_LINE_WITHOUT_EQUALS\nGROK_API_KEY=test\nEMPTY_VALUE=\n')

        with patch('os.path.expanduser', return_value=str(env_file)):
            # Should handle gracefully
            load_env_file()

    def test_load_env_file_with_unicode_error(self, tmp_path):
        """Test handling of encoding errors in env file."""
        env_file = tmp_path / ".env"

        # Write binary data that can't be decoded as UTF-8
        with open(env_file, 'wb') as f:
            f.write(b'\xff\xfe\x00\x00INVALID_UTF8_DATA')

        with patch('os.path.expanduser', return_value=str(env_file)):
            # Should handle gracefully without crashing
            load_env_file()


class TestSubprocessErrorHandling:

    @patch('subprocess.run')
    @patch('os.path.exists', return_value=True)
    def test_compress_image_subprocess_error(self, mock_exists, mock_run):
        """Test handling of subprocess errors in image compression."""
        from grok import compress_image

        mock_run.side_effect = Exception("Subprocess failed")

        result = compress_image("test.jpg", b"data", 1000000)

        assert result is None

    @patch('subprocess.run')
    @patch('os.path.exists', return_value=True)
    def test_compress_image_timeout_error(self, mock_exists, mock_run):
        """Test handling of timeout errors in image compression."""
        from grok import compress_image

        mock_run.side_effect = subprocess.TimeoutExpired("convert", 30)

        result = compress_image("test.jpg", b"data", 1000000)

        assert result is None
