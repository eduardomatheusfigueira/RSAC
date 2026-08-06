"""
Módulo de infraestrutura de Inteligência Artificial (Cliente Gemini e Parser de Resposta).
"""

from src.infrastructure.ai.response_parser import JSONResponseParser
from src.infrastructure.ai.gemini_client import GeminiClient

__all__ = [
    "JSONResponseParser",
    "GeminiClient",
]
