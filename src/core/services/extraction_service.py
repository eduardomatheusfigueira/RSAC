#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Serviço de Domínio de Extração de Dados (ExtractionService).
Gerencia o preenchimento de perguntas do protocolo e extração estruturada de informações dos artigos.
"""

import logging
from typing import Optional, Dict, Any, List
from src.core.domain.entities import Paper, Protocol as ProtocolEntity
from src.core.ports.ai_client import AIClient
from src.core.ports.repositories import ProjectRepository, PDFRepository

logger: logging.Logger = logging.getLogger(__name__)


class ExtractionService:
    """Caso de uso para extração de dados estruturados (Triagem 2 / Extração)."""

    def __init__(
        self,
        ai_client: Optional[AIClient] = None,
        project_repo: Optional[ProjectRepository] = None,
        pdf_repo: Optional[PDFRepository] = None,
    ) -> None:
        self._ai: Optional[AIClient] = ai_client
        self._project_repo: Optional[ProjectRepository] = project_repo
        self._pdf_repo: Optional[PDFRepository] = pdf_repo

    def extract_answers_sync(
        self,
        paper: Paper,
        protocol: ProtocolEntity,
    ) -> Paper:
        """
        Extrai as respostas das perguntas do protocolo para um artigo utilizando o texto do PDF ou resumo.
        """
        if not protocol.extraction_questions:
            return paper

        full_text: Optional[str] = None
        if self._pdf_repo:
            full_text = self._pdf_repo.get_extracted_text(paper.id)

        text_to_analyze = full_text or paper.abstract
        if not text_to_analyze or len(text_to_analyze.strip()) < 20:
            logger.info(f"Texto insuficiente para extração no artigo ID '{paper.id}'.")
            return paper

        if not self._ai:
            raise RuntimeError("Cliente de IA não configurado para extração de dados.")

        system_instruction = (
            "Você é um especialista acadêmico responsável pela extração de dados em uma Revisão Sistemática. "
            "Responda a cada uma das perguntas formuladas estritamente com base no texto fornecido. "
            "Retorne a resposta EXCLUSIVAMENTE em formato JSON onde cada chave é a pergunta exata e o valor é a resposta factual."
        )

        prompt = f"""
        PERGUNTAS DE EXTRAÇÃO:
        {protocol.extraction_questions}

        TEXTO DO ARTIGO:
        Título: {paper.title}
        Conteúdo: {text_to_analyze[:10000]}
        """

        answers = self._ai.generate_json(prompt, system_instruction)
        updated_paper = paper

        for q, ans in answers.items():
            updated_paper = updated_paper.with_question_answer(str(q), str(ans))

        if self._project_repo:
            self._project_repo.update_paper(updated_paper)

        return updated_paper
