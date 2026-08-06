#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
View de Extração de Dados (ExtractionView).
Tela declarativa desacoplada no padrão MVVM para a etapa de extração profunda (Triagem 2).
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional, List
from src.core.domain.entities import Paper, Protocol as ProtocolEntity
from src.presentation.viewmodels.extraction_vm import ExtractionViewModel, ExtractionState
from src.presentation.widgets.status_bar import StatusBarWidget


class ExtractionView(ttk.Frame):
    """Componente gráfico da interface de extração profunda de dados dos artigos."""

    def __init__(
        self,
        parent: tk.Widget,
        viewmodel: ExtractionViewModel,
        protocol: Optional[ProtocolEntity] = None,
        **kwargs
    ) -> None:
        super().__init__(parent, **kwargs)
        self._vm: ExtractionViewModel = viewmodel
        self._protocol: Optional[ProtocolEntity] = protocol
        self._paper: Optional[Paper] = None

        self._build_ui()
        self._vm.add_listener(self._on_state_changed)

    def set_paper(self, paper: Paper) -> None:
        """Carrega o artigo para extração de dados."""
        self._paper = paper
        self._vm.select_paper(paper)

    def _build_ui(self) -> None:
        """Constrói a interface declarativa."""
        # 1. Informações do Artigo Selecionado
        lbl_frame_info = ttk.LabelFrame(self, text="Artigo em Extração")
        lbl_frame_info.pack(fill=tk.X, padx=10, pady=5)

        self._lbl_info = ttk.Label(lbl_frame_info, text="Nenhum artigo selecionado", font=("Segoe UI", 9, "bold"))
        self._lbl_info.pack(anchor=tk.W, padx=5, pady=5)

        # 2. Tabela/Campos de Extração
        lbl_frame_q = ttk.LabelFrame(self, text="Perguntas de Extração e Respostas")
        lbl_frame_q.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self._txt_questions = tk.Text(lbl_frame_q, wrap=tk.WORD, height=12)
        self._txt_questions.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 3. Painel de Ações
        frame_actions = ttk.Frame(self)
        frame_actions.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(frame_actions, text="🤖 Extrair Respostas via IA", command=self._on_auto_extract).pack(side=tk.LEFT, padx=5)

        # 4. Barra de Status
        self._status_bar = StatusBarWidget(self)
        self._status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def _on_auto_extract(self) -> None:
        if self._paper and self._protocol:
            updated = self._vm.run_auto_extraction(self._paper, self._protocol)
            self._paper = updated

    def _on_state_changed(self, state: ExtractionState) -> None:
        """Reage a mudanças de estado do ExtractionViewModel."""
        if state.message:
            self._status_bar.set_status(state.message)

        if self._paper:
            self._lbl_info.config(text=f"ID: {self._paper.id} | Título: {self._paper.title}")

        self._txt_questions.delete("1.0", tk.END)
        for q, ans in state.extracted_questions.items():
            self._txt_questions.insert(tk.END, f"P: {q}\nR: {ans}\n\n" + "-" * 40 + "\n\n")
