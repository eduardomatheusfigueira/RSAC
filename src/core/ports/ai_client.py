#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Contrato da Porta de Cliente de IA (AI Client Interface).
Permite abstrair os provedores de Inteligência Artificial (Gemini REST, SDK, OpenAI, etc.).
"""

from typing import Protocol, Dict, Any
from src.core.domain.entities import Paper, Protocol as ProtocolEntity


class AIClient(Protocol):
    """Protocolo definindo a interface exigida para serviços parceiros de IA no RSAC."""

    async def analyze_screening(
        self,
        paper: Paper,
        protocol: ProtocolEntity,
    ) -> Dict[str, Any]:
        """
        Analisa um artigo para triagem (Triagem 1 ou 2) retornando parecer e critérios validados.
        """
        ...

    async def generate_json(self, prompt: str, system_instruction: str = "") -> Dict[str, Any]:
        """
        Gera uma resposta estruturada em JSON para um prompt livre.
        """
        ...
