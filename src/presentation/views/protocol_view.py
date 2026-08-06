#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
View de Configuração do Protocolo (ProtocolView).
Tela declarativa desacoplada no padrão MVVM.
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional
from src.presentation.viewmodels.protocol_vm import ProtocolViewModel, ProtocolState


class ProtocolView(ttk.Frame):
    """Componente de interface para gerenciamento de protocolos de pesquisa."""

    def __init__(self, parent: tk.Widget, viewmodel: ProtocolViewModel, **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self._vm: ProtocolViewModel = viewmodel

        self._build_ui()
        self._vm.add_listener(self._on_state_changed)

    def _build_ui(self) -> None:
        """Constrói os elementos gráficos da tela."""
        # 1. Título do Protocolo
        lbl_frame_title = ttk.LabelFrame(self, text="Título e Objetivo da Revisão")
        lbl_frame_title.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(lbl_frame_title, text="Título:").pack(anchor=tk.W, padx=5, pady=2)
        self._ent_title = ttk.Entry(lbl_frame_title, width=80)
        self._ent_title.pack(fill=tk.X, padx=5, pady=2)
        self._ent_title.bind("<FocusOut>", lambda e: self._vm.set_title(self._ent_title.get()))

        ttk.Label(lbl_frame_title, text="Objetivo Geral:").pack(anchor=tk.W, padx=5, pady=2)
        self._ent_objective = ttk.Entry(lbl_frame_title, width=80)
        self._ent_objective.pack(fill=tk.X, padx=5, pady=2)
        self._ent_objective.bind("<FocusOut>", lambda e: self._vm.set_objective(self._ent_objective.get()))

        # 2. Critérios de Inclusão e Exclusão
        lbl_frame_criteria = ttk.LabelFrame(self, text="Critérios Elegibilidade")
        lbl_frame_criteria.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Inclusão
        frame_inc = ttk.Frame(lbl_frame_criteria)
        frame_inc.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        ttk.Label(frame_inc, text="Critérios de Inclusão:", font=("Segoe UI", 9, "bold")).pack(anchor=tk.W)

        self._lst_inc = tk.Listbox(frame_inc, height=6)
        self._lst_inc.pack(fill=tk.BOTH, expand=True, pady=2)

        frame_inc_entry = ttk.Frame(frame_inc)
        frame_inc_entry.pack(fill=tk.X)
        self._ent_inc = ttk.Entry(frame_inc_entry)
        self._ent_inc.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(frame_inc_entry, text="+", width=3, command=self._add_inc).pack(side=tk.RIGHT)

        # Exclusão
        frame_exc = ttk.Frame(lbl_frame_criteria)
        frame_exc.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        ttk.Label(frame_exc, text="Critérios de Exclusão:", font=("Segoe UI", 9, "bold")).pack(anchor=tk.W)

        self._lst_exc = tk.Listbox(frame_exc, height=6)
        self._lst_exc.pack(fill=tk.BOTH, expand=True, pady=2)

        frame_exc_entry = ttk.Frame(frame_exc)
        frame_exc_entry.pack(fill=tk.X)
        self._ent_exc = ttk.Entry(frame_exc_entry)
        self._ent_exc.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(frame_exc_entry, text="+", width=3, command=self._add_exc).pack(side=tk.RIGHT)

    def _add_inc(self) -> None:
        val = self._ent_inc.get()
        if val:
            self._vm.add_inclusion_criterion(val)
            self._ent_inc.delete(0, tk.END)

    def _add_exc(self) -> None:
        val = self._ent_exc.get()
        if val:
            self._vm.add_exclusion_criterion(val)
            self._ent_exc.delete(0, tk.END)

    def _on_state_changed(self, state: ProtocolState) -> None:
        """Callback reativo quando o ViewModel notifica alterações de estado."""
        self._lst_inc.delete(0, tk.END)
        for item in state.inclusion_criteria:
            self._lst_inc.insert(tk.END, item)

        self._lst_exc.delete(0, tk.END)
        for item in state.exclusion_criteria:
            self._lst_exc.insert(tk.END, item)
