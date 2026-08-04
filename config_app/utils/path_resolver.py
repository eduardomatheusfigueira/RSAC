#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
path_resolver.py — Módulo centralizado para resolução de caminhos do RSAC.

Garante portabilidade entre:
- Execução direta (python config_app/main.py)
- Execução como módulo (python -m config_app)
- Empacotamento via PyInstaller (sys._MEIPASS)
- Execução a partir de qualquer diretório de trabalho

Todos os módulos do projeto devem usar este módulo para resolver caminhos,
em vez de hardcoded strings relativas.
"""

import os
import sys
from pathlib import Path


def get_base_dir() -> Path:
    """
    Retorna o diretório raiz do projeto RSAC.

    Compatível com:
    - Execução normal: resolve a partir do diretório pai de config_app/
    - PyInstaller: usa sys._MEIPASS como base
    """
    if getattr(sys, 'frozen', False):
        # Executando como executável empacotado pelo PyInstaller
        return Path(sys._MEIPASS)
    # Diretório deste arquivo: RSAC/config_app/utils/
    # Subir 2 níveis para chegar em RSAC/
    return Path(__file__).resolve().parent.parent.parent


# Diretório raiz do projeto (imutável após importação)
BASE_DIR = get_base_dir()


# ---------------------------------------------------------------------------
# Diretórios dos harvesters
# ---------------------------------------------------------------------------
HARVESTER_DIRS = {
    "bdtd": BASE_DIR / "bdtd_harvester",
    "scielo": BASE_DIR / "scielo_harvester",
    "openalex": BASE_DIR / "openalex_harvester",
    "pubmed": BASE_DIR / "pubmed_harvester",
    "scopus": BASE_DIR / "scopus_harvester",
}

# ---------------------------------------------------------------------------
# Caminhos de bancos de dados — cada fonte tem uma lista de candidatos
# O primeiro existente será utilizado.
# ---------------------------------------------------------------------------
DB_CANDIDATES = {
    "OpenAlex": [
        BASE_DIR / "openalex_metadata.db",
        BASE_DIR / "openalex_harvester" / "openalex_metadata.db",
    ],
    "SciELO": [
        BASE_DIR / "scielo_metadata.db",
        BASE_DIR / "scielo_harvester" / "scielo_metadata.db",
    ],
    "BDTD": [
        BASE_DIR / "bdtd_metadata.db",
        BASE_DIR / "bdtd_harvester" / "bdtd_metadata.db",
    ],
    "PubMed": [
        BASE_DIR / "pubmed_metadata.db",
        BASE_DIR / "pubmed_harvester" / "pubmed_metadata.db",
    ],
    "Scopus": [
        BASE_DIR / "scopus_metadata.db",
        BASE_DIR / "scopus_harvester" / "scopus_metadata.db",
    ],
}


def resolve_db(source_name: str) -> Path | None:
    """
    Retorna o primeiro caminho existente para o banco de dados da fonte.

    Args:
        source_name: Nome da fonte (ex: "OpenAlex", "SciELO", "BDTD").

    Returns:
        Path para o banco existente, ou None se nenhum for encontrado.
    """
    for candidate in DB_CANDIDATES.get(source_name, []):
        if candidate.exists():
            return candidate
    return None


def resolve_path(relative_path: str) -> Path:
    """
    Resolve um caminho relativo ao diretório raiz do projeto.

    Se o caminho fornecido já é absoluto, retorna como está.

    Args:
        relative_path: Caminho relativo ao BASE_DIR (ex: "bdtd_harvester/bdtd_config.json")

    Returns:
        Path absoluto resolvido.
    """
    p = Path(relative_path)
    if p.is_absolute():
        return p
    return BASE_DIR / p


def resolve_config(harvester_name: str) -> Path | None:
    """
    Localiza o arquivo JSON de configuração de um harvester.

    Procura em dois locais:
    1. config_app/<harvester_name>/<harvester_name>_config.json (GUI configs)
    2. <harvester_name>/<harvester_name>_config.json (configs standalone)

    Args:
        harvester_name: Nome do harvester (ex: "bdtd", "scielo").

    Returns:
        Path para o config encontrado, ou None.
    """
    candidates = [
        BASE_DIR / "config_app" / f"{harvester_name}_harvester" / f"{harvester_name}_config.json",
        BASE_DIR / f"{harvester_name}_harvester" / f"{harvester_name}_config.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def ensure_workspace_in_sys_path():
    """
    Garante que o diretório raiz do projeto está no sys.path.
    Necessário para que imports como `from bdtd_harvester.bdtd_harvester import ...` funcionem.
    """
    root_str = str(BASE_DIR)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def fix_win_long_path(path: str) -> str:
    r"""
    Normaliza path e prepõe \\?\ no Windows se o path for absoluto,
    habilitando bypass do limite MAX_PATH de 260 caracteres.

    Em outros SOs, retorna o path normalizado sem modificação.
    """
    if not path:
        return path
    abs_p = os.path.abspath(path)
    if sys.platform == "win32" and not abs_p.startswith("\\\\?\\"):
        return "\\\\?\\" + abs_p.replace("/", "\\")
    return abs_p


# Nomes de arquivo padrão para cada harvester (usados como defaults na GUI)
DEFAULT_DB_NAMES = {
    "bdtd": "2_bdtd_metadata.db",
    "scielo": "2_scielo_metadata.db",
    "openalex": "2_openalex_metadata.db",
    "pubmed": "2_pubmed_metadata.db",
    "scopus": "2_scopus_metadata.db",
}

DEFAULT_EXPORT_NAMES = {
    "bdtd": "2_bdtd_resultados.xlsx",
    "scielo": "2_scielo_resultados.xlsx",
    "openalex": "2_openalex_resultados.xlsx",
    "pubmed": "2_pubmed_resultados.xlsx",
    "scopus": "2_scopus_resultados.xlsx",
}
