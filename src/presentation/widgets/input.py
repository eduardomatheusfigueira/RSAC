#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Widgets de Input — Estilo ScholarReview.

TextField: entrada de texto single-line estilizada.
TextArea: entrada multi-linha com cores e fontes do design system.
Select: combobox estilizado com fundo paper e borda fina.
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional, List

from src.presentation.theme import PALETTE


class TextField(ttk.Entry):
    """
    Entrada de texto single-line com estilo editorial.

    Aplica automaticamente fonte Inter, borda fina e fundo branco.
    """

    def __init__(self, parent: tk.Widget, **kwargs) -> None:
        kwargs.setdefault("font", ("Inter", 11))
        super().__init__(parent, **kwargs)


class TextArea(tk.Text):
    """
    Entrada de texto multi-linha com estilo editorial.

    Aplica cores do design system e espaçamento confortável.
    """

    def __init__(
        self,
        parent: tk.Widget,
        *,
        height: int = 5,
        **kwargs,
    ) -> None:
        kwargs.setdefault("bg", PALETTE["paper_white"])
        kwargs.setdefault("fg", PALETTE["on_surface"])
        kwargs.setdefault("font", ("Inter", 11))
        kwargs.setdefault("wrap", "word")
        kwargs.setdefault("relief", "solid")
        kwargs.setdefault("borderwidth", 1)
        kwargs.setdefault("highlightthickness", 1)
        kwargs.setdefault("highlightbackground", PALETTE["border"])
        kwargs.setdefault("highlightcolor", PALETTE["primary"])
        kwargs.setdefault("insertbackground", PALETTE["primary"])
        kwargs.setdefault("selectbackground", PALETTE["selection"])
        kwargs.setdefault("selectforeground", PALETTE["primary"])
        # Espaçamento vertical entre linhas (simula line-height 1.5)
        kwargs.setdefault("spacing1", 2)
        kwargs.setdefault("spacing3", 2)

        super().__init__(parent, height=height, **kwargs)


class Select(ttk.Combobox):
    """
    Combobox estilizado com fundo paper e borda fina.

    Usage::

        sel = Select(parent, values=["Opção A", "Opção B"], state="readonly")
        sel.set("Opção A")
    """

    def __init__(
        self,
        parent: tk.Widget,
        *,
        values: Optional[List[str]] = None,
        **kwargs,
    ) -> None:
        kwargs.setdefault("font", ("Inter", 11))
        if values is not None:
            kwargs["values"] = values
        super().__init__(parent, **kwargs)
