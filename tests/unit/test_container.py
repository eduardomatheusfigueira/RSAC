#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Testes unitários para o Container de Injeção de Dependências (IoC).
"""

import pytest
from src.app.container import Container
from src.infrastructure.utils.event_bus import EventBus
from src.core.services.screening_service import ScreeningService


def test_container_initialization():
    container = Container(json_db_path="test.json", pdf_dir="pdfs")

    assert isinstance(container.event_bus, EventBus)
    assert isinstance(container.screening_service, ScreeningService)
    assert container.gemini_client is None  # Sem chaves de API passadas


def test_container_with_gemini_keys():
    container = Container(json_db_path="test.json", pdf_dir="pdfs", gemini_keys=["KEY_1", "KEY_2"])

    assert container.gemini_client is not None
