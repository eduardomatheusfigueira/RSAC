#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Logger Estruturado em Formato JSON (StructuredLogger).
Adiciona campos estruturados (correlation_id, modulo, timestamp ISO8601) às mensagens de log.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional


class JSONFormatter(logging.Formatter):
    """Formatador de log que converte os registros em JSON estruturado."""

    def __init__(self, correlation_id: Optional[str] = None) -> None:
        super().__init__()
        self.correlation_id: str = correlation_id or str(uuid.uuid4())[:8]

    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "correlation_id": getattr(record, "correlation_id", self.correlation_id),
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)


def setup_structured_logging(correlation_id: Optional[str] = None, level: int = logging.INFO) -> str:
    """Configura o logger raiz para emitir logs no formato JSON estruturado."""
    cid = correlation_id or str(uuid.uuid4())[:8]
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    formatter = JSONFormatter(correlation_id=cid)

    # Atualiza handlers existentes para usar o novo formatador
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)

    return cid
