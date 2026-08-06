#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Hierarquia de Exceções de Domínio do RSAC.
Permite captura tipada e tratamento apropriado sem dependência de strings genéricas.
"""


class DomainException(Exception):
    """Exceção base para todos os erros de regras de negócio do RSAC."""
    pass


class PaperNotFoundException(DomainException):
    """Exceção lançada quando um artigo solicitado não é localizado na sessão ou banco."""
    def __init__(self, paper_id: str) -> None:
        self.paper_id: str = paper_id
        super().__init__(f"Artigo com ID '{paper_id}' não foi encontrado.")


class InvalidDecisionException(DomainException):
    """Exceção lançada ao tentar atribuir um valor de decisão inválido."""
    def __init__(self, decision_value: str) -> None:
        self.decision_value: str = decision_value
        super().__init__(f"Decisão '{decision_value}' é inválida.")


class QuotaExhaustedException(DomainException):
    """Exceção lançada quando a cota de todas as chaves de API da IA foi atingida."""
    def __init__(self, message: str = "Todas as chaves de API atingiram o limite de quota.") -> None:
        super().__init__(message)


class ModelUnavailableException(DomainException):
    """Exceção lançada quando o modelo de IA está temporariamente indisponível (HTTP 503)."""
    def __init__(self, model_name: str) -> None:
        self.model_name: str = model_name
        super().__init__(f"Modelo de IA '{model_name}' está temporariamente indisponível.")
