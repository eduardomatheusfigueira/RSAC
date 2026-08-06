"""
Entidades puras de domínio, eventos e exceções da aplicação RSAC.
"""

from src.core.domain.entities import Paper, Protocol, Decision, ScreeningSession
from src.core.domain.events import (
    ScreeningRequested,
    ScreeningCompleted,
    BatchScreeningProgress,
    HarvestStarted,
    HarvestCompleted,
)
from src.core.domain.exceptions import (
    DomainException,
    PaperNotFoundException,
    InvalidDecisionException,
    QuotaExhaustedException,
)

__all__ = [
    "Paper",
    "Protocol",
    "Decision",
    "ScreeningSession",
    "ScreeningRequested",
    "ScreeningCompleted",
    "BatchScreeningProgress",
    "HarvestStarted",
    "HarvestCompleted",
    "DomainException",
    "PaperNotFoundException",
    "InvalidDecisionException",
    "QuotaExhaustedException",
]
