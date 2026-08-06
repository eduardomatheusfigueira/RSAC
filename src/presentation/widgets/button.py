#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Widgets de Botão — Estilo ScholarReview.

PrimaryButton: fundo preto, texto branco (ação principal).
SecondaryButton: borda fina, fundo transparente (ação secundária).
GhostButton: sem borda, hover sutil (ação terciária/navegação).
"""

from tkinter import ttk
import tkinter as tk
from typing import Optional

from src.presentation.theme import PALETTE, ICONS


class PrimaryButton(ttk.Button):
    """Botão de ação principal — fundo preto sólido."""

    def __init__(self, parent: tk.Widget, **kwargs) -> None:
        kwargs.setdefault("style", "Primary.TButton")
        super().__init__(parent, **kwargs)


class SecondaryButton(ttk.Button):
    """Botão de ação secundária — borda fina, fundo sutil."""

    def __init__(self, parent: tk.Widget, **kwargs) -> None:
        kwargs.setdefault("style", "Secondary.TButton")
        super().__init__(parent, **kwargs)


class GhostButton(ttk.Button):
    """Botão fantasma — sem borda, hover em selection."""

    def __init__(self, parent: tk.Widget, **kwargs) -> None:
        kwargs.setdefault("style", "Ghost.TButton")
        super().__init__(parent, **kwargs)


class IconButton(ttk.Button):
    """
    Botão com ícone Material Symbols à esquerda do texto.

    Usage::

        btn = IconButton(parent, icon="save", text="Salvar", command=save_fn)
    """

    def __init__(
        self,
        parent: tk.Widget,
        *,
        icon: str,
        text: str = "",
        style: str = "Ghost.TButton",
        **kwargs,
    ) -> None:
        icon_char = ICONS.get(icon, "")
        display_text = f"{icon_char}  {text}" if icon_char and text else (icon_char or text)
        super().__init__(parent, text=display_text, style=style, **kwargs)
