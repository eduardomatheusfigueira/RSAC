#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
View de Triagem (ScreeningView).
Tela declarativa desacoplada no padrão MVVM.
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional, List
from src.core.domain.entities import Paper, Decision, Protocol as ProtocolEntity
from src.presentation.viewmodels.screening_vm import ScreeningViewModel, ScreeningState
from src.presentation.widgets.paper_card import PaperCardWidget
from src.presentation.widgets.status_bar import StatusBarWidget


class ScreeningView(ttk.Frame):
    """Componente de interface gráfica para a etapa de triagem de artigos (Triagem 1)."""

    def __init__(
        self,
        parent: tk.Widget,
        viewmodel: ScreeningViewModel,
        protocol: Optional[ProtocolEntity] = None,
        **kwargs
    ) -> None:
        super().__init__(parent, **kwargs)
        self._vm: ScreeningViewModel = viewmodel
        self._protocol: Optional[ProtocolEntity] = protocol
        self._papers: List[Paper] = []
        self._current_index: int = 0

        self._build_ui()
        self._vm.add_listener(self._on_state_changed)

    def set_papers(self, papers: List[Paper]) -> None:
        """Carrega a lista de artigos para triagem."""
        self._papers = papers
        self._current_index = 0
        self._update_current_paper_display()

    def _build_ui(self) -> None:
        """Constrói os componentes gráficos da interface de triagem."""
        # 1. Card do Artigo
        self._paper_card = PaperCardWidget(self)
        self._paper_card.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 2. Painel de Ações de Triagem
        frame_actions = ttk.LabelFrame(self, text="Decisão de Elegibilidade")
        frame_actions.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(frame_actions, text="✔ Incluir (F1)", command=self._on_include).pack(side=tk.LEFT, padx=10, pady=5)
        ttk.Button(frame_actions, text="✖ Excluir (F2)", command=self._on_exclude).pack(side=tk.LEFT, padx=10, pady=5)
        ttk.Button(frame_actions, text="🤖 Triar por IA (F5)", command=self._on_screen_ai).pack(side=tk.LEFT, padx=10, pady=5)

        ttk.Button(frame_actions, text="Anterior (←)", command=self._prev_paper).pack(side=tk.RIGHT, padx=5, pady=5)
        ttk.Button(frame_actions, text="Próximo (→)", command=self._next_paper).pack(side=tk.RIGHT, padx=5, pady=5)

        # 3. Barra de Status
        self._status_bar = StatusBarWidget(self)
        self._status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def _update_current_paper_display(self) -> None:
        """Atualiza o artigo exibido no card."""
        if self._papers and 0 <= self._current_index < len(self._papers):
            current = self._papers[self._current_index]
            self._paper_card.display_paper(current)

            tot = len(self._papers)
            inc = sum(1 for p in self._papers if p.decision == Decision.INCLUDED)
            exc = sum(1 for p in self._papers if p.decision == Decision.EXCLUDED)
            pnd = sum(1 for p in self._papers if p.decision == Decision.PENDING)
            self._status_bar.set_counts(tot, inc, exc, pnd)
        else:
            self._paper_card.display_paper(None)

    def _on_include(self) -> None:
        if self._papers and 0 <= self._current_index < len(self._papers):
            paper = self._papers[self._current_index]
            updated = paper.with_decision(Decision.INCLUDED)
            self._papers[self._current_index] = updated
            self._update_current_paper_display()

    def _on_exclude(self) -> None:
        if self._papers and 0 <= self._current_index < len(self._papers):
            paper = self._papers[self._current_index]
            updated = paper.with_decision(Decision.EXCLUDED)
            self._papers[self._current_index] = updated
            self._update_current_paper_display()

    def _on_screen_ai(self) -> None:
        if self._papers and 0 <= self._current_index < len(self._papers) and self._protocol:
            paper = self._papers[self._current_index]
            updated = self._vm.screen_paper(paper, self._protocol)
            self._papers[self._current_index] = updated
            self._update_current_paper_display()

    def _prev_paper(self) -> None:
        if self._current_index > 0:
            self._current_index -= 1
            self._update_current_paper_display()

    def _next_paper(self) -> None:
        if self._current_index < len(self._papers) - 1:
            self._current_index += 1
            self._update_current_paper_display()

    def _on_state_changed(self, state: ScreeningState) -> None:
        """Reage a mudanças no ViewModel de triagem."""
        if state.last_message:
            self._status_bar.set_status(state.last_message)
        if state.is_batch_running:
            cur, tot = state.batch_progress
            self._status_bar.update_progress(cur, tot)
