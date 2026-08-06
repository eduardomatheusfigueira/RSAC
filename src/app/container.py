#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Container de Injeção de Dependências (IoC / Dependency Injection).
Instancia, conecta e gerencia o ciclo de vida dos repositórios, cliente de IA, serviços de domínio e ViewModels.
"""

import logging
from typing import Optional, List

from src.infrastructure.utils.event_bus import EventBus
from src.infrastructure.persistence.json_project_repo import JSONProjectRepository
from src.infrastructure.persistence.filesystem_pdf_repo import FileSystemPDFRepository
from src.infrastructure.ai.gemini_client import GeminiClient

from src.core.services.screening_service import ScreeningService
from src.core.services.extraction_service import ExtractionService
from src.core.services.harvest_orchestrator import HarvestOrchestrator

from src.presentation.viewmodels.protocol_vm import ProtocolViewModel
from src.presentation.viewmodels.screening_vm import ScreeningViewModel
from src.presentation.viewmodels.extraction_vm import ExtractionViewModel

logger: logging.Logger = logging.getLogger(__name__)


class Container:
    """Container IoC para gerenciamento centralizado de dependências do RSAC."""

    def __init__(
        self,
        json_db_path: str = "revisao_session.json",
        pdf_dir: str = "pdfs",
        gemini_keys: Optional[List[str]] = None,
    ) -> None:
        logger.info("Inicializando o Container de Injeção de Dependências (IoC)...")

        # 1. Barramento de Eventos (Singleton)
        self.event_bus: EventBus = EventBus()

        # 2. Repositórios
        self.project_repo: JSONProjectRepository = JSONProjectRepository(filepath=json_db_path)
        self.pdf_repo: FileSystemPDFRepository = FileSystemPDFRepository(pdf_dir=pdf_dir)

        # 3. Cliente de IA (opcional)
        self.gemini_client: Optional[GeminiClient] = None
        if gemini_keys:
            try:
                self.gemini_client = GeminiClient(api_keys=gemini_keys)
            except Exception as e:
                logger.warning(f"Não foi possível inicializar o GeminiClient no Container: {e}")

        # 4. Serviços de Domínio
        self.screening_service: ScreeningService = ScreeningService(
            ai_client=self.gemini_client,
            repository=self.project_repo,
            event_bus=self.event_bus,
        )
        self.extraction_service: ExtractionService = ExtractionService(
            ai_client=self.gemini_client,
            project_repo=self.project_repo,
            pdf_repo=self.pdf_repo,
        )
        self.harvest_orchestrator: HarvestOrchestrator = HarvestOrchestrator(
            event_bus=self.event_bus,
        )

        # 5. ViewModels para a camada de apresentação
        self.protocol_vm: ProtocolViewModel = ProtocolViewModel(repository=self.project_repo)
        self.screening_vm: ScreeningViewModel = ScreeningViewModel(
            service=self.screening_service,
            event_bus=self.event_bus,
        )
        self.extraction_vm: ExtractionViewModel = ExtractionViewModel(
            service=self.extraction_service,
        )

        logger.info("Container IoC inicializado com sucesso.")
