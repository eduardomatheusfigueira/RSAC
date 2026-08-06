#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Testes unitários para o repositório de projetos JSON (JSONProjectRepository).
"""

import os
import tempfile
import pytest
from src.infrastructure.persistence.json_project_repo import JSONProjectRepository
from src.core.domain.entities import Paper, Protocol, Decision, ScreeningSession


def test_json_project_repository_save_and_load_session():
    with tempfile.TemporaryDirectory() as tmp_dir:
        json_path = os.path.join(tmp_dir, "test_session.json")
        repo = JSONProjectRepository(filepath=json_path)

        p1 = Paper(
            id="1",
            title="Artigo 1",
            authors="Autor A",
            year="2023",
            source="SciELO",
            research_type="Artigo",
            institution="USP",
            abstract="Resumo 1",
            download_url="http://link1",
            decision=Decision.INCLUDED,
        )

        session = ScreeningSession(
            papers=[p1],
            inclusion_criteria=["Critério 1"],
            exclusion_criteria=["Exclusão 1"],
            questions=["Pergunta 1"],
        )

        repo.save_session(session, json_path)
        assert os.path.exists(json_path)

        loaded_session = repo.load_session(json_path)
        assert loaded_session.total_count == 1
        assert loaded_session.included_count == 1
        assert loaded_session.papers[0].title == "Artigo 1"
        assert loaded_session.inclusion_criteria == ["Critério 1"]


def test_json_project_repository_save_and_load_protocol():
    with tempfile.TemporaryDirectory() as tmp_dir:
        json_path = os.path.join(tmp_dir, "test_protocol.json")
        repo = JSONProjectRepository(filepath=json_path)

        protocol = Protocol(
            title="Revisão sobre Inteligência Artificial",
            objective="Mapear modelos de linguagem",
            inclusion_criteria=["I1"],
            exclusion_criteria=["E1"],
            extraction_questions=["Q1"],
            keywords=["IA", "LLM"],
        )

        repo.save_protocol(protocol, json_path)
        assert os.path.exists(json_path)

        loaded_protocol = repo.load_protocol(json_path)
        assert loaded_protocol.title == "Revisão sobre Inteligência Artificial"
        assert loaded_protocol.keywords == ["IA", "LLM"]
