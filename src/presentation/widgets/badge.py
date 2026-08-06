#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Widget Badge / Chip — Estilo ScholarReview.

Pequeno rótulo com fundo sutil, usado para tags, status e metadados.
Equivalente ao <span class="bg-surface-container-low"> do HTML.
"""

import tkinter as tk
from typing import Optional

from src.presentation.theme import PALETTE


class Badge(tk.Label):
    """
    Badge minimalista para rótulos de status e metadados.

    Usage::

        Badge(parent, text="PRISMA-P").pack()
        Badge(parent, text="Incluído", variant="success").pack()
    """

    VARIANTS = {
        "default":  {"bg": PALETTE["surface_low"], "fg": PALETTE["on_surface"]},
        "success":  {"bg": PALETTE["success_subtle"], "fg": PALETTE["on_surface"]},
        "error":    {"bg": PALETTE["error_subtle"], "fg": PALETTE["on_surface"]},
        "warning":  {"bg": PALETTE["warning_subtle"], "fg": PALETTE["on_surface"]},
        "primary":  {"bg": PALETTE["primary"], "fg": PALETTE["on_primary"]},
    }

    def __init__(
        self,
        parent: tk.Widget,
        text: str = "",
        *,
        variant: str = "default",
        **kwargs,
    ) -> None:
        colors = self.VARIANTS.get(variant, self.VARIANTS["default"])

        kwargs.setdefault("bg", colors["bg"])
        kwargs.setdefault("fg", colors["fg"])
        kwargs.setdefault("font", ("Inter", 10))
        kwargs.setdefault("padx", 8)
        kwargs.setdefault("pady", 2)
        kwargs.setdefault("highlightthickness", 1)
        kwargs.setdefault("highlightbackground", PALETTE["border"])

        super().__init__(parent, text=text, **kwargs)

    def set_variant(self, variant: str) -> None:
        """Altera a variante visual do badge."""
        colors = self.VARIANTS.get(variant, self.VARIANTS["default"])
        self.configure(bg=colors["bg"], fg=colors["fg"])
