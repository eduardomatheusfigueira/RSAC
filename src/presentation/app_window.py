#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Janela Principal da Aplicação RSAC (AppWindow).
Janela magra baseada em ttk.Notebook integrando as 3 Views e ViewModels desacopladas.
"""

import os as _os
import sys as _sys
_workspace_root = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", ".."))
if _workspace_root not in _sys.path:
    _sys.path.insert(0, _workspace_root)

import tkinter as tk
from tkinter import ttk
from typing import Optional

from src.core.ports.repositories import ProjectRepository
from src.core.services.screening_service import ScreeningService
from src.core.services.extraction_service import ExtractionService

from src.presentation.viewmodels.protocol_vm import ProtocolViewModel
from src.presentation.viewmodels.screening_vm import ScreeningViewModel
from src.presentation.viewmodels.extraction_vm import ExtractionViewModel

from src.presentation.views.protocol_view import ProtocolView
from src.presentation.views.screening_view import ScreeningView
from src.presentation.views.extraction_view import ExtractionView


from src.presentation.typography import register_fonts
from src.presentation.theme import apply_theme


class AppWindow(tk.Tk):
    """Janela principal magra da aplicação RSAC no padrão MVVM."""

    def __init__(
        self,
        project_repo: Optional[ProjectRepository] = None,
        screening_service: Optional[ScreeningService] = None,
        extraction_service: Optional[ExtractionService] = None,
        *args,
        **kwargs
    ) -> None:
        super().__init__(*args, **kwargs)

        self.title("RSAC - Revisão Sistemática Assistida por Computador (MVVM)")
        self.geometry("1100x750")
        self.minsize(900, 600)

        # ── ScholarReview Design System ──────────────────────────────
        register_fonts()
        self._tokens = apply_theme(self)

        # ViewModels
        self.protocol_vm = ProtocolViewModel(repository=project_repo)
        self.screening_vm = ScreeningViewModel(service=screening_service or ScreeningService())
        self.extraction_vm = ExtractionViewModel(service=extraction_service or ExtractionService())

        self._build_ui()

    def _build_ui(self) -> None:
        """Inicializa e empacota as abas no ttk.Notebook."""
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Aba 1: Protocolo
        self.tab_protocol = ProtocolView(self.notebook, viewmodel=self.protocol_vm)
        self.notebook.add(self.tab_protocol, text=" 1. Protocolo de Pesquisa ")

        # Aba 2: Triagem (Triagem 1)
        self.tab_screening = ScreeningView(self.notebook, viewmodel=self.screening_vm)
        self.notebook.add(self.tab_screening, text=" 2. Triagem (Triagem 1) ")

        # Aba 3: Extração (Triagem 2)
        self.tab_extraction = ExtractionView(self.notebook, viewmodel=self.extraction_vm)
        self.notebook.add(self.tab_extraction, text=" 3. Extração e Análise (Triagem 2) ")


def launch_app() -> None:
    """Função de conveniência para inicializar a aplicação MVVM."""
    app = AppWindow()
    app.mainloop()


if __name__ == "__main__":
    launch_app()
