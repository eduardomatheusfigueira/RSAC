#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Repositório de Arquivos PDF no Sistema de Arquivos (FileSystemPDFRepository).
Gerencia a leitura, salvamento em disco de textos de PDFs e otimização por LRUCache.
"""

import os
import logging
from typing import Optional
from src.core.ports.repositories import PDFRepository
from src.infrastructure.utils.lru_cache import LRUCache
from src.infrastructure.utils.text_sanitizer import sanitize_text

logger: logging.Logger = logging.getLogger(__name__)


class FileSystemPDFRepository(PDFRepository):
    """
    Implementação concreta de PDFRepository para ler e salvar arquivos .txt extraídos de PDFs no disco.
    Utiliza LRUCache para evitar reler o disco continuamente.
    """

    def __init__(self, pdf_dir: str, cache_max_size: int = 500) -> None:
        self.pdf_dir: str = pdf_dir
        self.cache: LRUCache[str, str] = LRUCache[str, str](max_size=cache_max_size)

    def _get_txt_path(self, paper_id: str) -> str:
        """Monta o caminho do arquivo de texto do PDF."""
        return os.path.join(self.pdf_dir, f"{paper_id}_texto.txt")

    def get_extracted_text(self, paper_id: str) -> Optional[str]:
        """Obtém o texto do PDF, priorizando o LRUCache em memória antes de acessar o disco."""
        # 1. Tenta recuperar do cache LRU em memória
        cached_text = self.cache.get(paper_id)
        if cached_text is not None:
            return cached_text

        # 2. Se ausente no cache, busca no disco
        txt_path = self._get_txt_path(paper_id)
        if os.path.exists(txt_path):
            try:
                with open(txt_path, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
                sanitized = sanitize_text(text)
                self.cache.put(paper_id, sanitized)
                return sanitized
            except Exception as e:
                logger.error(f"Erro ao ler arquivo de texto de PDF no disco '{txt_path}': {e}")

        return None

    def save_extracted_text(self, paper_id: str, text: str) -> None:
        """Salva o texto extraído do PDF no disco e atualiza o LRUCache."""
        sanitized = sanitize_text(text)
        os.makedirs(self.pdf_dir, exist_ok=True)
        txt_path = self._get_txt_path(paper_id)

        try:
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(sanitized)
            self.cache.put(paper_id, sanitized)
            logger.debug(f"Texto do PDF para o artigo ID '{paper_id}' salvo em '{txt_path}'.")
        except Exception as e:
            logger.error(f"Erro ao salvar texto do PDF no disco '{txt_path}': {e}")
            raise

    def pdf_exists(self, paper_id: str) -> bool:
        """Verifica se o arquivo PDF ou seu texto extraído existem localmente."""
        txt_path = self._get_txt_path(paper_id)
        pdf_path = os.path.join(self.pdf_dir, f"{paper_id}.pdf")
        return os.path.exists(txt_path) or os.path.exists(pdf_path)
