#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Cache LRU (Least Recently Used) Genérico e Thread-Safe.
Substitui dicionários ilimitados em memória para evitar vazamento de memória (Memory Leak).
Fornece compatibilidade total com métodos de dicionário Python (__getitem__, __setitem__, etc.).
"""

from collections import OrderedDict
from threading import RLock
from typing import TypeVar, Generic, Optional, Any, Iterator

K = TypeVar("K")
V = TypeVar("V")


class LRUCache(Generic[K, V]):
    """
    Cache thread-safe com limite de capacidade e política de despejo LRU.
    """

    def __init__(self, max_size: int = 500) -> None:
        if max_size <= 0:
            raise ValueError("O tamanho máximo do LRUCache deve ser superior a zero.")
        self._max_size: int = max_size
        self._data: OrderedDict[K, V] = OrderedDict()
        self._lock: RLock = RLock()

    @property
    def max_size(self) -> int:
        """Capacidade máxima suportada pelo cache."""
        return self._max_size

    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        """Recupera um valor do cache e atualiza seu uso recente. Retorna default se ausente."""
        with self._lock:
            if key not in self._data:
                return default
            self._data.move_to_end(key)
            return self._data[key]

    def put(self, key: K, value: V) -> None:
        """Insere ou atualiza uma chave no cache, removendo o elemento menos recente se cheio."""
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
            else:
                if len(self._data) >= self._max_size:
                    self._data.popitem(last=False)
            self._data[key] = value

    def clear(self) -> None:
        """Remove todos os elementos do cache."""
        with self._lock:
            self._data.clear()

    # ──────────────────────────────────────────────────────────────────────────
    # Métodos Mágicos para Compatibilidade com Dicionários Python (dict-like API)
    # ──────────────────────────────────────────────────────────────────────────

    def __getitem__(self, key: K) -> V:
        with self._lock:
            if key not in self._data:
                raise KeyError(key)
            self._data.move_to_end(key)
            return self._data[key]

    def __setitem__(self, key: K, value: V) -> None:
        self.put(key, value)

    def __contains__(self, key: Any) -> bool:
        with self._lock:
            return key in self._data

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def __delitem__(self, key: K) -> None:
        with self._lock:
            del self._data[key]

    def __iter__(self) -> Iterator[K]:
        with self._lock:
            return iter(list(self._data.keys()))

    def __repr__(self) -> str:
        with self._lock:
            return f"LRUCache(max_size={self._max_size}, current_size={len(self._data)})"
