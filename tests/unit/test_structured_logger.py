#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Testes unitários para o Logger Estruturado JSON.
"""

import json
import logging
import pytest
from src.infrastructure.logging.structured_logger import JSONFormatter


def test_json_formatter():
    formatter = JSONFormatter(correlation_id="TEST_123")
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Mensagem de teste de log",
        args=(),
        exc_info=None,
    )

    formatted_str = formatter.format(record)
    parsed = json.loads(formatted_str)

    assert parsed["level"] == "INFO"
    assert parsed["correlation_id"] == "TEST_123"
    assert parsed["message"] == "Mensagem de teste de log"
    assert "timestamp" in parsed
