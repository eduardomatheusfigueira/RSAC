#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Serviço de Domínio de Triagem (ScreeningService).
Contém a lógica de caso de uso para triar um único artigo ou lotes de artigos por IA/regras.
"""

import logging
from typing import Optional, Dict, Any, List
from src.core.domain.entities import Paper, Protocol as ProtocolEntity, Decision
from src.core.domain.events import ScreeningCompleted, BatchScreeningProgress
from src.core.ports.repositories import ProjectRepository
from src.core.ports.ai_client import AIClient
from src.infrastructure.utils.event_bus import EventBus

logger: logging.Logger = logging.getLogger(__name__)


class ScreeningService:
    """Caso de uso de triagem automatizada ou assistida de artigos."""

    def __init__(
        self,
        ai_client: Optional[AIClient] = None,
        repository: Optional[ProjectRepository] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self._ai: Optional[AIClient] = ai_client
        self._repo: Optional[ProjectRepository] = repository
        self._bus: Optional[EventBus] = event_bus

    def _has_sufficient_data(self, paper: Paper) -> bool:
        """Validação prévia e fail-fast sem chamadas de rede."""
        if not paper.abstract:
            return False
        abstract = paper.abstract.strip().lower()
        if len(abstract) < 20:
            return False
        invalid_markers = {"", "n/a", "none", "não informado", "nao informado", "sem resumo"}
        return abstract not in invalid_markers

    def screen_paper_sync(
        self,
        paper: Paper,
        protocol: ProtocolEntity,
    ) -> Paper:
        """
        Executa a triagem síncrona de um único artigo.
        """
        if not self._has_sufficient_data(paper):
            logger.info(f"Artigo ID '{paper.id}' possui resumo insuficiente para triagem automática. Mantido como Pendente.")
            return paper.with_decision(Decision.PENDING)

        if not self._ai:
            raise RuntimeError("Cliente de IA não foi configurado no ScreeningService.")

        result = self._ai.analyze_screening(paper, protocol)

        decisao_str = result.get("decisao", Decision.PENDING.value)
        try:
            new_decision = Decision(decisao_str)
        except ValueError:
            new_decision = Decision.PENDING

        updated_paper = paper.with_decision(new_decision)

        # Atualiza critérios de inclusão e exclusão retornados
        inc_crits: Dict[str, bool] = result.get("criterios_inclusao", {})
        for crit_name, val in inc_crits.items():
            updated_paper = updated_paper.with_criterion(crit_name, bool(val), is_exclusion=False)

        exc_crits: Dict[str, bool] = result.get("criterios_exclusao", {})
        for crit_name, val in exc_crits.items():
            updated_paper = updated_paper.with_criterion(crit_name, bool(val), is_exclusion=True)

        if "justificativa" in result:
            updated_paper = updated_paper.with_observations(str(result["justificativa"]))

        if self._repo:
            self._repo.update_paper(updated_paper)

        if self._bus:
            self._bus.publish(ScreeningCompleted(paper=updated_paper, suggested_by_ai=True))

        return updated_paper

    def screen_batch_sync(
        self,
        papers: List[Paper],
        protocol: ProtocolEntity,
        stop_requested_check: Optional[Any] = None,
    ) -> List[Paper]:
        """
        Executa a triagem sequencial em lote para uma lista de artigos com reporte de progresso.
        """
        updated_papers: List[Paper] = []
        total = len(papers)

        for idx, paper in enumerate(papers, start=1):
            if stop_requested_check and stop_requested_check():
                logger.info("Triagem em lote interrompida pelo usuário.")
                break

            if paper.decision != Decision.PENDING:
                updated_papers.append(paper)
                continue

            try:
                screened = self.screen_paper_sync(paper, protocol)
                updated_papers.append(screened)
            except Exception as e:
                logger.error(f"Erro ao triar artigo ID '{paper.id}' no lote: {e}")
                updated_papers.append(paper)

            if self._bus:
                self._bus.publish(BatchScreeningProgress(current=idx, total=total, paper_id=paper.id))

        return updated_papers
