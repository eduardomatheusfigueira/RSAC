#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Entidades puras do domínio RSAC (Revisão Sistemática Assistida por Computador).
Isoladas de qualquer dependência com frameworks de UI (Tkinter) ou persistência.
"""

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any


class Decision(str, Enum):
    """Enumerador representando as decisões possíveis para um artigo na triagem."""
    PENDING = "Pendente"
    INCLUDED = "Incluído"
    EXCLUDED = "Excluído"


@dataclass(frozen=True)
class Paper:
    """
    Entidade imutável representando um artigo ou documento científico no RSAC.
    Qualquer modificação retorna uma nova instância da classe (imutabilidade).
    """
    id: str
    title: str
    authors: str
    year: str
    source: str
    research_type: str
    institution: str
    abstract: str
    download_url: str
    decision: Decision = Decision.PENDING
    inclusion_criteria: Dict[str, bool] = field(default_factory=dict)
    exclusion_criteria: Dict[str, bool] = field(default_factory=dict)
    questions: Dict[str, str] = field(default_factory=dict)
    observations: str = ""

    def with_decision(self, decision: Decision) -> "Paper":
        """Retorna uma nova instância de Paper com a decisão atualizada."""
        return replace(self, decision=decision)

    def with_criterion(self, criterion: str, value: bool, is_exclusion: bool = False) -> "Paper":
        """Retorna uma nova instância de Paper com o critério especificado atualizado."""
        if is_exclusion:
            new_exclusion = dict(self.exclusion_criteria)
            new_exclusion[criterion] = value
            return replace(self, exclusion_criteria=new_exclusion)
        else:
            new_inclusion = dict(self.inclusion_criteria)
            new_inclusion[criterion] = value
            return replace(self, inclusion_criteria=new_inclusion)

    def with_question_answer(self, question: str, answer: str) -> "Paper":
        """Retorna uma nova instância de Paper com a resposta da pergunta de extração atualizada."""
        new_questions = dict(self.questions)
        new_questions[question] = answer
        return replace(self, questions=new_questions)

    def with_observations(self, observations: str) -> "Paper":
        """Retorna uma nova instância de Paper com as observações atualizadas."""
        return replace(self, observations=observations)

    def to_dict(self) -> Dict[str, Any]:
        """Converte a entidade Paper para um dicionário legível/serializável."""
        return {
            "ID": self.id,
            "Título": self.title,
            "Autores": self.authors,
            "Ano": self.year,
            "Base": self.source,
            "Tipo de Pesquisa": self.research_type,
            "Universidade / Editora / Revista": self.institution,
            "Resumo": self.abstract,
            "Link para Download": self.download_url,
            "Decisão": self.decision.value,
            "Critérios de Inclusão": dict(self.inclusion_criteria),
            "Critérios de Exclusão": dict(self.exclusion_criteria),
            "Perguntas Específicas": dict(self.questions),
            "Observações": self.observations,
        }


@dataclass
class Protocol:
    """Protocolo da Revisão Sistemática (contendo objetivos, critérios e perguntas)."""
    title: str
    objective: str
    inclusion_criteria: List[str] = field(default_factory=list)
    exclusion_criteria: List[str] = field(default_factory=list)
    extraction_questions: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Converte a entidade Protocol para dicionário."""
        return {
            "title": self.title,
            "objective": self.objective,
            "inclusion_criteria": list(self.inclusion_criteria),
            "exclusion_criteria": list(self.exclusion_criteria),
            "extraction_questions": list(self.extraction_questions),
            "keywords": list(self.keywords),
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class ScreeningSession:
    """Agregado raiz representando uma sessão de triagem em andamento ou finalizada."""
    papers: List[Paper] = field(default_factory=list)
    inclusion_criteria: List[str] = field(default_factory=list)
    exclusion_criteria: List[str] = field(default_factory=list)
    questions: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    def paper_by_id(self, paper_id: str) -> Optional[Paper]:
        """Recupera um artigo pelo ID único."""
        return next((p for p in self.papers if p.id == paper_id), None)

    def replace_paper(self, updated: Paper) -> None:
        """Substitui o artigo atualizado na sessão mantendo a ordem."""
        for i, p in enumerate(self.papers):
            if p.id == updated.id:
                self.papers[i] = updated
                return
        raise ValueError(f"Paper com ID '{updated.id}' não encontrado na sessão.")

    @property
    def total_count(self) -> int:
        """Total de artigos na sessão."""
        return len(self.papers)

    @property
    def included_count(self) -> int:
        """Total de artigos incluídos."""
        return sum(1 for p in self.papers if p.decision == Decision.INCLUDED)

    @property
    def excluded_count(self) -> int:
        """Total de artigos excluídos."""
        return sum(1 for p in self.papers if p.decision == Decision.EXCLUDED)

    @property
    def pending_count(self) -> int:
        """Total de artigos pendentes de decisão."""
        return sum(1 for p in self.papers if p.decision == Decision.PENDING)
