#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Widget EditorialProgress — Barra de progresso minimalista.

Altura mínima (2-4px), cor preta sobre fundo cinza claro.
"""

from tkinter import ttk
import tkinter as tk


class EditorialProgress(ttk.Progressbar):
    """
    Barra de progresso ultra-fina no estilo ScholarReview.

    Usage::

        prog = EditorialProgress(parent, maximum=100)
        prog.pack(fill="x")
        prog["value"] = 42
    """

    def __init__(
        self,
        parent: tk.Widget,
        *,
        mode: str = "determinate",
        **kwargs,
    ) -> None:
        kwargs.setdefault("length", 200)
        super().__init__(parent, mode=mode, **kwargs)

    def set_progress(self, current: int, total: int) -> None:
        """Atualiza valor e máximo de uma vez."""
        if total > 0:
            self["maximum"] = total
            self["value"] = current
        else:
            self["value"] = 0
