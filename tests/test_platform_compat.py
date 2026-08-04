"""Testes para o módulo config_app.utils.platform_compat."""
import sys
import os
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config_app.utils.platform_compat import (
    configure_dpi_awareness,
    open_file_with_default_app,
    get_downloads_dir,
)


class TestConfigureDpiAwareness:
    def test_does_not_raise(self):
        """configure_dpi_awareness nunca deve lançar exceção, em qualquer SO."""
        configure_dpi_awareness()

    def test_can_call_multiple_times(self):
        """Chamar múltiplas vezes é seguro."""
        configure_dpi_awareness()
        configure_dpi_awareness()


class TestOpenFileWithDefaultApp:
    def test_raises_file_not_found_for_missing_file(self):
        with pytest.raises(FileNotFoundError):
            open_file_with_default_app("/nonexistent/path/to/file.pdf")

    def test_raises_for_nonexistent_path(self):
        """Deve lançar exceção para path que não existe."""
        with pytest.raises(FileNotFoundError):
            open_file_with_default_app("/definitely/nonexistent/file_12345.xyz")


class TestGetDownloadsDir:
    def test_returns_string(self):
        result = get_downloads_dir()
        assert isinstance(result, str)

    def test_contains_downloads(self):
        result = get_downloads_dir()
        assert "Downloads" in result or "downloads" in result.lower()

    def test_is_absolute_path(self):
        result = get_downloads_dir()
        assert os.path.isabs(result)
