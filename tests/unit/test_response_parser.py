#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Testes unitários para o parser de resposta JSON da IA (JSONResponseParser).
"""

import pytest
from src.infrastructure.ai.response_parser import JSONResponseParser


def test_parse_clean_json():
    raw = '{"decisao": "Incluído", "justificativa": "Relevante."}'
    parsed = JSONResponseParser.parse(raw)
    assert parsed["decisao"] == "Incluído"
    assert parsed["justificativa"] == "Relevante."


def test_parse_markdown_json_block():
    raw = """
    Aqui está a análise solicitada:
    ```json
    {
        "decisao": "Excluído",
        "criterios_inclusao": {"c1": false}
    }
    ```
    Espero ter ajudado.
    """
    parsed = JSONResponseParser.parse(raw)
    assert parsed["decisao"] == "Excluído"
    assert parsed["criterios_inclusao"] == {"c1": False}


def test_parse_trailing_comma_repair():
    raw = '{"decisao": "Pendente", "lista": [1, 2, 3,],}'
    parsed = JSONResponseParser.parse(raw)
    assert parsed["decisao"] == "Pendente"
    assert parsed["lista"] == [1, 2, 3]


def test_parse_empty_raises_value_error():
    with pytest.raises(ValueError):
        JSONResponseParser.parse("")
