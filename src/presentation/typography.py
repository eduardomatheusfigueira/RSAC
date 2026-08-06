#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
ScholarReview Design System — Registro e Resolução Tipográfica.

Gerencia o carregamento de fontes TTF embarcadas (EB Garamond, Inter,
Material Symbols) e fornece resolução inteligente com fallbacks
cross-platform quando as fontes customizadas não estão disponíveis.
"""

import os
import sys
import logging
from typing import Optional, Tuple, Dict, List
from functools import lru_cache

logger = logging.getLogger(__name__)

# ── Localização do diretório de fontes ───────────────────────────────

def _get_fonts_dir() -> str:
    """Retorna o caminho absoluto para assets/fonts/."""
    if getattr(sys, 'frozen', False):
        # PyInstaller bundle
        base = os.path.dirname(sys.executable)
    else:
        # Desenvolvimento: raiz do workspace (2 níveis acima de src/presentation/)
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(base, "assets", "fonts")


# ── Font Stacks (ordem de preferência) ───────────────────────────────

FONT_STACKS: Dict[str, List[str]] = {
    "display": [
        "EB Garamond", "Cormorant Garamond", "Libre Caslon Text",
        "Georgia", "Times New Roman",
    ],
    "body": [
        "Inter", "Segoe UI", "Helvetica Neue", "SF Pro Text",
        "Roboto", "Ubuntu", "Arial",
    ],
    "mono": [
        "JetBrains Mono", "Cascadia Code", "Consolas",
        "SF Mono", "Courier New",
    ],
}


# ── Cache de famílias disponíveis ────────────────────────────────────

_available_families: Optional[set] = None


def _get_available_families() -> set:
    """Carrega o conjunto de famílias de fontes disponíveis no Tk atual."""
    global _available_families
    if _available_families is None:
        try:
            import tkinter.font as tkfont
            _available_families = set(tkfont.families())
        except Exception:
            _available_families = set()
    return _available_families


def _register_ttf_fonts() -> None:
    """
    Tenta registrar fontes TTF embarcadas no Windows via ctypes.

    No Windows, usa AddFontResourceExW para tornar as fontes disponíveis
    à sessão atual do processo (não instala permanentemente).
    """
    fonts_dir = _get_fonts_dir()
    if not os.path.isdir(fonts_dir):
        logger.debug("Diretório de fontes não encontrado: %s", fonts_dir)
        return

    if sys.platform != "win32":
        logger.debug("Registro de fontes TTF via ctypes disponível apenas no Windows.")
        return

    try:
        import ctypes
        FR_PRIVATE = 0x10  # Apenas para este processo

        ttf_files = [f for f in os.listdir(fonts_dir) if f.lower().endswith(".ttf")]
        if not ttf_files:
            return

        gdi32 = ctypes.windll.gdi32
        for ttf in ttf_files:
            ttf_path = os.path.join(fonts_dir, ttf)
            result = gdi32.AddFontResourceExW(ttf_path, FR_PRIVATE, 0)
            if result > 0:
                logger.info("Fonte registrada: %s (%d famílias)", ttf, result)
            else:
                logger.warning("Falha ao registrar fonte: %s", ttf)

        # Invalida o cache de famílias para re-detectar
        global _available_families
        _available_families = None

    except Exception as e:
        logger.warning("Erro ao registrar fontes TTF: %s", e)


def register_fonts() -> None:
    """
    Ponto de entrada principal: registra fontes embarcadas e atualiza o cache.

    Deve ser chamado uma vez, antes de apply_theme(), idealmente no boot
    da aplicação.
    """
    _register_ttf_fonts()
    # Força recarga do cache
    _get_available_families()
    logger.info(
        "Fontes disponíveis após registro: %d famílias",
        len(_get_available_families())
    )


# ── Resolução de fonte ───────────────────────────────────────────────

@lru_cache(maxsize=16)
def resolve_font_family(stack_name: str) -> str:
    """
    Resolve a primeira família de fonte disponível no stack especificado.

    Args:
        stack_name: Nome do stack ("display", "body", "mono").

    Returns:
        Nome da família de fonte disponível, ou fallback padrão do Tk.
    """
    stack = FONT_STACKS.get(stack_name)
    if not stack:
        return "TkDefaultFont"

    available = _get_available_families()

    for family in stack:
        if family in available:
            logger.debug("Stack '%s' resolvido para: %s", stack_name, family)
            return family

    # Nenhuma encontrada — retorna fallback absoluto
    fallback = stack[-1] if stack else "TkDefaultFont"
    logger.warning(
        "Nenhuma fonte do stack '%s' encontrada. Usando fallback: %s",
        stack_name, fallback
    )
    return fallback


def get_display_font(size: int = 28, weight: str = "normal") -> Tuple[str, int, str]:
    """Retorna tupla (family, size, weight) para fontes display (títulos)."""
    return (resolve_font_family("display"), size, weight)


def get_body_font(size: int = 11, weight: str = "normal") -> Tuple[str, int, str]:
    """Retorna tupla (family, size, weight) para fontes body (corpo de texto)."""
    return (resolve_font_family("body"), size, weight)


def get_mono_font(size: int = 11, weight: str = "normal") -> Tuple[str, int, str]:
    """Retorna tupla (family, size, weight) para fontes monospace."""
    return (resolve_font_family("mono"), size, weight)


def get_icon_font(size: int = 18) -> Tuple[str, int, str]:
    """Retorna tupla para a fonte Material Symbols Outlined."""
    available = _get_available_families()
    if "Material Symbols Outlined" in available:
        return ("Material Symbols Outlined", size, "normal")
    # Fallback: retorna body font (ícones serão texto)
    return (resolve_font_family("body"), size, "normal")
