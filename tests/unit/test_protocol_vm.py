#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Testes unitários para o ProtocolViewModel.
"""

import pytest
from src.presentation.viewmodels.protocol_vm import ProtocolViewModel, ProtocolState


def test_protocol_viewmodel_state_updates():
    vm = ProtocolViewModel()
    states_received = []

    vm.add_listener(lambda s: states_received.append(s.title))

    vm.set_title("Revisão de Redes Neurais")
    assert vm.state.title == "Revisão de Redes Neurais"
    assert len(states_received) == 1

    vm.add_inclusion_criterion("Estudos com benchmark público")
    assert "Estudos com benchmark público" in vm.state.inclusion_criteria

    vm.add_exclusion_criterion("Artigos anteriores a 2015")
    assert "Artigos anteriores a 2015" in vm.state.exclusion_criteria

    vm.add_keyword("Deep Learning")
    assert "Deep Learning" in vm.state.keywords


def test_protocol_viewmodel_remove_criteria():
    vm = ProtocolViewModel()
    vm.add_inclusion_criterion("C1")
    vm.add_inclusion_criterion("C2")

    assert len(vm.state.inclusion_criteria) == 2

    vm.remove_inclusion_criterion("C1")
    assert vm.state.inclusion_criteria == ["C2"]
