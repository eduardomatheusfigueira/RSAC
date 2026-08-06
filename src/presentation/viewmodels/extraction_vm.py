#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
ViewModel de Extração de Dados (ExtractionViewModel).
Gerencia o estado reativo da aba de extração profunda (Triagem 2).
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, List
from src.core.domain.entities import Paper, Protocol as ProtocolEntity
from src.core.services.extraction_service import ExtractionService
from src.presentation.viewmodels.base_viewmodel import BaseViewModel


@dataclass
class ExtractionState:
    """Estado reativo da tela de extração de dados."""
    selected_paper_id: Optional[str] = None
    extracted_questions: Dict[str, str] = field(default_factory=dict)
    is_extracting: bool = False
    message: str = ""


class ExtractionViewModel(BaseViewModel[ExtractionState]):
    """ViewModel no padrão MVVM para gerenciamento da extração de dados."""

    def __init__(self, service: ExtractionService) -> None:
        super().__init__(initial_state=ExtractionState())
        self._service: ExtractionService = service

    def select_paper(self, paper: Paper) -> None:
        """Seleciona um artigo para visualização e edição de extração."""
        self._state.selected_paper_id = paper.id
        self._state.extracted_questions = dict(paper.questions)
        self._state.message = f"Artigo '{paper.id}' selecionado para extração."
        self.notify()

    def update_answer(self, question: str, answer: str) -> None:
        """Atualiza manualmente a resposta para uma pergunta específica."""
        self._state.extracted_questions[question] = answer.strip()
        self.notify()

    def run_auto_extraction(self, paper: Paper, protocol: ProtocolEntity) -> Paper:
        """Executa a extração automática das respostas via IA."""
        self._state.is_extracting = True
        self._state.message = f"Extraindo respostas via IA para o artigo '{paper.id}'..."
        self.notify()

        updated_paper = self._service.extract_answers_sync(paper, protocol)

        self._state.extracted_questions = dict(updated_paper.questions)
        self._state.is_extracting = False
        self._state.message = f"Extração concluída para o artigo '{paper.id}'."
        self.notify()

        return updated_paper
