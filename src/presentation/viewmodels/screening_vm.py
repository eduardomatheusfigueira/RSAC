#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
ViewModel de Triagem (ScreeningViewModel).
Ponte reativa entre a interface gráfica de triagem e o ScreeningService.
"""

from dataclasses import dataclass
from typing import Optional, Tuple
from src.core.domain.entities import Paper, Protocol as ProtocolEntity
from src.core.domain.events import ScreeningCompleted, BatchScreeningProgress
from src.core.services.screening_service import ScreeningService
from src.infrastructure.utils.event_bus import EventBus
from src.presentation.viewmodels.base_viewmodel import BaseViewModel


@dataclass
class ScreeningState:
    """Estado da tela de triagem."""
    current_paper_id: Optional[str] = None
    is_batch_running: bool = False
    batch_progress: Tuple[int, int] = (0, 0)
    last_message: str = ""


class ScreeningViewModel(BaseViewModel[ScreeningState]):
    """ViewModel para gerenciamento da triagem de artigos."""

    def __init__(self, service: ScreeningService, event_bus: Optional[EventBus] = None) -> None:
        super().__init__(initial_state=ScreeningState())
        self._service: ScreeningService = service
        self._bus: Optional[EventBus] = event_bus

        if self._bus:
            self._bus.subscribe(ScreeningCompleted, self._on_screening_completed)
            self._bus.subscribe(BatchScreeningProgress, self._on_batch_progress)

    def screen_paper(self, paper: Paper, protocol: ProtocolEntity) -> Paper:
        """Comando chamado pela View para triar um artigo."""
        self._state.current_paper_id = paper.id
        self._state.last_message = f"Triando artigo '{paper.id}'..."
        self.notify()

        updated_paper = self._service.screen_paper_sync(paper, protocol)

        self._state.last_message = f"Triagem do artigo '{paper.id}' concluída."
        self.notify()
        return updated_paper

    def _on_screening_completed(self, event: ScreeningCompleted) -> None:
        """Handler do evento de triagem concluída."""
        self._state.last_message = f"Artigo '{event.paper.id}' triado com decisão: {event.paper.decision.value}"
        self.notify()

    def _on_batch_progress(self, event: BatchScreeningProgress) -> None:
        """Handler do evento de progresso da triagem em lote."""
        self._state.batch_progress = (event.current, event.total)
        self._state.is_batch_running = event.current < event.total
        self._state.last_message = f"Progresso do Lote: {event.current}/{event.total}"
        self.notify()
