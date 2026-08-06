"""
Módulo de persistência de infraestrutura (Repositório JSON e Repositório do Sistema de Arquivos de PDF).
"""

from src.infrastructure.persistence.json_project_repo import JSONProjectRepository
from src.infrastructure.persistence.filesystem_pdf_repo import FileSystemPDFRepository

__all__ = [
    "JSONProjectRepository",
    "FileSystemPDFRepository",
]
