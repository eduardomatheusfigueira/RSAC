#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Widget Reutilizável de Barra de Status (StatusBarWidget).
Renderiza mensagens de status, contadores de artigos e barra de progresso em Tkinter.

Estilizado com Design System ScholarReview.
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional

from src.presentation.theme import PALETTE


class StatusBarWidget(ttk.Frame):
    """Barra de status para exibição de mensagens operacionais e progresso."""

    def __init__(self, parent: tk.Widget, **kwargs) -> None:
        super().__init__(parent, **kwargs)

        body_font = ("Inter", 11)
        caption_font = ("Inter", 10)

        self._lbl_status = ttk.Label(
            self, text="Pronto", anchor=tk.W,
            font=caption_font,
            foreground=PALETTE["on_surface_v"],
        )
        self._lbl_status.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=2)

        self._lbl_counts = ttk.Label(
            self,
            text="Artigos: 0 | Incluídos: 0 | Excluídos: 0",
            anchor=tk.E,
            font=caption_font,
            foreground=PALETTE["outline"],
        )
        self._lbl_counts.pack(side=tk.RIGHT, padx=5, pady=2)

        self._progress_bar = ttk.Progressbar(self, mode="determinate", length=150)
        self._progress_bar.pack(side=tk.RIGHT, padx=5, pady=2)
        self._progress_bar.pack_forget()  # Oculta inicialmente

    def set_status(self, message: str) -> None:
        """Atualiza a mensagem de status exibida."""
        self._lbl_status.config(text=message)

    def set_counts(self, total: int, included: int, excluded: int, pending: int) -> None:
        """Atualiza os indicadores contadores de artigos."""
        self._lbl_counts.config(
            text=f"Total: {total} | Incluídos: {included} | Excluídos: {excluded} | Pendentes: {pending}"
        )

    def update_progress(self, current: int, total: int) -> None:
        """Atualiza a barra de progresso determinística."""
        if total > 0:
            self._progress_bar.pack(side=tk.RIGHT, padx=5, pady=2)
            self._progress_bar["maximum"] = total
            self._progress_bar["value"] = current
            if current >= total:
                self._progress_bar.pack_forget()
        else:
            self._progress_bar.pack_forget()
