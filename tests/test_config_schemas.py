"""Testes para o módulo config_app.core.config_schemas."""
import sys
import json
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config_app.core.config_schemas import (
    BaseHarvesterConfig,
    BDTDConfig,
    ScieloConfig,
    OpenAlexConfig,
    PubMedConfig,
    ScopusConfig,
    load_and_validate_config,
)


class TestBaseHarvesterConfig:
    def test_default_values(self):
        config = BaseHarvesterConfig()
        assert config.db_path == "metadata.db"
        assert config.export_path == "resultados.xlsx"
        assert config.limit is None
        assert config.delay == 2.5
        assert config.keywords == []

    def test_valid_custom_values(self):
        config = BaseHarvesterConfig(
            db_path="custom.db",
            export_path="custom.xlsx",
            limit=50,
            delay=1.5,
            keywords=["  termo1  ", "termo2"]
        )
        assert config.db_path == "custom.db"
        assert config.limit == 50
        assert config.delay == 1.5
        assert config.keywords == ["termo1", "termo2"]

    def test_invalid_delay(self):
        with pytest.raises(Exception):
            BaseHarvesterConfig(delay=0.0)

    def test_invalid_limit(self):
        with pytest.raises(Exception):
            BaseHarvesterConfig(limit=0)


class TestSpecificConfigs:
    def test_bdtd_config(self):
        config = BDTDConfig(
            search_type="Title",
            sort_order="year",
            scrape_details=False,
            keywords=["tese"]
        )
        assert config.search_type == "Title"
        assert config.scrape_details is False

    def test_scielo_config(self):
        config = ScieloConfig(search_field="ti", keywords=["artigo"])
        assert config.search_field == "ti"

    def test_openalex_config(self):
        config = OpenAlexConfig(email="user@example.com", api_key="abc")
        assert config.email == "user@example.com"
        assert config.api_key == "abc"

    def test_pubmed_config(self):
        config = PubMedConfig(delay=0.35)
        assert config.delay == 0.35

    def test_scopus_config(self):
        config = ScopusConfig(api_key="12345", view="STANDARD")
        assert config.api_key == "12345"
        assert config.view == "STANDARD"


class TestLoadAndValidateConfig:
    def test_load_valid_config(self, sample_valid_config):
        config = load_and_validate_config(sample_valid_config, BaseHarvesterConfig)
        assert isinstance(config, BaseHarvesterConfig)
        assert len(config.keywords) == 2

    def test_load_nonexistent_file(self, temp_dir):
        with pytest.raises(FileNotFoundError):
            load_and_validate_config(temp_dir / "nonexistent.json", BaseHarvesterConfig)

    def test_load_invalid_json_syntax(self, temp_dir):
        bad_json = temp_dir / "bad_syntax.json"
        bad_json.write_text("{ incomplete json ...", encoding="utf-8")
        with pytest.raises(ValueError, match="Sintaxe JSON inválida"):
            load_and_validate_config(bad_json, BaseHarvesterConfig)

    def test_load_invalid_schema_types(self, temp_dir):
        bad_schema = temp_dir / "bad_schema.json"
        bad_schema.write_text(json.dumps({"delay": -5.0}), encoding="utf-8")
        with pytest.raises(ValueError, match="Estrutura inválida"):
            load_and_validate_config(bad_schema, BaseHarvesterConfig)
