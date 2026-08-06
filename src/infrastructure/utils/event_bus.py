#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Barramento de Eventos (EventBus) Pub/Sub Thread-Safe.
Permite o desacoplar a emissão de eventos de domínio dos assinantes da interface gráfica ou logs.
"""

import logging
from collections import defaultdict
from threading import RLock
from typing import Callable, Any, Dict, List, Type

logger: logging.Logger = logging.getLogger(__name__)


class EventBus:
    """
    Barramento de eventos com suporte a múltiplos assinantes por tipo de evento.
    Garante sincronização thread-safe e isolamento de exceções nos handlers.
    """

    def __init__(self) -> None:
        self._subscribers: Dict[Type[Any], List[Callable[[Any], None]]] = defaultdict(list)
        self._lock: RLock = RLock()

    def subscribe(self, event_type: Type[Any], handler: Callable[[Any], None]) -> None:
        """Inscreve um handler para ser notificado quando eventos do tipo event_type forem publicados."""
        with self._lock:
            if handler not in self._subscribers[event_type]:
                self._subscribers[event_type].append(handler)
                logger.debug(f"Handler '{handler.__name__}' inscrito para evento '{event_type.__name__}'.")

    def unsubscribe(self, event_type: Type[Any], handler: Callable[[Any], None]) -> None:
        """Remove a inscrição de um handler."""
        with self._lock:
            if handler in self._subscribers[event_type]:
                self._subscribers[event_type].remove(handler)
                logger.debug(f"Handler '{handler.__name__}' removido do evento '{event_type.__name__}'.")

    def publish(self, event: Any) -> None:
        """Publica um evento para todos os assinantes registrados para o seu tipo."""
        event_type = type(event)
        with self._lock:
            handlers = list(self._subscribers.get(event_type, []))

        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.exception(f"Erro ao executar handler '{handler}' para evento '{event_type.__name__}': {e}")

    def clear(self) -> None:
        """Remove todas as inscrições do barramento."""
        with self._lock:
            self._subscribers.clear()
