#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Widgets reutilizáveis do Design System ScholarReview.

Componentes atômicos estilizados para a camada de apresentação.
"""

from src.presentation.widgets.paper_card import PaperCardWidget
from src.presentation.widgets.status_bar import StatusBarWidget
from src.presentation.widgets.card import EditorialCard
from src.presentation.widgets.button import (
    PrimaryButton,
    SecondaryButton,
    GhostButton,
    IconButton,
)
from src.presentation.widgets.badge import Badge
from src.presentation.widgets.input import TextField, TextArea, Select
from src.presentation.widgets.progress import EditorialProgress

__all__ = [
    # Legado
    "PaperCardWidget",
    "StatusBarWidget",
    # Design System ScholarReview
    "EditorialCard",
    "PrimaryButton",
    "SecondaryButton",
    "GhostButton",
    "IconButton",
    "Badge",
    "TextField",
    "TextArea",
    "Select",
    "EditorialProgress",
]
