# -*- mode: python ; coding: utf-8 -*-
"""
ConfiguradorRevisao.spec — PyInstaller build specification for RSAC.

Produces a single-file Windows executable that bundles:
- The Tkinter GUI (config_app/main.py)
- All 5 harvesters (BDTD, SciELO, OpenAlex, PubMed, Scopus)
- Clean Architecture layers (src/)
- Embedded fonts (assets/fonts/)
- All Python dependencies (pandas, requests, pypdf, bs4, openpyxl, etc.)
"""

import os

# Absolute path to the workspace root
WORKSPACE = os.path.abspath('.')

a = Analysis(
    ['config_app\\main.py'],
    pathex=[WORKSPACE],
    binaries=[],
    datas=[
        # Embed fonts for the editorial design system
        (os.path.join('assets', 'fonts', '*.ttf'), os.path.join('assets', 'fonts')),
        # Embed harvester default config JSONs (used as templates)
        (os.path.join('bdtd_harvester', 'bdtd_config.json'), 'bdtd_harvester'),
        (os.path.join('scielo_harvester', 'scielo_config.json'), 'scielo_harvester'),
        (os.path.join('openalex_harvester', 'openalex_config.json'), 'openalex_harvester'),
        (os.path.join('pubmed_harvester', 'pubmed_config.json'), 'pubmed_harvester'),
        (os.path.join('scopus_harvester', 'scopus_config.json'), 'scopus_harvester'),
    ],
    hiddenimports=[
        # ── Harvesters ──────────────────────────────────────────────
        'bdtd_harvester',
        'bdtd_harvester.bdtd_harvester',
        'scielo_harvester',
        'scielo_harvester.scielo_harvester',
        'openalex_harvester',
        'openalex_harvester.openalex_harvester',
        'pubmed_harvester',
        'pubmed_harvester.pubmed_harvester',
        'scopus_harvester',
        'scopus_harvester.scopus_harvester',
        # ── config_app internals ────────────────────────────────────
        'config_app',
        'config_app.main',
        'config_app.utils',
        'config_app.utils.path_resolver',
        'config_app.utils.platform_compat',
        'config_app.core',
        'config_app.core.config_schemas',
        # ── Clean Architecture (src/) ───────────────────────────────
        'src',
        'src.core',
        'src.core.domain',
        'src.core.domain.entities',
        'src.core.domain.events',
        'src.core.domain.exceptions',
        'src.core.domain.schemas',
        'src.core.commands',
        'src.core.commands.base_command',
        'src.core.ports',
        'src.core.services',
        'src.core.services.screening_service',
        'src.core.services.extraction_service',
        'src.app',
        'src.app.application',
        'src.app.container',
        'src.infrastructure',
        'src.infrastructure.ai',
        'src.infrastructure.ai.response_parser',
        'src.infrastructure.ai.gemini_client',
        'src.infrastructure.logging',
        'src.infrastructure.logging.structured_logger',
        'src.infrastructure.persistence',
        'src.infrastructure.persistence.json_project_repo',
        'src.infrastructure.persistence.filesystem_pdf_repo',
        'src.infrastructure.utils',
        'src.infrastructure.utils.lru_cache',
        'src.infrastructure.utils.text_sanitizer',
        'src.infrastructure.utils.event_bus',
        'src.presentation',
        'src.presentation.theme',
        'src.presentation.typography',
        'src.presentation.app_window',
        'src.presentation.viewmodels',
        'src.presentation.viewmodels.base_viewmodel',
        'src.presentation.viewmodels.protocol_vm',
        'src.presentation.viewmodels.screening_vm',
        'src.presentation.viewmodels.extraction_vm',
        'src.presentation.views',
        'src.presentation.views.protocol_view',
        'src.presentation.views.screening_view',
        'src.presentation.views.extraction_view',
        'src.presentation.widgets',
        'src.presentation.widgets.paper_card',
        'src.presentation.widgets.status_bar',
        'src.presentation.widgets.card',
        'src.presentation.widgets.button',
        'src.presentation.widgets.badge',
        'src.presentation.widgets.input',
        'src.presentation.widgets.progress',
        # ── Third-party dynamic imports ─────────────────────────────
        'windnd',
        'openpyxl',
        'bs4',
        'requests',
        'pypdf',
        'pandas',
        'pandas.io.formats.excel',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Remove heavy packages not needed at runtime
        'matplotlib',
        'scipy',
        'numpy.testing',
        'pytest',
        '_pytest',
        'IPython',
        'notebook',
        'docutils',
        'sphinx',
        'setuptools',
        'pip',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='RSAC',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon=os.path.join('assets', 'app_icon.ico'),
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
