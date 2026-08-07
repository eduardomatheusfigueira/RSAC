#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Utilitário de Higienização e Tratamento de Texto do RSAC.
Fornece funções puras para tratamento de strings, remoção de caracteres de controle,
normalização de títulos e sanitização de DOI.
"""

import re
import unicodedata
from typing import Optional


def sanitize_text(text: Optional[str]) -> str:
    """
    Remove caracteres de controle nulos e ajusta espaços em branco de textos de resumos e PDFs.
    """
    if not text:
        return ""
    # Substitui nulos e caracteres não imprimíveis por espaço
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', ' ', str(text))
    # Normaliza múltiplos espaços consecutivos
    cleaned = re.sub(r'[ \t]+', ' ', cleaned)
    return cleaned.strip()


def normalize_title(title: Optional[str]) -> str:
    """
    Normaliza um título para comparação e deduplicação:
    Converte para minúsculas, remove acentos, pontuações e caracteres especiais.
    """
    if not title:
        return ""
    s = str(title).strip().lower()
    if s in ["nao informado", "não informado", "none", "n/a", "nan", "sem titulo", "sem título"]:
        return ""
    # Remove acentuação usando decomposição NFD
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    # Mantém apenas caracteres alfanuméricos simples
    s = re.sub(r'[^a-z0-9]', '', s)
    return s


def clean_doi(doi: Optional[str]) -> str:
    """
    Higieniza e padroniza a string de DOI para formato minúsculo puro (ex: '10.1590/...').
    """
    if not doi:
        return ""
    doi_str = str(doi).strip().lower()
    if doi_str in ["não informado", "nao informado", "none", "n/a", "nan", ""]:
        return ""
    # Extrai DOI de URLs completas como https://doi.org/...
    match = re.search(r'(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)', doi_str)
    if match:
        return match.group(1).rstrip('.')
    return doi_str
