#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Testes unitários para o sistema de desfazer/refazer (Command Pattern).
"""

import pytest
from src.core.commands.base_command import UpdatePaperDecisionCommand, CommandHistory
from src.core.domain.entities import Paper, Decision


def test_update_paper_decision_command_execute_and_undo():
    paper = Paper(
        id="P1",
        title="Artigo Teste",
        authors="Autor",
        year="2023",
        source="SciELO",
        research_type="Artigo",
        institution="USP",
        abstract="Resumo",
        download_url="http",
        decision=Decision.PENDING,
    )

    current_paper = paper

    def callback(updated_paper: Paper):
        nonlocal current_paper
        current_paper = updated_paper

    cmd = UpdatePaperDecisionCommand(paper=paper, new_decision=Decision.INCLUDED, on_paper_updated_callback=callback)

    # Executa o comando -> altera para INCLUDED
    cmd.execute()
    assert current_paper.decision == Decision.INCLUDED

    # Reverte o comando -> retorna para PENDING
    cmd.undo()
    assert current_paper.decision == Decision.PENDING


def test_command_history_undo_redo_stack():
    history = CommandHistory()
    paper = Paper(
        id="P2",
        title="Artigo Teste 2",
        authors="Autor",
        year="2023",
        source="SciELO",
        research_type="Artigo",
        institution="USP",
        abstract="Resumo",
        download_url="http",
        decision=Decision.PENDING,
    )

    current_paper = paper

    def callback(updated_paper: Paper):
        nonlocal current_paper
        current_paper = updated_paper

    cmd1 = UpdatePaperDecisionCommand(paper=paper, new_decision=Decision.INCLUDED, on_paper_updated_callback=callback)

    assert not history.can_undo
    assert not history.can_redo

    history.execute_command(cmd1)
    assert current_paper.decision == Decision.INCLUDED
    assert history.can_undo

    # Undo
    success_undo = history.undo()
    assert success_undo is True
    assert current_paper.decision == Decision.PENDING
    assert history.can_redo

    # Redo
    success_redo = history.redo()
    assert success_redo is True
    assert current_paper.decision == Decision.INCLUDED
