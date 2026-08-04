"""Fixtures compartilhadas para todos os testes do RSAC."""
import pytest
import tempfile
import json
import os
import sys
from pathlib import Path

# Ensure the project root is in sys.path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def temp_dir():
    """Diretório temporário limpo para cada teste."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def sample_valid_config(temp_dir):
    """JSON de configuração válido para testes de harvester."""
    config = {
        "db_path": str(temp_dir / "test.db"),
        "export_path": str(temp_dir / "export"),
        "delay": 3.0,
        "keywords": ["planejamento urbano", "desenvolvimento regional"]
    }
    path = temp_dir / "test_config.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
    return path


@pytest.fixture
def sample_invalid_config_no_keywords(temp_dir):
    """JSON de configuração inválido — sem keywords."""
    config = {
        "db_path": str(temp_dir / "test.db"),
        "export_path": str(temp_dir / "export"),
        "delay": -1.0
    }
    path = temp_dir / "test_config_invalid.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
    return path


@pytest.fixture
def sample_session_json(temp_dir):
    """JSON de sessão de triagem para testes."""
    session = {
        "metadata": {
            "project_name": "Teste",
            "saved_at": "2026-01-01 00:00:00"
        },
        "session": {
            "trabalhos": [
                {
                    "title": "Planejamento Urbano no Brasil",
                    "authors": "Silva, J.",
                    "year": "2024",
                    "doi": "10.1590/S0102-88392020000100001",
                    "abstract": "Resumo do artigo sobre planejamento urbano.",
                    "status": "Incluído"
                },
                {
                    "title": "Regional Development Strategies",
                    "authors": "Oliveira, R.",
                    "year": "2023",
                    "doi": "10.1590/S0102-88392020000100002",
                    "abstract": "Abstract about regional development.",
                    "status": "Excluído"
                }
            ]
        }
    }
    path = temp_dir / "test_session.json"
    path.write_text(json.dumps(session, ensure_ascii=False), encoding='utf-8')
    return path
