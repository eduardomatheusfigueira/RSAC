#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Widget Reutilizável de Card do Artigo (PaperCardWidget).
Exibe título, autores, ano, resumo e status de decisão de um artigo.

Estilizado com Design System ScholarReview (monocromático).
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional
from src.core.domain.entities import Paper, Decision
from src.presentation.theme import PALETTE


class PaperCardWidget(ttk.LabelFrame):
    """Componente gráfico para exibição detalhada de um artigo."""

    def __init__(self, parent: tk.Widget, **kwargs) -> None:
        super().__init__(parent, text="Detalhes do Artigo", **kwargs)

        # Configuração de grid
        self.columnconfigure(1, weight=1)

        body_font = ("Inter", 11)
        bold_font = ("Inter", 11, "bold")
        title_font = ("Inter", 12, "bold")

        # 1. Título
        ttk.Label(self, text="Título:", font=bold_font).grid(
            row=0, column=0, sticky=tk.NW, padx=5, pady=2
        )
        self._lbl_title = ttk.Label(
            self, text="", wraplength=600, font=title_font
        )
        self._lbl_title.grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)

        # 2. Autores e Ano
        ttk.Label(self, text="Autores / Ano:", font=body_font).grid(
            row=1, column=0, sticky=tk.NW, padx=5, pady=2
        )
        self._lbl_meta = ttk.Label(self, text="", font=body_font)
        self._lbl_meta.grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)

        # 3. Base / Revista
        ttk.Label(self, text="Fonte / Revista:", font=body_font).grid(
            row=2, column=0, sticky=tk.NW, padx=5, pady=2
        )
        self._lbl_source = ttk.Label(self, text="", font=body_font)
        self._lbl_source.grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)

        # 4. Decisão
        ttk.Label(self, text="Decisão Atual:", font=bold_font).grid(
            row=3, column=0, sticky=tk.NW, padx=5, pady=2
        )
        self._lbl_decision = ttk.Label(
            self, text="Pendente", font=bold_font,
            foreground=PALETTE["outline"],
        )
        self._lbl_decision.grid(row=3, column=1, sticky=tk.W, padx=5, pady=2)

        # 5. Resumo (Text widget)
        ttk.Label(self, text="Resumo:", font=body_font).grid(
            row=4, column=0, sticky=tk.NW, padx=5, pady=2
        )
        self._txt_abstract = tk.Text(
            self, wrap=tk.WORD, height=8, width=60,
            bg=PALETTE["paper_white"],
            fg=PALETTE["on_surface"],
            font=body_font,
            relief="solid",
            borderwidth=1,
            highlightthickness=1,
            highlightbackground=PALETTE["border"],
            highlightcolor=PALETTE["primary"],
            insertbackground=PALETTE["primary"],
        )
        self._txt_abstract.grid(row=4, column=1, sticky=tk.NSEW, padx=5, pady=2)

    def display_paper(self, paper: Optional[Paper]) -> None:
        """Atualiza o widget para exibir as informações do artigo especificado."""
        if not paper:
            self._lbl_title.config(text="")
            self._lbl_meta.config(text="")
            self._lbl_source.config(text="")
            self._lbl_decision.config(
                text="Sem seleção", foreground=PALETTE["outline"]
            )
            self._txt_abstract.delete("1.0", tk.END)
            return

        self._lbl_title.config(text=paper.title)
        self._lbl_meta.config(text=f"{paper.authors} ({paper.year})")
        self._lbl_source.config(text=f"{paper.source} - {paper.institution}")

        if paper.decision == Decision.INCLUDED:
            self._lbl_decision.config(
                text="INCLUÍDO", foreground=PALETTE["primary"]
            )
        elif paper.decision == Decision.EXCLUDED:
            self._lbl_decision.config(
                text="EXCLUÍDO", foreground=PALETTE["on_surface_v"]
            )
        else:
            self._lbl_decision.config(
                text="PENDENTE", foreground=PALETTE["outline"]
            )

        self._txt_abstract.delete("1.0", tk.END)
        self._txt_abstract.insert(tk.END, paper.abstract or "Sem resumo disponível.")
