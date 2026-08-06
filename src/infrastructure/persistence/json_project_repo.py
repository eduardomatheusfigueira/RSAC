#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Repositório de Projeto Baseado em Arquivos JSON (JSONProjectRepository).
Implementa a interface ProjectRepository com gravação atômica em disco (.tmp -> rename).
"""

import json
import os
import tempfile
import logging
from typing import Dict, Any, List, Optional
from src.core.ports.repositories import ProjectRepository
from src.core.domain.entities import Paper, Protocol, Decision, ScreeningSession
from src.core.domain.exceptions import PaperNotFoundException

logger: logging.Logger = logging.getLogger(__name__)


class JSONProjectRepository(ProjectRepository):
    """
    Implementação concreta de ProjectRepository para serialização e desserialização em JSON.
    Garante integridade com gravações atômicas em disco.
    """

    def __init__(self, filepath: Optional[str] = None) -> None:
        self.default_filepath: Optional[str] = filepath

    def _atomic_write(self, target_filepath: str, data: Dict[str, Any]) -> None:
        """Executa gravação atômica no disco para prevenir corrupção em falhas repentinas."""
        dir_name = os.path.dirname(os.path.abspath(target_filepath))
        os.makedirs(dir_name, exist_ok=True)

        temp_fd, temp_path = tempfile.mkstemp(dir=dir_name, prefix=".rsac_tmp_", suffix=".json")
        try:
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            # Substitui o arquivo de destino de forma atômica
            os.replace(temp_path, target_filepath)
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            logger.error(f"Falha na gravação atômica do arquivo '{target_filepath}': {e}")
            raise

    def save_session(self, session: ScreeningSession, filepath: Optional[str] = None) -> None:
        target_file = filepath or self.default_filepath
        if not target_file:
            raise ValueError("Caminho do arquivo de destino não fornecido para salvar a sessão.")

        data: Dict[str, Any] = {
            "version": "1.1",
            "saved_at": session.created_at.isoformat(),
            "inclusion_criteria": session.inclusion_criteria,
            "exclusion_criteria": session.exclusion_criteria,
            "questions": session.questions,
            "records": [p.to_dict() for p in session.papers]
        }

        self._atomic_write(target_file, data)
        logger.info(f"Sessão salva com sucesso em '{target_file}' ({len(session.papers)} registros).")

    def load_session(self, filepath: Optional[str] = None) -> ScreeningSession:
        target_file = filepath or self.default_filepath
        if not target_file or not os.path.exists(target_file):
            raise FileNotFoundError(f"Arquivo de sessão '{target_file}' não encontrado.")

        with open(target_file, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)

        records_data = raw_data.get("records", [])
        papers: List[Paper] = []

        for r in records_data:
            decision_str = r.get("Decisão", Decision.PENDING.value)
            try:
                decision = Decision(decision_str)
            except ValueError:
                decision = Decision.PENDING

            paper = Paper(
                id=str(r.get("ID", "")),
                title=str(r.get("Título", "")),
                authors=str(r.get("Autores", "")),
                year=str(r.get("Ano", "")),
                source=str(r.get("Base", "")),
                research_type=str(r.get("Tipo de Pesquisa", "")),
                institution=str(r.get("Universidade / Editora / Revista", "")),
                abstract=str(r.get("Resumo", "")),
                download_url=str(r.get("Link para Download", "")),
                decision=decision,
                inclusion_criteria=r.get("Critérios de Inclusão", {}),
                exclusion_criteria=r.get("Critérios de Exclusão", {}),
                questions=r.get("Perguntas Específicas", {}),
                observations=r.get("Observações", ""),
            )
            papers.append(paper)

        session = ScreeningSession(
            papers=papers,
            inclusion_criteria=raw_data.get("inclusion_criteria", []),
            exclusion_criteria=raw_data.get("exclusion_criteria", []),
            questions=raw_data.get("questions", []),
        )

        logger.info(f"Sessão carregada de '{target_file}' ({len(papers)} registros).")
        return session

    def update_paper(self, paper: Paper) -> None:
        """Método em memória/persistência individual (a ser integrado no save da sessão)."""
        pass

    def save_protocol(self, protocol: Protocol, filepath: Optional[str] = None) -> None:
        target_file = filepath or self.default_filepath
        if not target_file:
            raise ValueError("Caminho do arquivo não fornecido para salvar o protocolo.")

        data = protocol.to_dict()
        self._atomic_write(target_file, data)
        logger.info(f"Protocolo salvo com sucesso em '{target_file}'.")

    def load_protocol(self, filepath: Optional[str] = None) -> Protocol:
        target_file = filepath or self.default_filepath
        if not target_file or not os.path.exists(target_file):
            raise FileNotFoundError(f"Arquivo de protocolo '{target_file}' não encontrado.")

        with open(target_file, 'r', encoding='utf-8') as f:
            raw = json.load(f)

        protocol = Protocol(
            title=raw.get("title", ""),
            objective=raw.get("objective", ""),
            inclusion_criteria=raw.get("inclusion_criteria", []),
            exclusion_criteria=raw.get("exclusion_criteria", []),
            extraction_questions=raw.get("extraction_questions", []),
            keywords=raw.get("keywords", []),
        )
        return protocol
