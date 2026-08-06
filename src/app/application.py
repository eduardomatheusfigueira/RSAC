#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Orquestrador Principal da Aplicação (RSACApplication).
Gerencia a inicialização, configuração de logging estruturado e ciclo de vida.
"""

import os as _os
import sys as _sys
_workspace_root = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", ".."))
if _workspace_root not in _sys.path:
    _sys.path.insert(0, _workspace_root)

import logging
from typing import Optional, List
from src.app.container import Container
from src.infrastructure.logging.structured_logger import setup_structured_logging

logger: logging.Logger = logging.getLogger(__name__)


class RSACApplication:
    """Orquestrador da aplicação RSAC inicializando container e logging."""

    def __init__(self, json_db_path: str = "revisao_session.json", gemini_keys: Optional[List[str]] = None) -> None:
        self.correlation_id: str = setup_structured_logging()
        logger.info(f"Iniciando RSACApplication (Correlation ID: {self.correlation_id})...")

        self.container: Container = Container(json_db_path=json_db_path, gemini_keys=gemini_keys)

    def run_gui(self) -> None:
        """Inicia a interface gráfica desacoplada (AppWindow)."""
        from src.presentation.app_window import AppWindow
        app = AppWindow(
            project_repo=self.container.project_repo,
            screening_service=self.container.screening_service,
            extraction_service=self.container.extraction_service,
        )
        app.mainloop()


if __name__ == "__main__":
    app_instance = RSACApplication()
    app_instance.run_gui()
