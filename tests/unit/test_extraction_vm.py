#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Testes unitários para o ExtractionViewModel.
"""

import pytest
from src.presentation.viewmodels.extraction_vm import ExtractionViewModel
from src.core.services.extraction_service import ExtractionService
from src.core.domain.entities import Paper, Decision, Protocol


class MockAIClientForExtraction:
    def generate_json(self, prompt: str, system_instruction: str = "") -> dict:
        return {"Qual o método?": "Método Causal X"}


def test_extraction_viewmodel_selection_and_auto_extract():
    service = ExtractionService(ai_client=MockAIClientForExtraction())
    vm = ExtractionViewModel(service=service)

    paper = Paper(
        id="P200",
        title="Estudo Causal",
        authors="A",
        year="2023",
        source="SciELO",
        research_type="Artigo",
        institution="USP",
        abstract="Texto extenso do artigo sobre métodos de inferência causal para teste de unidade.",
        download_url="http",
        questions={"Qual o método?": "Pendente"}
    )

    vm.select_paper(paper)
    assert vm.state.selected_paper_id == "P200"

    protocol = Protocol(title="P", objective="O", extraction_questions=["Qual o método?"])
    updated_paper = vm.run_auto_extraction(paper, protocol)

    assert vm.state.extracted_questions["Qual o método?"] == "Método Causal X"
    assert updated_paper.questions["Qual o método?"] == "Método Causal X"
