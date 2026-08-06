#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Testes unitários para as entidades puras do domínio (Paper, Protocol, Decision, ScreeningSession).
"""

import pytest
from src.core.domain.entities import Paper, Protocol, Decision, ScreeningSession


def test_paper_immutability_and_decision_update():
    paper = Paper(
        id="P001",
        title="Estudo de Caso em Planejamento Urbano",
        authors="Silva, João",
        year="2023",
        source="SciELO",
        research_type="Artigo",
        institution="USP",
        abstract="Resumo do estudo...",
        download_url="https://example.com/pdf",
        decision=Decision.PENDING,
    )

    # Imutabilidade: a decisão inicial continua PENDING
    updated_paper = paper.with_decision(Decision.INCLUDED)
    assert paper.decision == Decision.PENDING
    assert updated_paper.decision == Decision.INCLUDED
    assert updated_paper.id == "P001"


def test_paper_criteria_updates():
    paper = Paper(
        id="P002",
        title="Análise Causal em Saúde",
        authors="Oliveira, Maria",
        year="2024",
        source="PubMed",
        research_type="Artigo",
        institution="Unicamp",
        abstract="Resumo de saúde...",
        download_url="https://example.com/pdf2",
    )

    p_inc = paper.with_criterion("Critério 1", True, is_exclusion=False)
    p_exc = p_inc.with_criterion("Exclusão 1", False, is_exclusion=True)

    assert p_inc.inclusion_criteria == {"Critério 1": True}
    assert p_exc.inclusion_criteria == {"Critério 1": True}
    assert p_exc.exclusion_criteria == {"Exclusão 1": False}


def test_paper_to_dict():
    paper = Paper(
        id="P003",
        title="Desenvolvimento Regional",
        authors="Santos, Carlos",
        year="2022",
        source="BDTD",
        research_type="Tese",
        institution="UFRJ",
        abstract="Tese de desenvolvimento...",
        download_url="https://bdtd.ibict.br/P003",
        decision=Decision.EXCLUDED,
    )

    d = paper.to_dict()
    assert d["ID"] == "P003"
    assert d["Título"] == "Desenvolvimento Regional"
    assert d["Decisão"] == "Excluído"


def test_screening_session_aggregation():
    paper1 = Paper(id="1", title="Paper 1", authors="A1", year="2021", source="S1", research_type="A", institution="I1", abstract="Abs 1", download_url="U1", decision=Decision.INCLUDED)
    paper2 = Paper(id="2", title="Paper 2", authors="A2", year="2022", source="S2", research_type="A", institution="I2", abstract="Abs 2", download_url="U2", decision=Decision.EXCLUDED)
    paper3 = Paper(id="3", title="Paper 3", authors="A3", year="2023", source="S3", research_type="A", institution="I3", abstract="Abs 3", download_url="U3", decision=Decision.PENDING)

    session = ScreeningSession(papers=[paper1, paper2, paper3])

    assert session.total_count == 3
    assert session.included_count == 1
    assert session.excluded_count == 1
    assert session.pending_count == 1

    assert session.paper_by_id("2") == paper2
    assert session.paper_by_id("99") is None

    # Teste de substituição de artigo na sessão
    updated_paper2 = paper2.with_decision(Decision.INCLUDED)
    session.replace_paper(updated_paper2)

    assert session.included_count == 2
    assert session.excluded_count == 0
    assert session.paper_by_id("2").decision == Decision.INCLUDED
