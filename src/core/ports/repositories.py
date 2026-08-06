#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Contratos de Portas de Repositório (Repository Pattern) para o RSAC.
Permite alternar entre persistência em JSON, SQLite, PostgreSQL ou arquivos de PDF sem alterar o core.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from src.core.domain.entities import Paper, Protocol, ScreeningSession


class ProjectRepository(ABC):
    """Interface abstrata para persistência e recuperação do projeto de revisão sistemática."""

    @abstractmethod
    def save_session(self, session: ScreeningSession, filepath: str) -> None:
        """Salva a sessão completa de triagem/extração no arquivo de destino."""
        pass

    @abstractmethod
    def load_session(self, filepath: str) -> ScreeningSession:
        """Carrega a sessão de triagem/extração a partir de um arquivo."""
        pass

    @abstractmethod
    def update_paper(self, paper: Paper) -> None:
        """Atualiza o estado de um artigo no repositório."""
        pass

    @abstractmethod
    def save_protocol(self, protocol: Protocol, filepath: str) -> None:
        """Salva a configuração do protocolo de revisão."""
        pass

    @abstractmethod
    def load_protocol(self, filepath: str) -> Protocol:
        """Carrega o protocolo de revisão."""
        pass


class PDFRepository(ABC):
    """Interface abstrata para gerenciamento e extração de texto de PDFs salvos no disco."""

    @abstractmethod
    def get_extracted_text(self, paper_id: str) -> Optional[str]:
        """Obtém o texto extraído do PDF correspondente ao artigo."""
        pass

    @abstractmethod
    def save_extracted_text(self, paper_id: str, text: str) -> None:
        """Persiste o texto extraído de um PDF no disco/cache."""
        pass

    @abstractmethod
    def pdf_exists(self, paper_id: str) -> bool:
        """Verifica se o arquivo PDF do artigo está disponível localmente."""
        pass
