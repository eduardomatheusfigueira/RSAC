#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Testes unitários para o serviço de triagem (ScreeningService) utilizando Mock de AIClient.
"""

import pytest
from typing import Dict, Any
from src.core.services.screening_service import ScreeningService
from src.core.domain.entities import Paper, Protocol, Decision
from src.infrastructure.utils.event_bus import EventBus


class MockAIClient:
    """Mock testável do cliente de IA para testes isolados de unidade."""

    def __init__(self, mock_response: Dict[str, Any]) -> None:
        self.mock_response = mock_response
        self.calls = 0

    def analyze_screening(self, paper: Paper, protocol: Protocol) -> Dict[str, Any]:
        self.calls += 1
        return self.mock_response

    def generate_json(self, prompt: str, system_instruction: str = "") -> Dict[str, Any]:
        self.calls += 1
        return self.mock_response


def test_screening_service_screen_paper_included():
    mock_ai = MockAIClient({
        "decisao": "Incluído",
        "criterios_inclusao": {"Critério 1": True},
        "criterios_exclusao": {"Critério Exclusão": False},
        "justificativa": "Relevante ao tema."
    })
    event_bus = EventBus()
    events_received = []

    event_bus.subscribe(type(None), lambda e: None)  # Dummy

    service = ScreeningService(ai_client=mock_ai, event_bus=event_bus)

    paper = Paper(
        id="P100",
        title="Estudo de Causalidade",
        authors="Autor X",
        year="2024",
        source="PubMed",
        research_type="Artigo",
        institution="UFMG",
        abstract="Este artigo analisa causalidade em políticas públicas usando métodos modernos de inferência causal.",
        download_url="http://link",
    )

    protocol = Protocol(
        title="Protocolo Causalidade",
        objective="Analisar inferência causal",
        inclusion_criteria=["Critério 1"],
    )

    updated_paper = service.screen_paper_sync(paper, protocol)

    assert mock_ai.calls == 1
    assert updated_paper.decision == Decision.INCLUDED
    assert updated_paper.inclusion_criteria == {"Critério 1": True}
    assert updated_paper.observations == "Relevante ao tema."


def test_screening_service_insufficient_abstract_kept_pending():
    mock_ai = MockAIClient({"decisao": "Incluído"})
    service = ScreeningService(ai_client=mock_ai)

    paper = Paper(
        id="P101",
        title="Artigo Curto",
        authors="Autor Y",
        year="2024",
        source="SciELO",
        research_type="Artigo",
        institution="USP",
        abstract="Não informado",
        download_url="http://link",
    )

    protocol = Protocol(title="P", objective="O")
    updated_paper = service.screen_paper_sync(paper, protocol)

    assert mock_ai.calls == 0  # Fail-fast: não chamou a IA
    assert updated_paper.decision == Decision.PENDING
