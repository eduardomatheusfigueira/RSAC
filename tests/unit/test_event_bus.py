#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Testes unitários para o Barramento de Eventos (EventBus).
"""

import pytest
from src.infrastructure.utils.event_bus import EventBus
from src.core.domain.events import HarvestStarted, HarvestCompleted
from src.core.domain.entities import Paper, Decision


def test_event_bus_subscribe_and_publish():
    bus = EventBus()
    received_events = []

    def handle_harvest_started(event: HarvestStarted):
        received_events.append(event)

    bus.subscribe(HarvestStarted, handle_harvest_started)

    event = HarvestStarted(source="SciELO", keyword="planejamento urbano")
    bus.publish(event)

    assert len(received_events) == 1
    assert received_events[0].source == "SciELO"
    assert received_events[0].keyword == "planejamento urbano"


def test_event_bus_multiple_handlers():
    bus = EventBus()
    counter = {"h1": 0, "h2": 0}

    def h1(event: HarvestCompleted):
        counter["h1"] += 1

    def h2(event: HarvestCompleted):
        counter["h2"] += 1

    bus.subscribe(HarvestCompleted, h1)
    bus.subscribe(HarvestCompleted, h2)

    bus.publish(HarvestCompleted(source="PubMed", keyword="causalidade", records_saved=42))

    assert counter["h1"] == 1
    assert counter["h2"] == 1


def test_event_bus_unsubscribe():
    bus = EventBus()
    logs = []

    def handler(event: HarvestStarted):
        logs.append(event.source)

    bus.subscribe(HarvestStarted, handler)
    bus.publish(HarvestStarted(source="BDTD", keyword="teste"))
    assert len(logs) == 1

    bus.unsubscribe(HarvestStarted, handler)
    bus.publish(HarvestStarted(source="Scopus", keyword="teste"))
    assert len(logs) == 1
