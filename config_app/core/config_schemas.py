#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
config_schemas.py — Modelos de validação de schemas JSON para o RSAC.

Utiliza Pydantic v2 para validar configurações de harvesters antes da execução,
prevenindo KeyError, tipos incorretos e valores inválidos em runtime.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator, ValidationError

logger = logging.getLogger(__name__)


class BaseHarvesterConfig(BaseModel):
    """Configuração base compartilhada por todos os harvesters do RSAC."""
    db_path: str = Field(default="metadata.db", min_length=1, description="Caminho do banco SQLite")
    export_path: str = Field(default="resultados.xlsx", min_length=1, description="Caminho do arquivo de exportação")
    limit: Optional[int] = Field(default=None, ge=1, description="Limite máximo de registros a coletar")
    delay: float = Field(default=2.5, gt=0, description="Intervalo em segundos entre requisições")
    keywords: List[str] = Field(default_factory=list, description="Lista de termos/strings booleanas para busca")

    @field_validator('keywords', mode='before')
    @classmethod
    def validate_keywords(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            v = [v]
        if not isinstance(v, list):
            return []
        cleaned = [str(k).strip() for k in v if str(k).strip()]
        return cleaned


class BDTDConfig(BaseHarvesterConfig):
    """Configuração do harvester BDTD."""
    search_type: str = Field(default="AllFields", description="Tipo de campo para busca no BDTD")
    sort_order: str = Field(default="year", description="Ordenação dos resultados")
    filters: Dict[str, Any] = Field(default_factory=dict, description="Filtros adicionais (formato, instituição, data, idioma)")
    scrape_details: bool = Field(default=True, description="Se deve raspar detalhes completos das teses/dissertações")


class ScieloConfig(BaseHarvesterConfig):
    """Configuração do harvester SciELO."""
    search_field: str = Field(default="", description="Campo de busca específico no SciELO")


class OpenAlexConfig(BaseHarvesterConfig):
    """Configuração do harvester OpenAlex."""
    email: Optional[str] = Field(default="", description="Email para polite pool")
    api_key: Optional[str] = Field(default="", description="Chave de API OpenAlex")
    filters: Dict[str, Any] = Field(default_factory=dict, description="Filtros adicionais de busca")


class PubMedConfig(BaseHarvesterConfig):
    """Configuração do harvester PubMed."""
    api_key: Optional[str] = Field(default="", description="Chave de API NCBI/PubMed")
    delay: float = Field(default=0.35, gt=0, description="Delay específico para PubMed (default 0.35s com/sem API key)")


class ScopusConfig(BaseHarvesterConfig):
    """Configuração do harvester Scopus."""
    api_key: str = Field(default="", description="Chave de API Elsevier Scopus")
    view: str = Field(default="COMPLETE", description="Nível de detalhamento da API Scopus (STANDARD ou COMPLETE)")
    insttoken: Optional[str] = Field(default="", description="Token institucional opcional da Elsevier")


HARVESTER_MODELS: Dict[str, type[BaseHarvesterConfig]] = {
    "bdtd": BDTDConfig,
    "scielo": ScieloConfig,
    "openalex": OpenAlexConfig,
    "pubmed": PubMedConfig,
    "scopus": ScopusConfig,
}


def load_and_validate_config(
    file_path: Union[str, Path],
    model_class: type[BaseHarvesterConfig] = BaseHarvesterConfig
) -> BaseHarvesterConfig:
    """
    Carrega um arquivo JSON de configuração e o valida usando o modelo Pydantic correspondente.

    Args:
        file_path: Caminho para o arquivo JSON de configuração.
        model_class: Classe do modelo Pydantic para validação.

    Returns:
        Instância do modelo validada.

    Raises:
        FileNotFoundError: Se o arquivo não for encontrado.
        ValueError: Se o arquivo JSON for inválido ou não passar na validação de schema.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de configuração não encontrado: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Sintaxe JSON inválida no arquivo {path}: {e}") from e

    if not isinstance(raw_data, dict):
        raise ValueError(f"O conteúdo do JSON em {path} deve ser um objeto/dicionário.")

    try:
        validated_config = model_class(**raw_data)
        logger.info(f"Configuração {path.name} validada com sucesso via {model_class.__name__}.")
        return validated_config
    except ValidationError as e:
        logger.error(f"Erro de validação no arquivo {path}: {e}")
        raise ValueError(f"Estrutura inválida no JSON {path.name}:\n{e}") from e
