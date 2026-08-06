#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Cliente de Conexão com a API Google Gemini.
Implementa a porta AIClient com suporte a rotação de múltiplas chaves de API,
fallback automático de modelos e retries resilientes usando a biblioteca tenacity.
"""

import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.core.domain.entities import Paper, Protocol as ProtocolEntity, Decision
from src.core.domain.exceptions import QuotaExhaustedException, ModelUnavailableException
from src.infrastructure.ai.response_parser import JSONResponseParser

logger: logging.Logger = logging.getLogger(__name__)


@dataclass
class GeminiKeyState:
    """Estado individual de uma chave de API do Gemini para controle de rotação."""
    key: str
    is_exhausted: bool = False
    failures: int = 0


class GeminiClient:
    """
    Cliente robusto para interação com a API REST do Google Gemini.
    Gerencia rotação de chaves, retry em falhas transitórias e fallback de modelos.
    """

    FALLBACK_MODELS = ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash")

    def __init__(self, api_keys: List[str], primary_model: str = "gemini-2.5-flash") -> None:
        if not api_keys:
            raise ValueError("Ao menos uma chave de API do Gemini deve ser fornecida.")
        self._key_states: List[GeminiKeyState] = [GeminiKeyState(key=k.strip()) for k in api_keys if k.strip()]
        if not self._key_states:
            raise ValueError("Nenhuma chave de API válida encontrada.")
        self._current_idx: int = 0
        self._primary_model: str = primary_model

    def _get_available_keys(self) -> List[GeminiKeyState]:
        """Retorna lista de chaves que ainda não atingiram a cota nesta sessão."""
        return [k for k in self._key_states if not k.is_exhausted]

    def _rotate_key(self) -> GeminiKeyState:
        """Rotaciona circularmente para a próxima chave de API disponível."""
        available = self._get_available_keys()
        if not available:
            # Reseta estado de esgotamento caso todas tenham sido marcadas como esgotadas (após pausa/respiro)
            for k in self._key_states:
                k.is_exhausted = False
            available = self._key_states

        self._current_idx = (self._current_idx + 1) % len(self._key_states)
        return self._key_states[self._current_idx]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        retry=retry_if_exception_type(ModelUnavailableException),
        reraise=True,
    )
    def generate_json(self, prompt: str, system_instruction: str = "") -> Dict[str, Any]:
        """
        Gera uma resposta estruturada em JSON enviando o prompt para a API do Gemini.
        Executa rotação de chaves e fallback de modelos se necessário.
        """
        key_state = self._rotate_key()
        models = [self._primary_model] + [m for m in self.FALLBACK_MODELS if m != self._primary_model]

        last_error: Optional[Exception] = None

        for model in models:
            try:
                raw_response = self._call_api(key_state.key, model, prompt, system_instruction)
                return JSONResponseParser.parse(raw_response)
            except QuotaExhaustedException:
                key_state.is_exhausted = True
                available = self._get_available_keys()
                if not available:
                    raise QuotaExhaustedException("Todas as chaves de API do Gemini atingiram o limite de cota.")
                key_state = self._rotate_key()
            except ModelUnavailableException as e:
                logger.warning(f"Modelo '{model}' indisponível, tentando próximo fallback...")
                last_error = e
                continue
            except Exception as e:
                logger.error(f"Erro ao chamar a API do Gemini com o modelo '{model}': {e}")
                last_error = e
                continue

        if last_error:
            raise last_error
        raise RuntimeError("Todas as tentativas de chamada à IA falharam.")

    def _call_api(self, api_key: str, model: str, prompt: str, system_instruction: str) -> str:
        """Executa a requisição HTTP POST para o endpoint REST da API do Gemini."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        params = {"key": api_key}
        headers = {"Content-Type": "application/json"}

        payload: Dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        resp = requests.post(url, params=params, json=payload, headers=headers, timeout=60)

        if resp.status_code == 429 or "RESOURCE_EXHAUSTED" in resp.text:
            logger.warning(f"Chave de API atingiu limite de cota (429/RESOURCE_EXHAUSTED).")
            raise QuotaExhaustedException("Limite de quota atingido nesta chave de API.")
        elif resp.status_code == 503:
            raise ModelUnavailableException(model)

        resp.raise_for_status()

        data = resp.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as e:
            raise ValueError(f"Resposta inesperada do formato da API Gemini: {data}")

    def analyze_screening(
        self,
        paper: Paper,
        protocol: ProtocolEntity,
    ) -> Dict[str, Any]:
        """
        Analisa o artigo fornecido contra os critérios e objetivos do protocolo de revisão.
        """
        system_instruction = (
            "Você é um assistente acadêmico sênior especializado em Revisões Sistemáticas da Literatura. "
            "Sua tarefa é analisar o artigo fornecido e emitir um parecer estritamente ancorado nos fatos informados. "
            "Responda EXCLUSIVAMENTE em formato JSON com as chaves: 'decisao' ('Incluído', 'Excluído' ou 'Pendente'), "
            "'criterios_inclusao' (dicionario de booleano), 'criterios_exclusao' (dicionario de booleano) e 'justificativa'."
        )

        prompt = f"""
        PROTOCOLO DE REVISÃO:
        Título: {protocol.title}
        Objetivo: {protocol.objective}
        Critérios de Inclusão: {protocol.inclusion_criteria}
        Critérios de Exclusão: {protocol.exclusion_criteria}

        ARTIGO EM ANÁLISE:
        ID: {paper.id}
        Título: {paper.title}
        Autores: {paper.authors}
        Ano: {paper.year}
        Resumo: {paper.abstract}
        """

        return self.generate_json(prompt, system_instruction)
