#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Padrão Command para Sistema de Desfazer/Refazer (Undo/Redo).
Permite reverter alterações acidentais de decisões de triagem de artigos.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
import logging

from src.core.domain.entities import Paper, Decision
from src.core.ports.repositories import ProjectRepository

logger: logging.Logger = logging.getLogger(__name__)


class Command(ABC):
    """Interface abstrata base para comandos executáveis e reversíveis."""

    @abstractmethod
    def execute(self) -> None:
        """Executa a ação do comando."""
        pass

    @abstractmethod
    def undo(self) -> None:
        """Reverte a ação executada pelo comando."""
        pass


class UpdatePaperDecisionCommand(Command):
    """Comando concreto para alterar a decisão de elegibilidade de um artigo."""

    def __init__(
        self,
        paper: Paper,
        new_decision: Decision,
        on_paper_updated_callback: Optional[callable] = None,
        repository: Optional[ProjectRepository] = None,
    ) -> None:
        self.paper: Paper = paper
        self.old_decision: Decision = paper.decision
        self.new_decision: Decision = new_decision
        self._callback = on_paper_updated_callback
        self._repo = repository

    def execute(self) -> None:
        """Aplica a nova decisão ao artigo."""
        updated = self.paper.with_decision(self.new_decision)
        if self._callback:
            self._callback(updated)
        if self._repo:
            self._repo.update_paper(updated)
        logger.info(f"Comando executado: Artigo ID '{self.paper.id}' alterado de {self.old_decision.value} para {self.new_decision.value}.")

    def undo(self) -> None:
        """Reverte a decisão para a anterior."""
        reverted = self.paper.with_decision(self.old_decision)
        if self._callback:
            self._callback(reverted)
        if self._repo:
            self._repo.update_paper(reverted)
        logger.info(f"Comando desfeito (Undo): Artigo ID '{self.paper.id}' revertido de {self.new_decision.value} para {self.old_decision.value}.")


class CommandHistory:
    """Gerenciador de pilhas para histórico de comandos (Undo/Redo)."""

    def __init__(self, max_history: int = 50) -> None:
        self._max_history: int = max_history
        self._undo_stack: List[Command] = []
        self._redo_stack: List[Command] = []

    def execute_command(self, command: Command) -> None:
        """Executa um comando e adiciona-o ao histórico de undo, limpando a pilha de redo."""
        command.execute()
        self._undo_stack.append(command)
        if len(self._undo_stack) > self._max_history:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self) -> bool:
        """Desfaz o último comando da pilha."""
        if not self._undo_stack:
            return False
        cmd = self._undo_stack.pop()
        cmd.undo()
        self._redo_stack.append(cmd)
        return True

    def redo(self) -> bool:
        """Refaz o último comando desfeito da pilha."""
        if not self._redo_stack:
            return False
        cmd = self._redo_stack.pop()
        cmd.execute()
        self._undo_stack.append(cmd)
        return True

    @property
    def can_undo(self) -> bool:
        """Retorna True se houver comandos para desfazer."""
        return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        """Retorna True se houver comandos para refazer."""
        return len(self._redo_stack) > 0
