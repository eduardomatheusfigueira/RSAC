#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Schemas de Validação de Fronteira com Pydantic v2 (schemas.py).
Garante validação fail-fast de tipos e campos obrigatórios ao importar dados de JSON/APIs.
"""

from typing import List, Dict, Optional
from pydantic import BaseModel, Field, field_validator


class PaperDTO(BaseModel):
    """Schema Pydantic de validação de dados de entrada para Artigos."""
    id: str = Field(..., min_length=1, description="Identificador único do artigo.")
    title: str = Field(..., min_length=1, description="Título do artigo.")
    authors: str = Field(default="Não Informado")
    year: str = Field(default="Não Informado")
    source: str = Field(default="Outra")
    research_type: str = Field(default="Artigo")
    institution: str = Field(default="Não Informado")
    abstract: str = Field(default="Não Informado")
    download_url: str = Field(default="")
    decision: str = Field(default="Pendente")
    inclusion_criteria: Dict[str, bool] = Field(default_factory=dict)
    exclusion_criteria: Dict[str, bool] = Field(default_factory=dict)
    questions: Dict[str, str] = Field(default_factory=dict)
    observations: str = Field(default="")

    @field_validator("title")
    @classmethod
    def title_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("O título do artigo não pode ser uma string em branco.")
        return v.strip()


class ProtocolDTO(BaseModel):
    """Schema Pydantic de validação de dados de entrada para Protocolos."""
    title: str = Field(..., min_length=1, description="Título do protocolo de pesquisa.")
    objective: str = Field(default="")
    inclusion_criteria: List[str] = Field(default_factory=list)
    exclusion_criteria: List[str] = Field(default_factory=list)
    extraction_questions: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, v: List[str]) -> List[str]:
        return [kw.strip() for kw in v if kw.strip()]
