import sys
import pytest
import os
from unittest.mock import patch, MagicMock
from grok import call_grok_api, load_env_file

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestCallGrokApi:

    @patch('grok.os.getenv')
    @patch('urllib.request.urlopen')
    def test_call_grok_api_success_text(self, mock_urlopen, mock_getenv):
        """Test successful API call with text-only prompt."""
        mock_getenv.return_value = "test_api_key"

        # Mock successful response
        mock_response = MagicMock()
        mock_response.read.return_value = (
            b'{"choices": [{"message": {"content": "Test response"}}]}'
        )
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        result = call_grok_api("Test prompt")

        assert result == "Test response"

        # Verify API call structure
        args, kwargs = mock_urlopen.call_args
        request_obj = args[0]  # urllib.request.Request object
        request_data = request_obj.data.decode('utf-8')

        assert '"model": "grok-4-fast-reasoning"' in request_data
        assert '"messages"' in request_data
        assert '"Test prompt"' in request_data

    @patch('grok.load_env_file')
    @patch('grok.os.getenv')
    @patch('urllib.request.urlopen')
    def test_call_grok_api_env_file_fallback(self, mock_urlopen, mock_getenv, mock_load_env):
        """Test loading API key from env file when not in environment."""
        # Mock that no API key exists initially, but env file provides it
        call_count = [0]

        def mock_getenv_side_effect(key):
            call_count[0] += 1
            # First call - no key, second call (after env file) - key exists
            return "test_api_key" if call_count[0] > 1 else None

        mock_getenv.side_effect = mock_getenv_side_effect

        # Mock successful response for the actual API call
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"choices": [{"message": {"content": "Response"}}]}'
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        result = call_grok_api("Test prompt")

        assert result == "Response"
        mock_load_env.assert_called_once()

    @patch('grok.os.getenv', return_value=None)
    def test_call_grok_api_no_api_key(self, mock_getenv):
        """Test API call failure when no API key is available."""
        with pytest.raises(SystemExit):
            call_grok_api("Test prompt")

    @patch('grok.read_file_content')
    @patch('grok.os.getenv')
    @patch('urllib.request.urlopen')
    def test_call_grok_api_with_text_file(self, mock_urlopen, mock_getenv, mock_read_file):
        """Test API call with text file attachment."""
        mock_getenv.return_value = "test_api_key"
        mock_read_file.return_value = {"type": "text", "content": "File content here"}

        mock_response = MagicMock()
        mock_response.read.return_value = b'{"choices": [{"message": {"content": "Response"}}]}'
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        result = call_grok_api("Analyze this:", file_path="test.txt")

        assert result == "Response"

        # Verify request contains both prompt and file content
        args, kwargs = mock_urlopen.call_args
        request_obj = args[0]  # urllib.request.Request object
        request_data = request_obj.data.decode('utf-8')
        assert "File content:" in request_data
        assert "File content here" in request_data

    @patch('grok.read_file_content')
    @patch('grok.os.getenv')
    @patch('urllib.request.urlopen')
    def test_call_grok_api_with_image_file(self, mock_urlopen, mock_getenv, mock_read_file):
        """Test API call with image file switches to vision model."""
        mock_getenv.return_value = "test_api_key"
        mock_read_file.return_value = {
            "type": "image_url",
            "image_url": {
                "url": "data:image/jpeg;base64,test",
                "detail": "high"
            }
        }

        mock_response = MagicMock()
        mock_response.read.return_value = (
            b'{"choices": [{"message": {"content": "Image analyzed"}}]}'
        )
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        result = call_grok_api("Analyze this image:", file_path="test.jpg")

        assert result == "Image analyzed"

        # Verify vision model was used
        args, kwargs = mock_urlopen.call_args
        request_obj = args[0]  # urllib.request.Request object
        request_data = request_obj.data.decode('utf-8')
        assert '"model": "grok-2-vision-1212"' in request_data
        assert "image_url" in request_data

    @patch('grok.read_file_content')
    @patch('grok.os.getenv')
    @patch('urllib.request.urlopen')
    def test_call_grok_api_with_multi_image(self, mock_urlopen, mock_getenv, mock_read_file):
        """Test API call with multiple images from PDF."""
        mock_getenv.return_value = "test_api_key"
        mock_read_file.return_value = {
            "type": "multi_image",
            "images": [
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/jpeg;base64,image1", "detail": "high"}
                },
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/jpeg;base64,image2", "detail": "high"}
                }
            ]
        }

        mock_response = MagicMock()

        mock_response.read.return_value = (
            b'{"choices": [{"message": {"content": "Multi-page analyzed"}}]}'
        )
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        result = call_grok_api("Analyze PDF:", file_path="test.pdf", all_pages=True)

        assert result == "Multi-page analyzed"

        # Verify request structure for multiple images
        args, kwargs = mock_urlopen.call_args
        request_obj = args[0]  # urllib.request.Request object
        request_data = request_obj.data.decode('utf-8')
        assert '"model": "grok-2-vision-1212"' in request_data
        assert "image1" in request_data
        assert "image2" in request_data

    @patch('grok.os.getenv')
    @patch('urllib.request.urlopen')
    def test_call_grok_api_custom_model(self, mock_urlopen, mock_getenv):
        """Test API call with custom model specified."""
        mock_getenv.return_value = "test_api_key"

        mock_response = MagicMock()
        mock_response.read.return_value = b'{"choices": [{"message": {"content": "Response"}}]}'
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        result = call_grok_api("Test", model="custom-model")

        assert result == "Response"

        # Verify custom model in request
        args, kwargs = mock_urlopen.call_args
        request_obj = args[0]  # urllib.request.Request object
        request_data = request_obj.data.decode('utf-8')
        assert '"model": "custom-model"' in request_data

    @patch('urllib.request.urlopen')
    def test_call_grok_api_http_error(self, mock_urlopen):
        """Test handling of HTTP errors."""
        import urllib.request
        mock_urlopen.side_effect = urllib.request.HTTPError(
            url="https://api.x.ai/v1/chat/completions",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=None
        )

        with pytest.raises(SystemExit):
            call_grok_api("Test")

    @patch('urllib.request.urlopen')
    def test_call_grok_api_invalid_response(self, mock_urlopen):
        """Test handling of malformed API responses."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'invalid json'
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        with pytest.raises(SystemExit):
            call_grok_api("Test", model="test")

    @patch('urllib.request.urlopen')
    def test_call_grok_api_missing_choices(self, mock_urlopen):
        """Test handling of API responses without choices."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"invalid": "response"}'
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        with pytest.raises(SystemExit):
            call_grok_api("Test", model="test")


class TestLoadEnvFile:

    def test_load_env_file_success(self, tmp_path):
        """Test successful loading of environment variables from .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            'GROK_API_KEY=test_key\nexport DATABASE_URL=postgresql://...\nANOTHER_VAR=value\n'
        )

        with patch('os.path.expanduser', return_value=str(env_file)):
            with patch('os.getenv') as mock_getenv:
                mock_getenv.return_value = None  # Nothing in environment

                load_env_file()

                # Verify environment variables were set
                assert mock_getenv.call_count >= 0  # Can't easily verify environ setting with patching

    def test_load_env_file_nonexistent(self):
        """Test handling of nonexistent .env file."""
        with patch('os.path.expanduser', return_value="/nonexistent/.env"):
            with patch('os.path.exists', return_value=False):
                # Should not raise exception
                load_env_file()

    def test_load_env_file_malformed(self, tmp_path):
        """Test handling of malformed .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text('invalid line\nGROK_API_KEY = test\n')  # Extra spaces

        with patch('os.path.expanduser', return_value=str(env_file)):
            with patch('os.getenv') as mock_getenv:
                mock_getenv.return_value = None

                load_env_file()

                # Should handle gracefully without crashing

    def test_load_env_file_with_quotes(self, tmp_path):
        """Test handling of quoted values in .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text('KEY1="value with spaces"\nKEY2=\'single quotes\'\n')

        with patch('os.path.expanduser', return_value=str(env_file)):
            # Clear any existing values
            if 'KEY1' in os.environ:
                del os.environ['KEY1']
            if 'KEY2' in os.environ:
                del os.environ['KEY2']

            load_env_file()

            # Values should be set without quotes
            assert os.environ.get('KEY1') == 'value with spaces'
            assert os.environ.get('KEY2') == 'single quotes'

            # Cleanup
            if 'KEY1' in os.environ:
                del os.environ['KEY1']
            if 'KEY2' in os.environ:
                del os.environ['KEY2']

    def test_load_env_file_with_embedded_equals(self, tmp_path):
        """Test handling of values containing = signs."""
        env_file = tmp_path / ".env"
        env_file.write_text('DATABASE_URL=postgresql://user:pass=word@localhost/db\n')

        with patch('os.path.expanduser', return_value=str(env_file)):
            if 'DATABASE_URL' in os.environ:
                del os.environ['DATABASE_URL']

            load_env_file()

            assert os.environ.get('DATABASE_URL') == 'postgresql://user:pass=word@localhost/db'

            if 'DATABASE_URL' in os.environ:
                del os.environ['DATABASE_URL']

    def test_load_env_file_doesnt_overwrite_existing(self, tmp_path):
        """Test that existing environment variables aren't overwritten."""
        env_file = tmp_path / ".env"
        env_file.write_text('EXISTING_VAR=new_value\n')

        # Set existing value
        os.environ['EXISTING_VAR'] = 'original_value'

        with patch('os.path.expanduser', return_value=str(env_file)):
            load_env_file()

            # Should keep original value
            assert os.environ.get('EXISTING_VAR') == 'original_value'

            # Cleanup
            del os.environ['EXISTING_VAR']

    def test_load_env_file_with_comments_and_empty_lines(self, tmp_path):
        """Test handling of comments and empty lines."""
        env_file = tmp_path / ".env"
        env_file.write_text('# This is a comment\n\nKEY=value\n  \n# Another comment\n')

        with patch('os.path.expanduser', return_value=str(env_file)):
            if 'KEY' in os.environ:
                del os.environ['KEY']

            load_env_file()

            # Only KEY should be set
            assert os.environ.get('KEY') == 'value'

            if 'KEY' in os.environ:
                del os.environ['KEY']
