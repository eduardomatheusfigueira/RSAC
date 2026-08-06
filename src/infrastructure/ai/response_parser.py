#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Parser de Resposta JSON para Inteligência Artificial (Gemini).
Extrai e repara strings JSON de blocos de resposta formatados em markdown (```json ... ```),
tratando vírgulas sobressalentes e caracteres especiais.
"""

import json
import re
import logging
from typing import Dict, Any

logger: logging.Logger = logging.getLogger(__name__)


class JSONResponseParser:
    """Parser estático e resiliente de JSON para respostas de Modelos de Linguagem."""

    @staticmethod
    def parse(text: str) -> Dict[str, Any]:
        """
        Parseia uma string de texto em dicionário JSON.
        Tenta múltiplas estratégias de parsing e reparo antes de lançar exceção.
        """
        if not text or not text.strip():
            raise ValueError("Resposta de texto da IA está vazia.")

        raw_text = text.strip()

        # 1. Tenta parse direto de JSON limpo
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            pass

        # 2. Extrai de bloco de código markdown ```json ... ``` ou ``` ... ```
        markdown_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', raw_text, re.IGNORECASE)
        if markdown_match:
            extracted = markdown_match.group(1).strip()
            try:
                return json.loads(extracted)
            except json.JSONDecodeError:
                raw_text = extracted

        # 3. Tenta localizar a primeira chave '{' e a última '}'
        start_idx = raw_text.find('{')
        end_idx = raw_text.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_candidate = raw_text[start_idx : end_idx + 1]
            try:
                return json.loads(json_candidate)
            except json.JSONDecodeError:
                # Reparo heurístico: remove vírgulas antes de fechamento de objeto ou lista
                repaired = re.sub(r',\s*([}\]])', r'\1', json_candidate)
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    pass

        logger.error(f"Falha ao parsear resposta da IA como JSON. Conteúdo bruto: {text[:200]}...")
        raise ValueError(f"Não foi possível extrair um JSON válido da resposta da IA: {text[:100]}")
