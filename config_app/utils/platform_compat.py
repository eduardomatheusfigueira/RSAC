#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
platform_compat.py — Compatibilidade cross-platform para o RSAC.

Encapsula todo código específico de SO (Windows, macOS, Linux)
em funções com fallback gracioso, eliminando erros em plataformas
não suportadas.
"""

import os
import sys
import subprocess
import logging

logger = logging.getLogger(__name__)


def configure_dpi_awareness():
    """
    Configura DPI awareness no Windows para interfaces Tkinter nítidas.
    Em outros SOs, não faz nada (Retina/HiDPI é gerenciado pelo Tk).
    """
    if sys.platform != "win32":
        return

    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass
    except Exception:
        pass


def open_file_with_default_app(file_path: str):
    """
    Abre um arquivo com o aplicativo padrão do sistema operacional.

    - Windows: os.startfile()
    - macOS: subprocess 'open'
    - Linux: subprocess 'xdg-open'

    Args:
        file_path: Caminho absoluto ou relativo para o arquivo.

    Raises:
        FileNotFoundError: Se o arquivo não existe.
        OSError: Se não foi possível abrir o arquivo.
    """
    abs_path = os.path.abspath(file_path)

    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"Arquivo não encontrado: {abs_path}")

    try:
        if sys.platform == "win32":
            os.startfile(abs_path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", abs_path])
        else:
            subprocess.Popen(["xdg-open", abs_path])
    except Exception as e:
        logger.error(f"Erro ao abrir arquivo {abs_path}: {e}")
        raise OSError(f"Não foi possível abrir o arquivo: {e}") from e


def get_downloads_dir() -> str:
    """
    Retorna o diretório de Downloads do usuário de forma cross-platform.

    Returns:
        Caminho absoluto para o diretório de Downloads.
    """
    return os.path.join(os.path.expanduser("~"), "Downloads")
