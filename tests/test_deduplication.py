"""Testes para as funções puras de consolidar_e_deduplicar.py."""
import sys
import os
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from consolidar_e_deduplicar import normalize_title, clean_doi


class TestNormalizeTitle:
    def test_removes_accents(self):
        assert normalize_title("Planejamento Urbano") == "planejamentourbano"

    def test_removes_accented_characters(self):
        result = normalize_title("Avaliação de Impacto Ambiental")
        assert "ã" not in result
        assert "ç" not in result
        assert result == "avaliacaodeimpactoambiental"

    def test_removes_special_characters(self):
        result = normalize_title("Título: com (parênteses) e [colchetes]!")
        assert ":" not in result
        assert "(" not in result
        assert "!" not in result

    def test_converts_to_lowercase(self):
        assert normalize_title("UPPERCASE TITLE") == "uppercasetitle"

    def test_handles_empty_string(self):
        assert normalize_title("") == ""

    def test_handles_none(self):
        assert normalize_title(None) == ""

    def test_handles_nan(self):
        """pandas float NaN deve retornar string vazia."""
        assert normalize_title(float('nan')) == ""

    def test_removes_hyphens_and_dots(self):
        result = normalize_title("Self-organizing systems v2.0")
        assert result == "selforganizingsystemsv20"

    def test_handles_unicode_normalization(self):
        # é pode ser representado como 'e' + combining accent ou como 'é' precomposto
        assert normalize_title("café") == "cafe"

    def test_same_title_different_accents_match(self):
        """Títulos com e sem acento devem normalizar para o mesmo valor."""
        assert normalize_title("Avaliação") == normalize_title("Avaliacao")


class TestCleanDoi:
    def test_extracts_from_full_url(self):
        doi = "https://doi.org/10.1590/S0102-88392020000100001"
        assert clean_doi(doi) == "10.1590/s0102-88392020000100001"

    def test_extracts_from_http_url(self):
        doi = "http://doi.org/10.1590/S0102-88392020000100001"
        assert clean_doi(doi) == "10.1590/s0102-88392020000100001"

    def test_handles_bare_doi(self):
        doi = "10.1590/S0102-88392020000100001"
        result = clean_doi(doi)
        assert result == "10.1590/s0102-88392020000100001"

    def test_handles_none(self):
        assert clean_doi(None) == ""

    def test_handles_empty_string(self):
        assert clean_doi("") == ""

    def test_handles_nao_informado(self):
        assert clean_doi("Não Informado") == ""
        assert clean_doi("não informado") == ""
        assert clean_doi("nao informado") == ""

    def test_handles_na_variants(self):
        assert clean_doi("N/A") == ""
        assert clean_doi("None") == ""
        assert clean_doi("nan") == ""

    def test_handles_nan_float(self):
        assert clean_doi(float('nan')) == ""

    def test_preserves_doi_format(self):
        """DOI sem URL deve ser preservado (em lowercase)."""
        doi = "10.1234/ABC-123"
        result = clean_doi(doi)
        assert result == "10.1234/abc-123"

    def test_case_insensitive(self):
        """Dois DOIs com case diferente devem normalizar igual."""
        doi1 = "10.1590/S0102-88392020000100001"
        doi2 = "10.1590/s0102-88392020000100001"
        assert clean_doi(doi1) == clean_doi(doi2)
