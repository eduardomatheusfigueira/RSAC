#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Widget EditorialCard — Card minimalista estilo ScholarReview.

Equivalente ao <article> do HTML de referência: fundo branco,
borda fina 1px #E5E5E5, hover com borda preta, cantos quase retos.
"""

import tkinter as tk
from typing import Optional

from src.presentation.theme import PALETTE


class EditorialCard(tk.Frame):
    """
    Card minimalista com borda sutil e hover feedback.

    Usage::

        card = EditorialCard(parent, padding=24)
        card.pack(fill="x", padx=16, pady=8)

        # Adicione widgets ao interior do card:
        tk.Label(card.inner, text="Título", bg=PALETTE["paper_white"])
    """

    def __init__(
        self,
        parent: tk.Widget,
        *,
        padding: int = 24,
        hover: bool = True,
        **kwargs,
    ) -> None:
        self._bg = kwargs.pop("bg", PALETTE["paper_white"])
        self._border_color = PALETTE["border"]
        self._hover_color = PALETTE["primary"]
        self._hover_enabled = hover

        super().__init__(
            parent,
            bg=self._bg,
            highlightthickness=1,
            highlightbackground=self._border_color,
            highlightcolor=self._hover_color if hover else self._border_color,
            **kwargs,
        )

        # Frame interno com padding
        self._inner = tk.Frame(self, bg=self._bg)
        self._inner.pack(fill="both", expand=True, padx=padding, pady=padding)

        if hover:
            self.bind("<Enter>", self._on_enter)
            self.bind("<Leave>", self._on_leave)
            # Propagar hover para widgets filhos
            self._inner.bind("<Enter>", self._on_enter)
            self._inner.bind("<Leave>", self._on_leave)

    @property
    def inner(self) -> tk.Frame:
        """Frame interno onde os widgets de conteúdo devem ser adicionados."""
        return self._inner

    def _on_enter(self, _event: Optional[tk.Event] = None) -> None:
        """Hover in: borda muda para preto."""
        self.configure(highlightbackground=self._hover_color)

    def _on_leave(self, _event: Optional[tk.Event] = None) -> None:
        """Hover out: borda volta ao cinza."""
        self.configure(highlightbackground=self._border_color)

    def set_active(self, active: bool = True) -> None:
        """Marca o card como ativo (borda preta permanente) ou inativo."""
        if active:
            self.configure(highlightbackground=self._hover_color)
        else:
            self.configure(highlightbackground=self._border_color)
