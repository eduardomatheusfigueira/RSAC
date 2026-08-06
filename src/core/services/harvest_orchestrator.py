#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Orquestrador de Coleta (HarvestOrchestrator).
Coordena a execução unificada dos 5 extratores bibliográficos (BDTD, SciELO, OpenAlex, PubMed, Scopus)
e notifica o progresso através do Barramento de Eventos (EventBus).
"""

import logging
from typing import Dict, Any, List, Optional
from src.core.domain.events import HarvestStarted, HarvestCompleted
from src.infrastructure.utils.event_bus import EventBus

logger: logging.Logger = logging.getLogger(__name__)


class HarvestOrchestrator:
    """Orquestrador unificado para disparo e acompanhamento dos extratores bibliográficos."""

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self._bus: Optional[EventBus] = event_bus

    def run_harvester(self, source_name: str, config: Dict[str, Any]) -> bool:
        """
        Executa um extrator específico pelo nome ("BDTD", "SciELO", "OpenAlex", "PubMed", "Scopus").
        """
        source_upper = source_name.strip().upper()
        keywords = config.get("keywords", [])
        keyword_str = keywords[0] if keywords else "N/A"

        if self._bus:
            self._bus.publish(HarvestStarted(source=source_upper, keyword=keyword_str))

        logger.info(f"Orquestrador iniciando coleta na base '{source_upper}'...")
        success = False

        try:
            if source_upper == "BDTD":
                from bdtd_harvester.bdtd_harvester import run_harvest
                success = run_harvest(config)
            elif source_upper == "SCIELO":
                from scielo_harvester.scielo_harvester import run_harvest
                success = run_harvest(config)
            elif source_upper == "OPENALEX":
                from openalex_harvester.openalex_harvester import run_harvest
                success = run_harvest(config)
            elif source_upper == "PUBMED":
                from pubmed_harvester.pubmed_harvester import run_harvest
                success = run_harvest(config)
            elif source_upper == "SCOPUS":
                from scopus_harvester.scopus_harvester import run_harvest
                success = run_harvest(config)
            else:
                logger.error(f"Extrator desconhecido: '{source_name}'.")
                return False

            if self._bus:
                self._bus.publish(HarvestCompleted(source=source_upper, keyword=keyword_str, records_saved=0))

            return success
        except Exception as e:
            logger.error(f"Falha na execução do extrator '{source_upper}': {e}", exc_info=True)
            return False
