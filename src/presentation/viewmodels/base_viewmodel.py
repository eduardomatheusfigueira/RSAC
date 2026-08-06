#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Classe Base para ViewModels (BaseViewModel) no Padrão MVVM.
Oferece gerenciamento reativo de estado e registro de ouvintes (listeners) para views.
"""

import logging
from typing import Callable, List, TypeVar, Generic

T = TypeVar("T")
logger: logging.Logger = logging.getLogger(__name__)


class BaseViewModel(Generic[T]):
    """
    Classe abstrata base para ViewModels no RSAC.
    """

    def __init__(self, initial_state: T) -> None:
        self._state: T = initial_state
        self._listeners: List[Callable[[T], None]] = []

    @property
    def state(self) -> T:
        """Estado reativo atual exposto para a View."""
        return self._state

    def add_listener(self, listener: Callable[[T], None]) -> None:
        """Inscreve uma função callback da View para reagir a mudanças de estado."""
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[T], None]) -> None:
        """Remove a inscrição de uma função callback."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    def notify(self) -> None:
        """Notifica todas as Views inscritas sobre alterações no estado."""
        for listener in self._listeners:
            try:
                listener(self._state)
            except Exception as e:
                logger.error(f"Erro ao notificar listener no ViewModel: {e}")
