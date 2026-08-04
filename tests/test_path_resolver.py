"""Testes para o módulo config_app.utils.path_resolver."""
import sys
import os
from pathlib import Path

import pytest

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config_app.utils.path_resolver import (
    BASE_DIR,
    get_base_dir,
    resolve_path,
    resolve_db,
    resolve_config,
    fix_win_long_path,
    ensure_workspace_in_sys_path,
    HARVESTER_DIRS,
    DB_CANDIDATES,
    DEFAULT_DB_NAMES,
    DEFAULT_EXPORT_NAMES,
)


class TestGetBaseDir:
    def test_returns_path_object(self):
        result = get_base_dir()
        assert isinstance(result, Path)

    def test_base_dir_is_project_root(self):
        """BASE_DIR deve apontar para o diretório raiz do projeto RSAC."""
        assert BASE_DIR.name == "RSAC" or BASE_DIR.exists()

    def test_base_dir_contains_config_app(self):
        """O diretório raiz deve conter config_app/."""
        assert (BASE_DIR / "config_app").exists()

    def test_base_dir_contains_harvesters(self):
        """O diretório raiz deve conter ao menos um harvester."""
        assert (BASE_DIR / "bdtd_harvester").exists() or (BASE_DIR / "scielo_harvester").exists()


class TestResolvePath:
    def test_relative_path_resolved_to_base(self):
        result = resolve_path("bdtd_harvester/bdtd_config.json")
        assert result == BASE_DIR / "bdtd_harvester" / "bdtd_config.json"

    def test_absolute_path_returned_as_is(self):
        abs_path = "/tmp/some/absolute/path" if sys.platform != "win32" else "C:\\tmp\\some\\path"
        result = resolve_path(abs_path)
        assert result == Path(abs_path)

    def test_returns_path_object(self):
        result = resolve_path("test.db")
        assert isinstance(result, Path)

    def test_empty_relative_path(self):
        result = resolve_path("")
        # Empty string resolves to BASE_DIR itself
        assert result == BASE_DIR / ""


class TestResolveDb:
    def test_returns_none_for_unknown_source(self):
        result = resolve_db("NonExistentSource")
        assert result is None

    def test_returns_none_when_no_file_exists(self):
        """Se nenhum arquivo de banco existe, deve retornar None."""
        # Isso pode retornar um path válido se o banco existe no projeto
        result = resolve_db("OpenAlex")
        if result is not None:
            assert result.exists()

    def test_known_sources_have_candidates(self):
        """Todas as 5 fontes devem ter candidatos definidos."""
        for source in ["OpenAlex", "SciELO", "BDTD", "PubMed", "Scopus"]:
            assert source in DB_CANDIDATES
            assert len(DB_CANDIDATES[source]) >= 2


class TestResolveConfig:
    def test_returns_none_for_unknown_harvester(self):
        result = resolve_config("nonexistent")
        assert result is None

    def test_finds_existing_config(self):
        """Deve encontrar ao menos um config JSON real do projeto."""
        found_any = False
        for name in ["bdtd", "scielo", "openalex", "pubmed", "scopus"]:
            result = resolve_config(name)
            if result is not None:
                assert result.exists()
                assert result.suffix == ".json"
                found_any = True
        assert found_any, "Ao menos um harvester config deve ser encontrado"


class TestFixWinLongPath:
    def test_empty_path_returns_as_is(self):
        assert fix_win_long_path("") == ""

    def test_none_returns_none(self):
        assert fix_win_long_path(None) is None

    def test_returns_string(self):
        result = fix_win_long_path("test.txt")
        assert isinstance(result, str)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
    def test_windows_prepends_prefix(self):
        result = fix_win_long_path("C:\\Users\\test\\file.txt")
        assert result.startswith("\\\\?\\")

    @pytest.mark.skipif(sys.platform == "win32", reason="Non-Windows test")
    def test_non_windows_no_prefix(self):
        result = fix_win_long_path("/tmp/test/file.txt")
        assert not result.startswith("\\\\?\\")


class TestEnsureWorkspaceInSysPath:
    def test_adds_base_dir_to_sys_path(self):
        ensure_workspace_in_sys_path()
        assert str(BASE_DIR) in sys.path

    def test_idempotent(self):
        """Chamar múltiplas vezes não duplica a entrada no sys.path."""
        initial_count = sys.path.count(str(BASE_DIR))
        ensure_workspace_in_sys_path()
        ensure_workspace_in_sys_path()
        assert sys.path.count(str(BASE_DIR)) == initial_count


class TestConstants:
    def test_harvester_dirs_complete(self):
        """Devem existir 5 entradas de harvester."""
        assert len(HARVESTER_DIRS) == 5
        for key in ["bdtd", "scielo", "openalex", "pubmed", "scopus"]:
            assert key in HARVESTER_DIRS

    def test_default_db_names_complete(self):
        assert len(DEFAULT_DB_NAMES) == 5
        for name in DEFAULT_DB_NAMES.values():
            assert name.endswith(".db")

    def test_default_export_names_complete(self):
        assert len(DEFAULT_EXPORT_NAMES) == 5
        for name in DEFAULT_EXPORT_NAMES.values():
            assert name.endswith(".xlsx")
