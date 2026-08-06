#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
ViewModel do Protocolo de Pesquisa (ProtocolViewModel).
Gerencia o estado reativo da aba de configuração do protocolo e integração com o repositório.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from src.core.domain.entities import Protocol as ProtocolEntity
from src.core.ports.repositories import ProjectRepository
from src.presentation.viewmodels.base_viewmodel import BaseViewModel


@dataclass
class ProtocolState:
    """Estado reativo do protocolo de pesquisa."""
    title: str = ""
    objective: str = ""
    inclusion_criteria: List[str] = field(default_factory=list)
    exclusion_criteria: List[str] = field(default_factory=list)
    extraction_questions: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    is_saved: bool = False
    message: str = ""


class ProtocolViewModel(BaseViewModel[ProtocolState]):
    """ViewModel no padrão MVVM para gerenciamento do protocolo."""

    def __init__(self, repository: Optional[ProjectRepository] = None) -> None:
        super().__init__(initial_state=ProtocolState())
        self._repo: Optional[ProjectRepository] = repository

    def set_title(self, title: str) -> None:
        """Atualiza o título do protocolo."""
        self._state.title = title.strip()
        self.notify()

    def set_objective(self, objective: str) -> None:
        """Atualiza o objetivo do protocolo."""
        self._state.objective = objective.strip()
        self.notify()

    def add_inclusion_criterion(self, criterion: str) -> None:
        """Adiciona um novo critério de inclusão."""
        crit = criterion.strip()
        if crit and crit not in self._state.inclusion_criteria:
            self._state.inclusion_criteria.append(crit)
            self._state.is_saved = False
            self.notify()

    def remove_inclusion_criterion(self, criterion: str) -> None:
        """Remove um critério de inclusão."""
        if criterion in self._state.inclusion_criteria:
            self._state.inclusion_criteria.remove(criterion)
            self._state.is_saved = False
            self.notify()

    def add_exclusion_criterion(self, criterion: str) -> None:
        """Adiciona um novo critério de exclusão."""
        crit = criterion.strip()
        if crit and crit not in self._state.exclusion_criteria:
            self._state.exclusion_criteria.append(crit)
            self._state.is_saved = False
            self.notify()

    def remove_exclusion_criterion(self, criterion: str) -> None:
        """Remove um critério de exclusão."""
        if criterion in self._state.exclusion_criteria:
            self._state.exclusion_criteria.remove(criterion)
            self._state.is_saved = False
            self.notify()

    def add_extraction_question(self, question: str) -> None:
        """Adiciona uma pergunta de extração."""
        q = question.strip()
        if q and q not in self._state.extraction_questions:
            self._state.extraction_questions.append(q)
            self._state.is_saved = False
            self.notify()

    def remove_extraction_question(self, question: str) -> None:
        """Remove uma pergunta de extração."""
        if question in self._state.extraction_questions:
            self._state.extraction_questions.remove(question)
            self._state.is_saved = False
            self.notify()

    def add_keyword(self, keyword: str) -> None:
        """Adiciona uma palavra-chave de busca."""
        kw = keyword.strip()
        if kw and kw not in self._state.keywords:
            self._state.keywords.append(kw)
            self._state.is_saved = False
            self.notify()

    def remove_keyword(self, keyword: str) -> None:
        """Remove uma palavra-chave de busca."""
        if keyword in self._state.keywords:
            self._state.keywords.remove(keyword)
            self._state.is_saved = False
            self.notify()

    def save_protocol(self, filepath: str) -> bool:
        """Salva o protocolo atual no repositório."""
        protocol = ProtocolEntity(
            title=self._state.title,
            objective=self._state.objective,
            inclusion_criteria=list(self._state.inclusion_criteria),
            exclusion_criteria=list(self._state.exclusion_criteria),
            extraction_questions=list(self._state.extraction_questions),
            keywords=list(self._state.keywords),
        )
        if self._repo:
            try:
                self._repo.save_protocol(protocol, filepath)
                self._state.is_saved = True
                self._state.message = f"Protocolo salvo com sucesso em '{filepath}'."
                self.notify()
                return True
            except Exception as e:
                self._state.message = f"Erro ao salvar protocolo: {e}"
                self.notify()
                return False
        self._state.is_saved = True
        self.notify()
        return True

    def load_protocol(self, filepath: str) -> bool:
        """Carrega um protocolo a partir de um arquivo no repositório."""
        if self._repo:
            try:
                protocol = self._repo.load_protocol(filepath)
                self._state.title = protocol.title
                self._state.objective = protocol.objective
                self._state.inclusion_criteria = list(protocol.inclusion_criteria)
                self._state.exclusion_criteria = list(protocol.exclusion_criteria)
                self._state.extraction_questions = list(protocol.extraction_questions)
                self._state.keywords = list(protocol.keywords)
                self._state.is_saved = True
                self._state.message = f"Protocolo carregado de '{filepath}'."
                self.notify()
                return True
            except Exception as e:
                self._state.message = f"Erro ao carregar protocolo: {e}"
                self.notify()
                return False
        return False
