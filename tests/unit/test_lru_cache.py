#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Testes unitários para a classe LRUCache e para as funções de higienização de texto.
"""

import pytest
from src.infrastructure.utils.lru_cache import LRUCache
from src.infrastructure.utils.text_sanitizer import sanitize_text, normalize_title, clean_doi


def test_lru_cache_eviction():
    cache = LRUCache[str, str](max_size=3)

    cache["key1"] = "val1"
    cache["key2"] = "val2"
    cache["key3"] = "val3"

    assert len(cache) == 3
    assert "key1" in cache

    # Acessa key1 para torná-lo o mais recentemente usado
    _ = cache["key1"]

    # Adiciona key4 -> deve despejar key2 (que é o menos recentemente usado)
    cache["key4"] = "val4"

    assert len(cache) == 3
    assert "key1" in cache
    assert "key3" in cache
    assert "key4" in cache
    assert "key2" not in cache


def test_lru_cache_dict_like_api():
    cache = LRUCache[str, int](max_size=5)

    cache.put("a", 100)
    assert cache.get("a") == 100
    assert cache.get("b", -1) == -1

    cache["b"] = 200
    assert cache["b"] == 200

    del cache["a"]
    assert "a" not in cache
    assert len(cache) == 1

    cache.clear()
    assert len(cache) == 0


def test_sanitize_text():
    raw_text = "Texto\x00 com \x07caracteres\x0e  especiais   e   múltiplos  espaços."
    clean = sanitize_text(raw_text)
    assert "\x00" not in clean
    assert "  " not in clean
    assert clean == "Texto com caracteres especiais e múltiplos espaços."


def test_normalize_title():
    t1 = "Planejamento Urbano e Desenvolvimentô!"
    t2 = "planejamento urbano e desenvolvimento"
    assert normalize_title(t1) == normalize_title(t2)
    assert normalize_title("Não Informado") == ""


def test_clean_doi():
    url_doi = "https://doi.org/10.1590/S0102-88392020000100001"
    assert clean_doi(url_doi) == "10.1590/s0102-88392020000100001"
    assert clean_doi("Não Informado") == ""
