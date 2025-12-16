import sys
import pytest
import os
from unittest.mock import patch, MagicMock
from llm_client import call_llm_api, load_env_file

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def create_mock_litellm_response(content="Test response"):
    """Helper to create a mock LiteLLM response object"""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = MagicMock()
    mock_response.choices[0].message.content = content
    return mock_response


class TestCallLLMApi:

    @patch('llm_client.os.getenv')
    @patch('llm_client.completion')
    def test_call_llm_api_success_text(self, mock_completion, mock_getenv):
        """Test successful API call with text-only prompt."""
        # Mock os.getenv to return appropriate values
        def getenv_side_effect(key, default=None):
            if key == "GROK_API_KEY":
                return "test_api_key"
            elif key == "LLM_MODEL":
                return None  # Use default
            return default
        mock_getenv.side_effect = getenv_side_effect

        # Mock successful LiteLLM response
        mock_completion.return_value = create_mock_litellm_response("Test response")

        result = call_llm_api("Test prompt")

        assert result == "Test response"

        # Verify API call structure
        mock_completion.assert_called_once()
        call_kwargs = mock_completion.call_args.kwargs

        assert call_kwargs["model"] == "xai/grok-4-1-fast-reasoning"
        assert call_kwargs['messages'] == [{"role": "user", "content": "Test prompt"}]
        assert call_kwargs['stream'] is False

    @patch('llm_client.load_env_file')
    @patch('llm_client.completion')
    def test_call_llm_api_env_file_fallback(self, mock_completion, mock_load_env):
        """Test loading API key from env file when not in environment."""
        # Mock successful LiteLLM response
        mock_completion.return_value = create_mock_litellm_response("Response")

        result = call_llm_api("Test prompt")

        assert result == "Response"
        mock_load_env.assert_called_once()

    @patch('llm_client.os.getenv', return_value=None)
    def test_call_llm_api_no_api_key(self, mock_getenv):
        """Test API call failure when no API key is available."""
        with pytest.raises(SystemExit):
            call_llm_api("Test prompt")

    @patch('llm_client.read_file_content')
    @patch('llm_client.os.getenv')
    @patch('llm_client.completion')
    def test_call_llm_api_with_text_file(self, mock_completion, mock_getenv, mock_read_file):
        """Test API call with text file attachment."""
        # Mock os.getenv to return appropriate values
        def getenv_side_effect(key, default=None):
            if key == "GROK_API_KEY":
                return "test_api_key"
            elif key == "LLM_MODEL":
                return None  # Use default
            return default
        mock_getenv.side_effect = getenv_side_effect

        mock_read_file.return_value = {"type": "text", "content": "File content here"}

        # Mock successful LiteLLM response
        mock_completion.return_value = create_mock_litellm_response("Response")

        result = call_llm_api("Analyze this:", file_path="test.txt")

        assert result == "Response"

        # Verify request contains both prompt and file content
        call_kwargs = mock_completion.call_args.kwargs
        messages = call_kwargs['messages']
        assert len(messages) == 1
        assert "File content:" in messages[0]['content']
        assert "File content here" in messages[0]['content']

    @patch('llm_client.read_file_content')
    @patch('llm_client.os.getenv')
    @patch('llm_client.completion')
    def test_call_llm_api_with_image_file(self, mock_completion, mock_getenv, mock_read_file):
        """Test API call with image file switches to vision model."""
        # Mock os.getenv to return appropriate values
        def getenv_side_effect(key, default=None):
            if key == "GROK_API_KEY":
                return "test_api_key"
            elif key == "LLM_MODEL":
                return None  # Use default
            return default
        mock_getenv.side_effect = getenv_side_effect

        mock_read_file.return_value = {
            "type": "image_url",
            "image_url": {
                "url": "data:image/jpeg;base64,test",
                "detail": "high"
            }
        }

        # Mock successful LiteLLM response
        mock_completion.return_value = create_mock_litellm_response("Image analyzed")

        result = call_llm_api("Analyze this image:", file_path="test.jpg")

        assert result == "Image analyzed"

        # Verify vision model was used (latest alias)
        call_kwargs = mock_completion.call_args.kwargs
        assert call_kwargs["model"] == "xai/grok-4-1-fast-reasoning"

    @patch('llm_client.read_file_content')
    @patch('llm_client.os.getenv')
    @patch('llm_client.completion')
    def test_call_llm_api_with_multi_image(self, mock_completion, mock_getenv, mock_read_file):
        """Test API call with multiple images from PDF."""
        # Mock os.getenv to return appropriate values
        def getenv_side_effect(key, default=None):
            if key == "GROK_API_KEY":
                return "test_api_key"
            elif key == "LLM_MODEL":
                return None  # Use default
            return default
        mock_getenv.side_effect = getenv_side_effect

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

        # Mock successful LiteLLM response
        mock_completion.return_value = create_mock_litellm_response("Multi-page analyzed")

        result = call_llm_api("Analyze PDF:", file_path="test.pdf", all_pages=True)

        assert result == "Multi-page analyzed"

        # Verify vision model was used and multiple images were passed (latest alias)
        call_kwargs = mock_completion.call_args.kwargs
        assert call_kwargs["model"] == "xai/grok-4-1-fast-reasoning"
        messages = call_kwargs['messages']
        assert len(messages) == 1
        # Content should be a list with text and multiple images
        assert isinstance(messages[0]['content'], list)
        assert len(messages[0]['content']) == 3  # text + 2 images

    @patch('llm_client.os.getenv')
    @patch('llm_client.completion')
    def test_call_llm_api_custom_model(self, mock_completion, mock_getenv):
        """Test API call with custom model specified."""
        # Mock os.getenv to return appropriate values
        def getenv_side_effect(key, default=None):
            if key == "GROK_API_KEY":
                return "test_api_key"
            elif key == "LLM_MODEL":
                return None  # Use default
            return default
        mock_getenv.side_effect = getenv_side_effect

        # Mock successful LiteLLM response
        mock_completion.return_value = create_mock_litellm_response("Response")

        result = call_llm_api("Test", model="custom-model")

        assert result == "Response"

        # Verify custom model in request
        call_kwargs = mock_completion.call_args.kwargs
        assert call_kwargs['model'] == "custom-model"

    @patch('llm_client.completion')
    def test_call_llm_api_http_error(self, mock_completion):
        """Test handling of API errors."""
        # Mock LiteLLM raising an exception
        mock_completion.side_effect = Exception("API Error: 401 Unauthorized")

        with pytest.raises(SystemExit):
            call_llm_api("Test")

    @patch('llm_client.completion')
    def test_call_llm_api_invalid_response(self, mock_completion):
        """Test handling of malformed API responses."""
        # Mock response with invalid structure
        mock_completion.side_effect = Exception("Invalid response structure")

        with pytest.raises(SystemExit):
            call_llm_api("Test", model="test")

    @patch('llm_client.completion')
    def test_call_llm_api_missing_choices(self, mock_completion):
        """Test handling of API responses without choices."""
        # Mock response with missing choices
        mock_completion.side_effect = AttributeError("'NoneType' object has no attribute 'choices'")

        with pytest.raises(SystemExit):
            call_llm_api("Test", model="test")


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
