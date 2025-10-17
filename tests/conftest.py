import pytest
import os
import base64
import json


@pytest.fixture
def sample_jpeg_data():
    """Minimal valid JPEG header bytes for testing."""
    # This is a very small valid JPEG (1x1 pixel)
    return base64.b64decode(
        "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB"
        "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/2wBDAQEBAQEBAQEBAQEBAQEB"
        "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/wAARCAAB"
        "AAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAv/xAAUEAEAAAAAAAAAAAAAAAAAA"
        "AAv/xAAUEAEAAAAAAAAAAAAAAAAAAAAv/xAAUEAEAAAAAAAAAAAAAAAAAAAAv/9oADAMBAAIRAxEA"
        "AACj//2Q=="
    )


@pytest.fixture
def temp_file_cleanup():
    """Fixture to clean up temporary files after tests."""
    created_files = []

    def track_file(filepath):
        created_files.append(filepath)
        return filepath

    yield track_file

    # Cleanup
    for filepath in created_files:
        try:
            if os.path.exists(filepath):
                os.unlink(filepath)
        except Exception:
            pass  # Ignore cleanup errors in tests


@pytest.fixture
def mock_env_file(tmp_path):
    """Create a mock .env file for testing."""
    env_file = tmp_path / ".env"
    env_file.write_text('GROK_API_KEY=test_api_key_here\nexport OTHER_VAR=value\n')

    # Mock expanduser to point to our test directory
    original_expanduser = os.path.expanduser

    def mock_expanduser(path):
        if path == "~/.env":
            return str(env_file)
        return original_expanduser(path)

    os.path.expanduser = mock_expanduser
    yield env_file
    os.path.expanduser = original_expanduser


@pytest.fixture
def mock_urllib_response():
    """Mock urllib response for API calls."""
    class MockResponse:
        def __init__(self, data, status=200):
            self.data = data
            self.status = status

        def read(self):
            return self.data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def create_response(json_data, status=200):
        return MockResponse(json.dumps(json_data).encode('utf-8'))

    return create_response
