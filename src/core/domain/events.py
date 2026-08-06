#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Eventos de Domínio (Domain Events) da aplicação RSAC.
Utilizados para desacoplar a execução de negócios da atualização de componentes da UI.
"""

from dataclasses import dataclass
from typing import Optional
from src.core.domain.entities import Paper


@dataclass(frozen=True)
class ScreeningRequested:
    """Evento disparado quando uma triagem para um artigo específico é solicitada."""
    paper_id: str


@dataclass(frozen=True)
class ScreeningCompleted:
    """Evento disparado quando a triagem de um artigo é concluída (manualmente ou via IA)."""
    paper: Paper
    suggested_by_ai: bool = False


@dataclass(frozen=True)
class BatchScreeningProgress:
    """Evento disparado periodicamente durante o progresso da triagem automatizada em lote."""
    current: int
    total: int
    paper_id: str
    message: Optional[str] = None


@dataclass(frozen=True)
class HarvestStarted:
    """Evento disparado ao iniciar a coleta em uma base bibliográfica."""
    source: str
    keyword: str


@dataclass(frozen=True)
class HarvestCompleted:
    """Evento disparado ao concluir a coleta em uma base bibliográfica."""
    source: str
    keyword: str
    records_saved: int
