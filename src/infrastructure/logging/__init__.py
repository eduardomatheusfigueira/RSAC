"""
Módulo de Logging Estruturado.
"""

from src.infrastructure.logging.structured_logger import JSONFormatter, setup_structured_logging

__all__ = [
    "JSONFormatter",
    "setup_structured_logging",
]
