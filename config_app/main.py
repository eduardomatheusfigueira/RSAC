#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Systematic Review Configuration GUI
Author: Antigravity AI
Description: A desktop application for configuring systematic reviews and generating JSON config files.
"""

# Ensure parent directory (workspace root) is in sys.path so config_app can be imported
# This MUST happen before any `from config_app.*` imports
import os as _os
import sys as _sys
_workspace_root = _os.path.dirname(_os.path.abspath(__file__))
if not getattr(_sys, 'frozen', False):
    _workspace_root = _os.path.abspath(_os.path.join(_workspace_root, ".."))
if _workspace_root not in _sys.path:
    _sys.path.insert(0, _workspace_root)

# Platform-specific DPI awareness (cross-platform safe)
from config_app.utils.platform_compat import configure_dpi_awareness, open_file_with_default_app
configure_dpi_awareness()

import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from tkinter import filedialog
from tkinter import scrolledtext
import json
import os
import sys
import unicodedata
import re
import pandas as pd
import webbrowser
import time
import subprocess
import threading
import queue
import requests
import pypdf
import urllib.parse
from datetime import datetime
import logging

# Centralized path resolution and workspace setup
from config_app.utils.path_resolver import (
    BASE_DIR, resolve_path, resolve_db, resolve_config,
    fix_win_long_path, ensure_workspace_in_sys_path,
    DEFAULT_DB_NAMES, DEFAULT_EXPORT_NAMES,
)
ensure_workspace_in_sys_path()

# Import harvesters natively so PyInstaller bundles them and execution works inside single process
try:
    from bdtd_harvester.bdtd_harvester import run_harvest as bdtd_run_harvest
except ImportError:
    bdtd_run_harvest = None

try:
    from scielo_harvester.scielo_harvester import run_harvest as scielo_run_harvest
except ImportError:
    scielo_run_harvest = None

try:
    from openalex_harvester.openalex_harvester import run_harvest as openalex_run_harvest
except ImportError:
    openalex_run_harvest = None

try:
    from pubmed_harvester.pubmed_harvester import run_harvest as pubmed_run_harvest
except ImportError:
    pubmed_run_harvest = None

try:
    from scopus_harvester.scopus_harvester import run_harvest as scopus_run_harvest
except ImportError:
    scopus_run_harvest = None


# fix_win_long_path is now imported from config_app.utils.path_resolver


# Helper to sanitize text sent to APIs (removes null bytes & control chars)
def sanitize_text(text):
    """Cleans text of null bytes and non-printable control characters to prevent API rejection."""
    if not text:
        return ""
    if not isinstance(text, str):
        text = str(text)
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    return cleaned.encode('utf-8', 'ignore').decode('utf-8')


# Helper for Drag and Drop on Windows (using windnd package)
def enable_win_dnd(widget, callback):
    """Enables Windows drag-and-drop (WM_DROPFILES) for a Tkinter widget using windnd."""
    if sys.platform != "win32":
        return
        
    try:
        import windnd
        def _setup():
            try:
                windnd.hook_dropfiles(widget, func=callback, force_unicode=True)
            except Exception as ex:
                logging.warning(f"windnd hook error for widget: {ex}")
        widget.after(300, _setup)
    except Exception as e:
        logging.warning(f"windnd module unavailable or failed: {e}")


SYSTEM_PROMPT_RESEARCH_PARTNER = """Você é um pesquisador sênior e metodologista sênior especialista em Revisões Sistemáticas e Mapeamentos Sistemáticos da Literatura, com vasta experiência em metodologias internacionais rigorosas (PRISMA, PRISMA-P, PRISMA-ScR, Cochrane, Campbell Collaboration, CEE/ROSES, EBSE/Kitchenham, Methodi Ordinatio e Umbrella Reviews).

Sua função é atuar como um Parceiro de Pesquisa IA experiente, objetivo, direto, adequado e completo.

Ao receber uma descrição de pesquisa, objetivo ou tema do usuário e o tipo de protocolo selecionado, você deve analisar minuciosamente o contexto científico e gerar uma proposta completa, precisa e de alto nível acadêmico para preenchimento de TODOS os campos do protocolo informado, além de sugerir questões/campos de extração de dados essenciais para o estudo.

Diretrizes de resposta:
1. Responda ESTRITAMENTE em formato JSON válido, sem texto explicativo ou markdown fora do JSON.
2. Seja objetivo, direto e completo, utilizando linguagem acadêmica precisa.
3. Preencha todos os campos do formulário do protocolo selecionado de acordo com as chaves solicitadas.
4. Para o campo 'busca' (Estratégia de Busca Booleana):
   a. Estruture a busca em no máximo 2 a 3 eixos conceituais (ex: Eixo Metodologia/Intervenção AND Eixo Objeto/Tema).
   b. Dentro de cada eixo, agrupe sinônimos e variações com o operador 'OR' entre parênteses, combinando termos em Português e Inglês (ex: '("avaliação de impacto" OR "inferência causal" OR "causalidade" OR "impact evaluation") AND ("desenvolvimento regional" OR "planejamento regional" OR "regional development")').
   c. Evite o uso de mais de 3 operadores 'AND' simultâneos ou aspas rígidas em termos metodológicos raros, para prevenir a sobrespecificidade e a recuperação zerada de artigos.
   d. Forneça APENAS as strings booleanas puras. NÃO inclua rótulos ou prefixos como 'SciELO/BDTD:', 'PubMed:', '[SciELO]:', 'Busca:' etc.
5. Defina critérios de inclusão e exclusão claros, operacionais e objetivos.
6. Defina 'campos_extracao' (questões de extração de dados) relevantes, abrangentes e específicos para responder aos objetivos da revisão (itens separados por \\n).
"""


class SystematicReviewApp(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title("Configurador de Revisão Sistemática")
        self.geometry("900x650")
        self.minsize(640, 480)
        
        # Define modern color palette and styles
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Primary colors
        self.bg_color = "#f5f6f8"
        self.primary_color = "#1f497d"
        self.accent_color = "#4f81bd"
        self.text_color = "#333333"
        self.white = "#ffffff"
        
        # Configure styles
        self.configure(bg=self.bg_color)
        
        self.style.configure(".", background=self.bg_color, foreground=self.text_color, font=("Segoe UI", 10))
        self.style.configure("TFrame", background=self.bg_color)
        
        # Title Label style
        self.style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"), foreground=self.primary_color, background=self.bg_color)
        self.style.configure("Subtitle.TLabel", font=("Segoe UI", 9, "italic"), foreground="#666666", background=self.bg_color)
        
        # Card style (Frame with white bg)
        self.style.configure("Card.TFrame", background=self.white, relief="solid", borderwidth=1)
        
        # Notebook (Tabs) style
        self.style.configure("TNotebook", background=self.bg_color, borderwidth=0)
        self.style.configure("TNotebook.Tab", font=("Segoe UI", 10, "bold"), padding=[12, 6], background="#e1e4e8")
        self.style.map("TNotebook.Tab",
            background=[("selected", self.primary_color)],
            foreground=[("selected", self.white)]
        )
        
        # Buttons style
        self.style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), foreground=self.white, background=self.primary_color, padding=[10, 6])
        self.style.map("Primary.TButton",
            background=[("active", self.accent_color), ("pressed", "#153358")],
            foreground=[("active", self.white)]
        )
        
        self.style.configure("Secondary.TButton", font=("Segoe UI", 10), background="#e1e4e8", padding=[8, 4])
        
        self.style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"), foreground=self.primary_color, background=self.white)
        self.style.configure("Bold.TLabel", font=("Segoe UI", 10, "bold"))
        
        # Initialize keywords list
        self.keywords = []
        
        # Initialize execution selection variables
        self.var_run_bdtd = tk.BooleanVar(value=True)
        self.var_run_scielo = tk.BooleanVar(value=True)
        self.var_run_openalex = tk.BooleanVar(value=True)
        self.var_run_pubmed = tk.BooleanVar(value=True)
        self.var_run_scopus = tk.BooleanVar(value=True)
        
        # Initialize screening variables
        self.triagem_csv_files = []
        self.inclusion_criteria = []
        self.exclusion_criteria = []
        self.triagem_questions = []
        self.current_session = {
            'arquivos_origem': [],
            'criterios_inclusao': [],
            'criterios_exclusao': [],
            'perguntas': [],
            'campos_extracao': [],
            'trabalhos': []
        }
        self.selected_paper_index = None
        
        # Initialize screening 2 variables (Data Extraction)
        self.campos_extracao = []
        self.selected_paper_index_t2 = None
        self.dynamic_vars_t2 = {}
        self.pdf_download_dir = tk.StringVar(value="Revisão teste/pdfs")
        self.search_matches_t2 = []
        self.current_search_idx_t2 = -1

        # Initialize protocol variables
        self.protocol_widgets = {}
        self.protocol_db_vars = {}

        # Initialize Gemini AI Config
        self.gemini_api_keys = []  # List of API keys for rotation
        self.gemini_current_key_index = 0  # Current key index for rotation
        self.gemini_exhausted_keys = set()  # Keys that hit quota limits this session
        self.gemini_model = tk.StringVar(value="gemini-2.5-flash")
        self.load_gemini_config()

        # Unified JSON file tracking
        self.unified_file_path = None

        # Batch AI Loop control flags
        self.batch_t1_running = False
        self.batch_t1_cancel_requested = False

        # Create components using grid for guaranteed footer visibility
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)  # header
        self.rowconfigure(1, weight=0)  # separator
        self.rowconfigure(2, weight=1)  # notebook (expands)
        self.rowconfigure(3, weight=0)  # separator
        self.rowconfigure(4, weight=0)  # footer (always visible)
        self.create_header()
        self.create_notebook()
        self.create_footer()
        
        # Load defaults
        self.load_default_values()

    def create_header(self):
        """Creates the top header area of the application."""
        header_frame = ttk.Frame(self, padding=(20, 10, 20, 10))
        header_frame.grid(row=0, column=0, sticky="ew")
        header_frame.columnconfigure(0, weight=1)
        
        left_header = ttk.Frame(header_frame)
        left_header.grid(row=0, column=0, sticky="w")

        title_label = ttk.Label(
            left_header, 
            text="Configurador de Revisão Sistemática", 
            style="Title.TLabel"
        )
        title_label.pack(anchor="w")
        
        subtitle_label = ttk.Label(
            left_header, 
            text="Plataforma Integrada para Protocolo, Busca, Triagem e Extração de Dados.", 
            style="Subtitle.TLabel"
        )
        subtitle_label.pack(anchor="w", pady=(2, 0))

        # Gear Icon Button for Harvester Configurations (Top Right)
        btn_config = ttk.Button(
            header_frame,
            text="⚙",
            style="Secondary.TButton",
            width=4,
            command=self.open_harvester_config_window
        )
        btn_config.grid(row=0, column=1, sticky="e", padx=(10, 0))
        
        # Divider line
        divider = ttk.Separator(self, orient="horizontal")
        divider.grid(row=1, column=0, sticky="ew", padx=20)

    def init_harvester_config_window(self):
        """Initializes the harvester configuration window and tabs."""
        if hasattr(self, 'harvester_win') and self.harvester_win is not None and self.harvester_win.winfo_exists():
            return

        self.harvester_win = tk.Toplevel(self)
        self.harvester_win.title("⚙️ Configuração das Fontes de Busca (Harvesters)")
        self.harvester_win.geometry("900x650")
        self.harvester_win.configure(bg=self.bg_color)
        self.harvester_win.protocol("WM_DELETE_WINDOW", self.harvester_win.withdraw)

        # Header inside config window
        top_frame = ttk.Frame(self.harvester_win, padding=15)
        top_frame.pack(fill="x")

        title_lbl = ttk.Label(top_frame, text="⚙️ Configuração das Fontes de Busca (Harvesters)", style="Title.TLabel")
        title_lbl.pack(anchor="w")

        sub_lbl = ttk.Label(top_frame, text="Ajuste os parâmetros de busca, limites, diretórios de banco de dados e chaves de API das fontes.", style="Subtitle.TLabel")
        sub_lbl.pack(anchor="w", pady=(2, 0))

        ttk.Separator(self.harvester_win, orient="horizontal").pack(fill="x", padx=15)

        # Notebook inside config window
        config_notebook = ttk.Notebook(self.harvester_win, padding=10)
        config_notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # Harvester Config Tabs (child of config_notebook)
        self.tab_bdtd = ttk.Frame(config_notebook, padding=15)
        config_notebook.add(self.tab_bdtd, text="BDTD Harvester")
        self.setup_tab_bdtd()

        self.tab_scielo = ttk.Frame(config_notebook, padding=15)
        config_notebook.add(self.tab_scielo, text="SciELO Harvester")
        self.setup_tab_scielo()

        self.tab_openalex = ttk.Frame(config_notebook, padding=15)
        config_notebook.add(self.tab_openalex, text="OpenAlex Harvester")
        self.setup_tab_openalex()

        self.tab_pubmed = ttk.Frame(config_notebook, padding=15)
        config_notebook.add(self.tab_pubmed, text="PubMed Harvester")
        self.setup_tab_pubmed()

        self.tab_scopus = ttk.Frame(config_notebook, padding=15)
        config_notebook.add(self.tab_scopus, text="Scopus Harvester")
        self.setup_tab_scopus()

        # Bottom action bar with Close button
        bottom_bar = ttk.Frame(self.harvester_win, padding=10)
        bottom_bar.pack(fill="x", side="bottom")

        btn_close = ttk.Button(bottom_bar, text="Concluído / Fechar", style="Primary.TButton", command=self.harvester_win.withdraw)
        btn_close.pack(side="right", padx=5)

        # Keep hidden initially
        self.harvester_win.withdraw()

    def open_harvester_config_window(self):
        """Shows the harvester configuration window."""
        if not hasattr(self, 'harvester_win') or self.harvester_win is None or not self.harvester_win.winfo_exists():
            self.init_harvester_config_window()

        self.harvester_win.deiconify()
        self.harvester_win.lift()
        self.harvester_win.focus_force()

        # Center window relative to parent
        try:
            self.harvester_win.update_idletasks()
            pw = self.winfo_width()
            ph = self.winfo_height()
            px = self.winfo_rootx()
            py = self.winfo_rooty()
            w = 900
            h = 650
            x = px + max(0, (pw - w) // 2)
            y = py + max(0, (ph - h) // 2)
            self.harvester_win.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    def _make_scrollable_tab(self, tab_frame):
        """Wraps a tab's content in a scrollable canvas. Returns the inner frame to add widgets to."""
        canvas = tk.Canvas(tab_frame, borderwidth=0, highlightthickness=0, bg=self.bg_color)
        scrollbar = ttk.Scrollbar(tab_frame, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        
        inner_frame = ttk.Frame(canvas, padding=15)
        inner_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas_window = canvas.create_window((0, 0), window=inner_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Keep inner frame width matched to canvas width
        def _configure_width(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind('<Configure>', _configure_width)
        
        # Mouse wheel scrolling (local, not global)
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        def _bind_mw(event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
        def _unbind_mw(event):
            canvas.unbind_all("<MouseWheel>")
        canvas.bind('<Enter>', _bind_mw)
        canvas.bind('<Leave>', _unbind_mw)
        
        return inner_frame

    def create_notebook(self):
        """Creates the main production tabbed area (Notebook) and initializes Harvester Config Window."""
        self.notebook = ttk.Notebook(self, padding=10)
        self.notebook.grid(row=2, column=0, sticky="nsew", padx=5, pady=0)
        
        # Production Tab 1: Protocolo de Pesquisa
        self.tab_protocol = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(self.tab_protocol, text="Protocolo de Pesquisa")
        self.setup_tab_protocol()
        
        # Production Tab 2: Configuração Geral
        self.tab_general = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(self.tab_general, text="Configuração Geral")
        self.setup_tab_general()
        
        # Production Tab 3: Triagem de Trabalhos
        self.tab_triagem = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(self.tab_triagem, text="Triagem de Trabalhos")
        self.setup_tab_triagem()
        
        # Production Tab 4: Triagem Fase 2 - Extração de Dados
        self.tab_triagem_2 = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(self.tab_triagem_2, text="Triagem 2 - Extração")
        self.setup_tab_triagem_2()
        
        # Bind tab change event for auto scanning
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        # Initialize Harvester Config Toplevel Window
        self.init_harvester_config_window()
        
        # Bind tab change event for auto scanning
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

    def on_tab_changed(self, event):
        """Triggers when notebook tab is changed."""
        selected_tab = self.notebook.select()
        if hasattr(self, 'tab_triagem_2') and selected_tab == str(self.tab_triagem_2):
            self.scan_pdf_directory_t2(show_message=False)

    def create_footer(self):
        """Creates the bottom actions and status area."""
        divider = ttk.Separator(self, orient="horizontal")
        divider.grid(row=3, column=0, sticky="ew", padx=20)
        
        footer_frame = ttk.Frame(self, padding=(15, 8, 15, 8))
        footer_frame.grid(row=4, column=0, sticky="ew")
        
        # Status Bar
        self.status_var = tk.StringVar(value="Pronto.")
        status_label = ttk.Label(footer_frame, textvariable=self.status_var, font=("Segoe UI", 9), foreground="#666666")
        status_label.pack(side="left", padx=10)
        
        # Save Button
        save_button = ttk.Button(
            footer_frame, 
            text="Salvar Arquivo JSON", 
            style="Primary.TButton",
            command=self.save_configuration
        )
        save_button.pack(side="right", padx=5)
        
        # Load Button
        load_button = ttk.Button(
            footer_frame, 
            text="Carregar Arquivo JSON", 
            style="Secondary.TButton",
            command=self.load_configuration
        )
        load_button.pack(side="right", padx=5)

        # Export Parts Button
        export_parts_button = ttk.Button(
            footer_frame,
            text="Exportar Partes...",
            style="Secondary.TButton",
            command=self.show_export_parts_window
        )
        export_parts_button.pack(side="right", padx=5)

    def setup_tab_protocol(self):
        """Builds the Research Protocol tab layout."""
        # Main split: Left for protocol selection/controls, Right for the scrollable form
        paned = ttk.Panedwindow(self.tab_protocol, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True)
        
        # Left Panel (Controls)
        left_panel = ttk.Frame(paned, width=240)
        paned.add(left_panel, weight=0)
        
        # 1. Protocol Choice Card
        choice_frame = ttk.LabelFrame(left_panel, text="Escolha do Protocolo", padding=10)
        choice_frame.pack(fill="x", pady=5, padx=5)
        
        ttk.Label(choice_frame, text="Protocolo Metodológico:", style="Bold.TLabel").pack(anchor="w", pady=(0, 5))
        self.cb_protocol_type = ttk.Combobox(choice_frame, values=[
            "PRISMA-P (Saúde)",
            "Campbell (Sociais)",
            "CEE/ROSES (Ecologia)",
            "EBSE (Software)",
            "Umbrella Review (Overview)",
            "Scoping Review (PRISMA-ScR)",
            "Methodi Ordinatio"
        ], state="readonly")
        self.cb_protocol_type.pack(fill="x", pady=(0, 10))
        self.cb_protocol_type.set("PRISMA-P (Saúde)")
        self.cb_protocol_type.bind("<<ComboboxSelected>>", self.on_protocol_type_changed)
        
        # 1.5. AI Research Partner Card
        ai_frame = ttk.LabelFrame(left_panel, text="🤖 Parceiro de Pesquisa (I.A.)", padding=10)
        ai_frame.pack(fill="x", pady=5, padx=5)
        
        ttk.Label(ai_frame, text="Descreva sua pesquisa:", style="Bold.TLabel").pack(anchor="w", pady=(0, 2))
        ttk.Label(ai_frame, text="Tema, objetivos e o que quer investigar:", style="Subtitle.TLabel").pack(anchor="w", pady=(0, 4))
        
        self.txt_ai_research_prompt = scrolledtext.ScrolledText(ai_frame, wrap="word", font=("Segoe UI", 9), height=5)
        self.txt_ai_research_prompt.pack(fill="x", pady=(0, 6))
        
        self.btn_ai_fill_protocol = ttk.Button(
            ai_frame, 
            text="✨ Sugerir Protocolo com I.A.", 
            style="Primary.TButton", 
            command=self.run_ai_protocol_partner
        )
        self.btn_ai_fill_protocol.pack(fill="x", pady=(0, 4))
        
        self.lbl_ai_protocol_status = ttk.Label(ai_frame, text="", style="Subtitle.TLabel", wraplength=210)
        self.lbl_ai_protocol_status.pack(anchor="w")
        
        # 2. File Actions Card
        files_frame = ttk.LabelFrame(left_panel, text="Ações do Protocolo", padding=10)
        files_frame.pack(fill="x", pady=5, padx=5)
        
        btn_load = ttk.Button(files_frame, text="Carregar Protocolo (.json)", style="Secondary.TButton", command=self.load_protocol_json)
        btn_load.pack(fill="x", pady=3)
        
        btn_save = ttk.Button(files_frame, text="Salvar Protocolo (.json)", style="Secondary.TButton", command=self.save_protocol_json)
        btn_save.pack(fill="x", pady=3)
        
        # 3. Next Stage Action Card
        action_frame = ttk.LabelFrame(left_panel, text="Integração e Busca", padding=10)
        action_frame.pack(fill="x", pady=5, padx=5)
        
        btn_advance = ttk.Button(action_frame, text="Gerar Configuração de Busca e Avançar", style="Primary.TButton", command=self.advance_from_protocol)
        btn_advance.pack(fill="x", pady=5)
        
        # Right Panel (Form Area)
        self.protocol_form_container = ttk.LabelFrame(paned, text="Formulário do Protocolo: PRISMA-P", padding=10)
        paned.add(self.protocol_form_container, weight=1)
        
        # Scrollable form setup
        self.protocol_canvas = tk.Canvas(self.protocol_form_container, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.protocol_form_container, orient="vertical", command=self.protocol_canvas.yview)
        scrollbar.pack(side="right", fill="y")
        self.protocol_canvas.pack(side="left", fill="both", expand=True)
        
        self.protocol_form_frame = ttk.Frame(self.protocol_canvas, padding=5)
        self.protocol_form_frame.bind(
            "<Configure>",
            lambda e: self.protocol_canvas.configure(scrollregion=self.protocol_canvas.bbox("all"))
        )
        self.protocol_canvas_window = self.protocol_canvas.create_window((0, 0), window=self.protocol_form_frame, anchor="nw")
        self.protocol_canvas.configure(yscrollcommand=scrollbar.set)
        
        # Bind mouse wheel to scroll protocol form
        def _on_mousewheel_protocol(event):
            self.protocol_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            
        def _bind_protocol_mw(event):
            self.protocol_canvas.bind_all("<MouseWheel>", _on_mousewheel_protocol)
            
        def _unbind_protocol_mw(event):
            self.protocol_canvas.unbind_all("<MouseWheel>")
            
        self.protocol_canvas.bind('<Enter>', _bind_protocol_mw)
        self.protocol_canvas.bind('<Leave>', _unbind_protocol_mw)
        
        # Keep width of inner frame matched to canvas
        def _configure_window(event):
            self.protocol_canvas.itemconfig(self.protocol_canvas_window, width=event.width)
        self.protocol_canvas.bind('<Configure>', _configure_window)
        
        self.protocol_form_inner_frame = ttk.Frame(self.protocol_form_frame)
        self.protocol_form_inner_frame.pack(fill="both", expand=True)
        
        # Initial draw
        self.on_protocol_type_changed()

    def add_protocol_field(self, parent, label_text, field_name, field_type="entry", values=None, height=3):
        """Helper to add a labeled field to the protocol form."""
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=6)
        
        lbl = ttk.Label(frame, text=label_text, style="Bold.TLabel")
        lbl.pack(anchor="w", pady=(0, 2))
        
        if field_type == "entry":
            widget = ttk.Entry(frame)
            widget.pack(fill="x", ipady=2)
            self.protocol_widgets[field_name] = widget
        elif field_type == "text":
            widget = scrolledtext.ScrolledText(frame, wrap="word", font=("Segoe UI", 9), height=height)
            widget.pack(fill="x")
            self.protocol_widgets[field_name] = widget
        elif field_type == "combobox":
            widget = ttk.Combobox(frame, values=values or [], state="readonly")
            widget.pack(fill="x", ipady=2)
            if values:
                widget.set(values[0])
            self.protocol_widgets[field_name] = widget
        elif field_type == "databases":
            db_frame = ttk.Frame(frame)
            db_frame.pack(fill="x", pady=2)
            self.protocol_db_vars = {}
            for db in ["SciELO", "BDTD", "OpenAlex", "PubMed", "Scopus", "Google Scholar", "Outras"]:
                var = tk.BooleanVar(value=True if db in ["SciELO", "BDTD", "OpenAlex", "PubMed", "Scopus"] else False)
                self.protocol_db_vars[db] = var
                chk = ttk.Checkbutton(db_frame, text=db, variable=var)
                chk.pack(side="left", padx=(0, 15))
            self.protocol_widgets[field_name] = self.protocol_db_vars

    def on_protocol_type_changed(self, event=None):
        """Rebuilds the form fields based on the selected protocol type."""
        proto_type = self.cb_protocol_type.get()
        self.protocol_form_container.configure(text=f"Formulário do Protocolo: {proto_type}")
        
        # Clear previous fields
        for child in self.protocol_form_inner_frame.winfo_children():
            child.destroy()
            
        self.protocol_widgets = {}
        
        # 1. PRISMA-P (Saúde)
        if proto_type == "PRISMA-P (Saúde)":
            self.add_protocol_field(self.protocol_form_inner_frame, "1. Título do Projeto (com PICO e design):", "titulo", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "2. Plataforma de Registo Alvo:", "registro_alvo", "combobox", values=["PROSPERO", "INPLASY", "OSF", "Outra"])
            self.add_protocol_field(self.protocol_form_inner_frame, "3. Especialista Clínico / Autores:", "autores", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "4. Especialista em Informação / Bibliotecário:", "bibliotecario", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "5. Especialista em Bioestatística:", "estatistico", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "6. Envolvimento de Doentes / Consumidores:", "envolvimento", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "7. Justificação / Objetivos:", "objetivo", "entry")
            
            # PICO Sub-frame
            pico_lbl = ttk.Label(self.protocol_form_inner_frame, text="Questão PICO (Detalhamento):", style="Bold.TLabel", foreground=self.primary_color)
            pico_lbl.pack(anchor="w", pady=(10, 2))
            
            pico_frame = ttk.Frame(self.protocol_form_inner_frame, padding=5)
            pico_frame.pack(fill="x", pady=2)
            
            self.add_protocol_field(pico_frame, "  * População (P):", "pico_p", "entry")
            self.add_protocol_field(pico_frame, "  * Intervenção (I):", "pico_i", "entry")
            self.add_protocol_field(pico_frame, "  * Comparador (C):", "pico_c", "entry")
            self.add_protocol_field(pico_frame, "  * Outcomes / Resultados (O):", "pico_o", "entry")
            self.add_protocol_field(pico_frame, "  * Design de Estudo (S):", "pico_s", "entry")
            
            self.add_protocol_field(self.protocol_form_inner_frame, "8. Bases de Dados a Consultar:", "databases", "databases")
            self.add_protocol_field(self.protocol_form_inner_frame, "9. Estratégia de Busca (Descritores / Strings por linha):", "busca", "text", height=4)
            
            # Year fields side by side
            years_frame = ttk.Frame(self.protocol_form_inner_frame)
            years_frame.pack(fill="x", pady=4)
            
            y_start_frame = ttk.Frame(years_frame)
            y_start_frame.pack(side="left", fill="x", expand=True, padx=(0, 5))
            self.add_protocol_field(y_start_frame, "10. Ano Inicial (Filtro Temporal):", "limite_ano_inicio", "entry")
            
            y_end_frame = ttk.Frame(years_frame)
            y_end_frame.pack(side="left", fill="x", expand=True, padx=(5, 0))
            self.add_protocol_field(y_end_frame, "11. Ano Final (Filtro Temporal):", "limite_ano_fim", "entry")
            
            self.add_protocol_field(self.protocol_form_inner_frame, "12. Idioma(s) Elegível(is) (ex: por, eng):", "idioma", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "13. Critérios de Inclusão (Um por linha):", "criterios_inclusao", "text", height=4)
            self.add_protocol_field(self.protocol_form_inner_frame, "14. Critérios de Exclusão (Um por linha):", "criterios_exclusao", "text", height=4)
            self.add_protocol_field(self.protocol_form_inner_frame, "15. Questões / Campos de Extração de Dados (Um por linha):", "campos_extracao", "text", height=4)
            self.add_protocol_field(self.protocol_form_inner_frame, "16. Ferramenta de Gestão (ex: Covidence, Rayyan):", "gestao", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "17. Mecanismo de Desempate:", "conflitos", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "18. Avaliação do Risco de Viés (RoB):", "vies_robs", "combobox", values=["RoB 2 (Randomizados)", "ROBINS-I (Não randomizados)", "Outra"])
            self.add_protocol_field(self.protocol_form_inner_frame, "19. Avaliação da Certeza da Evidência:", "grade", "combobox", values=["Metodologia GRADE", "Não se aplica"])
            self.add_protocol_field(self.protocol_form_inner_frame, "20. Meta-análise (heterogeneidade I² aceitável):", "meta_analise", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "21. Modelos Estatísticos:", "modelo_estatistico", "combobox", values=["Efeitos aleatórios", "Efeitos fixos"])
            
            # Fill some defaults
            self.protocol_widgets['idioma'].insert(0, "por, eng")
            self.protocol_widgets['limite_ano_inicio'].insert(0, "2018")
            self.protocol_widgets['limite_ano_fim'].insert(0, str(pd.Timestamp.now().year))
            self.protocol_widgets['criterios_inclusao'].insert(tk.END, "Disponível com acesso público\n")
            self.protocol_widgets['campos_extracao'].insert(tk.END, "Objetivo do Estudo\nMétodo / Abordagem\nParticipantes / Amostra\nPrincipais Resultados\nConclusões / Limitações\n")
            self.protocol_widgets['meta_analise'].insert(0, "I² < 50%")
            
        # 2. Campbell (Sociais)
        elif proto_type == "Campbell (Sociais)":
            self.add_protocol_field(self.protocol_form_inner_frame, "1. Título do Projeto:", "titulo", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "2. Plataforma de Registo Alvo:", "registro_alvo", "combobox", values=["OSF", "INPLASY", "Campbell Library", "Outra"])
            self.add_protocol_field(self.protocol_form_inner_frame, "3. Autores / Equipe:", "autores", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "4. Foco em Equidade, Diversidade e Inclusão (EDI):", "edi", "entry")
            
            # SPICE/SPIDER Sub-frame
            spice_lbl = ttk.Label(self.protocol_form_inner_frame, text="Questão SPICE / SPIDER (Detalhamento):", style="Bold.TLabel", foreground=self.primary_color)
            spice_lbl.pack(anchor="w", pady=(10, 2))
            
            spice_frame = ttk.Frame(self.protocol_form_inner_frame, padding=5)
            spice_frame.pack(fill="x", pady=2)
            
            self.add_protocol_field(spice_frame, "  * Cenário (Setting) (S):", "spice_s", "entry")
            self.add_protocol_field(spice_frame, "  * Perspetiva / Amostra (Population) (P):", "spice_p", "entry")
            self.add_protocol_field(spice_frame, "  * Intervenção / Fenómeno (Intervention) (I):", "spice_i", "entry")
            self.add_protocol_field(spice_frame, "  * Comparador (Comparison) (C):", "spice_c", "entry")
            self.add_protocol_field(spice_frame, "  * Avaliação / Resultados (Evaluation) (E):", "spice_e", "entry")
            
            self.add_protocol_field(self.protocol_form_inner_frame, "5. Bases de Dados a Consultar:", "databases", "databases")
            self.add_protocol_field(self.protocol_form_inner_frame, "6. Estratégia de Busca (Descritores / Strings por linha):", "busca", "text", height=4)
            self.add_protocol_field(self.protocol_form_inner_frame, "7. Pesquisa de Literatura Cinzenta (ex: Relatórios, Teses):", "literatura_cinzenta", "entry")
            
            # Year fields side by side
            years_frame = ttk.Frame(self.protocol_form_inner_frame)
            years_frame.pack(fill="x", pady=4)
            
            y_start_frame = ttk.Frame(years_frame)
            y_start_frame.pack(side="left", fill="x", expand=True, padx=(0, 5))
            self.add_protocol_field(y_start_frame, "8. Ano Inicial (Filtro Temporal):", "limite_ano_inicio", "entry")
            
            y_end_frame = ttk.Frame(years_frame)
            y_end_frame.pack(side="left", fill="x", expand=True, padx=(5, 0))
            self.add_protocol_field(y_end_frame, "9. Ano Final (Filtro Temporal):", "limite_ano_fim", "entry")
            
            self.add_protocol_field(self.protocol_form_inner_frame, "10. Critérios de Inclusão (Um por linha):", "criterios_inclusao", "text", height=4)
            self.add_protocol_field(self.protocol_form_inner_frame, "11. Critérios de Exclusão (Um por linha):", "criterios_exclusao", "text", height=4)
            self.add_protocol_field(self.protocol_form_inner_frame, "12. Questões / Campos de Extração de Dados (Um por linha):", "campos_extracao", "text", height=4)
            self.add_protocol_field(self.protocol_form_inner_frame, "13. Avaliação de Qualidade (Designs mistos):", "qualidade", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "14. Plano de Síntese / Taxonomias adaptativas:", "sintese", "entry")
            
            # Fill some defaults
            self.protocol_widgets['limite_ano_inicio'].insert(0, "2018")
            self.protocol_widgets['limite_ano_fim'].insert(0, str(pd.Timestamp.now().year))
            self.protocol_widgets['criterios_inclusao'].insert(tk.END, "Disponível com acesso público\n")
            self.protocol_widgets['campos_extracao'].insert(tk.END, "Objetivo do Estudo\nMétodo / Abordagem\nParticipantes / Amostra\nPrincipais Resultados\nConclusões / Limitações\n")
            
        # 3. CEE/ROSES (Ecologia)
        elif proto_type == "CEE/ROSES (Ecologia)":
            self.add_protocol_field(self.protocol_form_inner_frame, "1. Título do Projeto:", "titulo", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "2. Plataforma de Registo Alvo:", "registro_alvo", "combobox", values=["OSF", "CEEDER", "Outra"])
            self.add_protocol_field(self.protocol_form_inner_frame, "3. Tipo de Síntese Planeada:", "tipo_sintese", "combobox", values=["Revisão Sistemática", "Systematic Map (Mapeamento)"])
            
            # PECO Sub-frame
            peco_lbl = ttk.Label(self.protocol_form_inner_frame, text="Questão PECO (Detalhamento):", style="Bold.TLabel", foreground=self.primary_color)
            peco_lbl.pack(anchor="w", pady=(10, 2))
            
            peco_frame = ttk.Frame(self.protocol_form_inner_frame, padding=5)
            peco_frame.pack(fill="x", pady=2)
            
            self.add_protocol_field(peco_frame, "  * População / Ecossistema (P):", "peco_p", "entry")
            self.add_protocol_field(peco_frame, "  * Exposição / Ação (E):", "peco_e", "entry")
            self.add_protocol_field(peco_frame, "  * Comparador (C):", "peco_c", "entry")
            self.add_protocol_field(peco_frame, "  * Resultados (O):", "peco_o", "entry")
            
            self.add_protocol_field(self.protocol_form_inner_frame, "4. Bases de Dados a Consultar:", "databases", "databases")
            self.add_protocol_field(self.protocol_form_inner_frame, "5. Estratégia de Busca (Descritores / Strings por linha):", "busca", "text", height=4)
            self.add_protocol_field(self.protocol_form_inner_frame, "6. Literatura Cinzenta / Órgãos Ambientais:", "cinzenta_ambiental", "entry")
            
            # Google Scholar sub-frame
            gs_lbl = ttk.Label(self.protocol_form_inner_frame, text="Protocolo Google Scholar (Mitigação de Viés Algorítmico):", style="Bold.TLabel")
            gs_lbl.pack(anchor="w", pady=(8, 2))
            
            gs_frame = ttk.Frame(self.protocol_form_inner_frame, padding=5)
            gs_frame.pack(fill="x", pady=2)
            
            self.add_protocol_field(gs_frame, "  * GS Navegação Cega (sem cookies/histórico):", "gs_blind", "combobox", values=["Sim", "Não"])
            self.add_protocol_field(gs_frame, "  * GS Limite de Extração (ex: 200):", "gs_limit", "entry")
            
            # Year fields side by side
            years_frame = ttk.Frame(self.protocol_form_inner_frame)
            years_frame.pack(fill="x", pady=4)
            
            y_start_frame = ttk.Frame(years_frame)
            y_start_frame.pack(side="left", fill="x", expand=True, padx=(0, 5))
            self.add_protocol_field(y_start_frame, "7. Ano Inicial (Filtro Temporal):", "limite_ano_inicio", "entry")
            
            y_end_frame = ttk.Frame(years_frame)
            y_end_frame.pack(side="left", fill="x", expand=True, padx=(5, 0))
            self.add_protocol_field(y_end_frame, "8. Ano Final (Filtro Temporal):", "limite_ano_fim", "entry")
            
            self.add_protocol_field(self.protocol_form_inner_frame, "9. Critérios de Inclusão FEAT (Um por linha):", "criterios_inclusao", "text", height=4)
            self.add_protocol_field(self.protocol_form_inner_frame, "10. Critérios de Exclusão (Um por linha):", "criterios_exclusao", "text", height=4)
            self.add_protocol_field(self.protocol_form_inner_frame, "11. Questões / Campos de Extração de Dados (Um por linha):", "campos_extracao", "text", height=4)
            self.add_protocol_field(self.protocol_form_inner_frame, "12. Variáveis Incontroláveis (clima, sazonalidade):", "variaveis_incontrolaveis", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "13. Plano de Síntese e Apresentação:", "sintese_apresentacao", "entry")
            
            # Fill some defaults
            self.protocol_widgets['gs_limit'].insert(0, "200")
            self.protocol_widgets['limite_ano_inicio'].insert(0, "2018")
            self.protocol_widgets['limite_ano_fim'].insert(0, str(pd.Timestamp.now().year))
            self.protocol_widgets['criterios_inclusao'].insert(tk.END, "Disponível com acesso público\n")
            self.protocol_widgets['campos_extracao'].insert(tk.END, "Objetivo do Estudo\nMétodo / Abordagem\nParticipantes / Amostra\nPrincipais Resultados\nConclusões / Limitações\n")
            
        # 4. EBSE (Software)
        elif proto_type == "EBSE (Software)":
            self.add_protocol_field(self.protocol_form_inner_frame, "1. Título do Projeto:", "titulo", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "2. Confirmação de ausência de revisão prévia:", "revisao_preliminar", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "3. Tipo de Estudo:", "tipo_estudo", "combobox", values=["Systematic Literature Review (SLR)", "Systematic Mapping Study (SMS)"])
            self.add_protocol_field(self.protocol_form_inner_frame, "4. Questões de Investigação (Contexto, Tecnologia, Métricas):", "questoes_investigacao", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "5. Bases de Dados a Consultar:", "databases", "databases")
            self.add_protocol_field(self.protocol_form_inner_frame, "6. Estratégia de Busca (Descritores / Strings por linha):", "busca", "text", height=4)
            
            # Wohlin Start Set
            seed_lbl = ttk.Label(self.protocol_form_inner_frame, text="Método de Wohlin (Snowballing Híbrido):", style="Bold.TLabel")
            seed_lbl.pack(anchor="w", pady=(8, 2))
            
            seed_frame = ttk.Frame(self.protocol_form_inner_frame, padding=5)
            seed_frame.pack(fill="x", pady=2)
            
            self.add_protocol_field(seed_frame, "  * Semente Fundamental (Start Set - 3 a 5 artigos seminais):", "wohlin_seed", "text", height=3)
            self.add_protocol_field(seed_frame, "  * Backward Snowballing (Referências da semente):", "wohlin_backward", "combobox", values=["Sim", "Não"])
            self.add_protocol_field(seed_frame, "  * Forward Snowballing (Citações futuras):", "wohlin_forward", "combobox", values=["Sim", "Não"])
            
            # Year fields side by side
            years_frame = ttk.Frame(self.protocol_form_inner_frame)
            years_frame.pack(fill="x", pady=4)
            
            y_start_frame = ttk.Frame(years_frame)
            y_start_frame.pack(side="left", fill="x", expand=True, padx=(0, 5))
            self.add_protocol_field(y_start_frame, "7. Ano Inicial (Filtro Temporal):", "limite_ano_inicio", "entry")
            
            y_end_frame = ttk.Frame(years_frame)
            y_end_frame.pack(side="left", fill="x", expand=True, padx=(5, 0))
            self.add_protocol_field(y_end_frame, "8. Ano Final (Filtro Temporal):", "limite_ano_fim", "entry")
            
            self.add_protocol_field(self.protocol_form_inner_frame, "9. Critérios de Inclusão (Um por linha):", "criterios_inclusao", "text", height=4)
            self.add_protocol_field(self.protocol_form_inner_frame, "10. Critérios de Exclusão (Um por linha):", "criterios_exclusao", "text", height=4)
            self.add_protocol_field(self.protocol_form_inner_frame, "11. Questões / Campos de Extração de Dados (Um por linha):", "campos_extracao", "text", height=4)
            self.add_protocol_field(self.protocol_form_inner_frame, "12. Faceta 1 (Arquitetura/Tópico de Agrupamento):", "faceta_topico", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "13. Faceta 2 (Natureza Metodológica):", "faceta_metodo", "combobox", values=["Validação Empírica (Laboratório)", "Investigação Avaliativa (Ambiente Real)", "Ensaios Teóricos", "Proposta de Framework"])
            self.add_protocol_field(self.protocol_form_inner_frame, "14. Apresentação Visual (Bubble plots):", "visualizacao", "combobox", values=["Sim", "Não"])
            
            # Fill some defaults
            self.protocol_widgets['limite_ano_inicio'].insert(0, "2018")
            self.protocol_widgets['limite_ano_fim'].insert(0, str(pd.Timestamp.now().year))
            self.protocol_widgets['criterios_inclusao'].insert(tk.END, "Disponível com acesso público\n")
            self.protocol_widgets['campos_extracao'].insert(tk.END, "Objetivo do Estudo\nMétodo / Abordagem\nParticipantes / Amostra\nPrincipais Resultados\nConclusões / Limitações\n")
            
        # 5. Umbrella Review (Overview)
        elif proto_type == "Umbrella Review (Overview)":
            self.add_protocol_field(self.protocol_form_inner_frame, "1. Título da Umbrella Review / Overview:", "titulo", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "2. Racional / Saturação Bibliográfica:", "justificativa", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "3. Plataforma de Registo Alvo:", "registro_alvo", "combobox", values=["PROSPERO", "INPLASY", "OSF", "Outra"])
            self.add_protocol_field(self.protocol_form_inner_frame, "4. Tipo de Revisões Elegíveis (Meta-análise, Scoping, etc.):", "criterios_revisoes", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "5. Bases de Dados a Consultar:", "databases", "databases")
            self.add_protocol_field(self.protocol_form_inner_frame, "6. Estratégia de Busca (Descritores / Strings por linha):", "busca", "text", height=4)
            
            # Year fields side by side
            years_frame = ttk.Frame(self.protocol_form_inner_frame)
            years_frame.pack(fill="x", pady=4)
            
            y_start_frame = ttk.Frame(years_frame)
            y_start_frame.pack(side="left", fill="x", expand=True, padx=(0, 5))
            self.add_protocol_field(y_start_frame, "7. Ano Inicial (Filtro Temporal):", "limite_ano_inicio", "entry")
            
            y_end_frame = ttk.Frame(years_frame)
            y_end_frame.pack(side="left", fill="x", expand=True, padx=(5, 0))
            self.add_protocol_field(y_end_frame, "8. Ano Final (Filtro Temporal):", "limite_ano_fim", "entry")
            
            self.add_protocol_field(self.protocol_form_inner_frame, "9. Critérios de Inclusão (Um por linha):", "criterios_inclusao", "text", height=4)
            self.add_protocol_field(self.protocol_form_inner_frame, "10. Critérios de Exclusão (Um por linha):", "criterios_exclusao", "text", height=4)
            self.add_protocol_field(self.protocol_form_inner_frame, "11. Questões / Campos de Extração de Dados (Um por linha):", "campos_extracao", "text", height=4)
            
            # Quality tools
            qual_lbl = ttk.Label(self.protocol_form_inner_frame, text="Avaliação da Qualidade das Revisões:", style="Bold.TLabel")
            qual_lbl.pack(anchor="w", pady=(8, 2))
            
            qual_frame = ttk.Frame(self.protocol_form_inner_frame, padding=5)
            qual_frame.pack(fill="x", pady=2)
            
            self.add_protocol_field(qual_frame, "  * Usar AMSTAR-2 (16 itens, relato metodológico global):", "qualidade_amstar", "combobox", values=["Sim", "Não"])
            self.add_protocol_field(qual_frame, "  * Usar ROBIS (24 itens, microscopia de risco de viés):", "qualidade_robis", "combobox", values=["Sim", "Não"])
            
            self.add_protocol_field(self.protocol_form_inner_frame, "12. Resolução de Discordâncias AMSTAR/ROBIS:", "concordancia", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "13. Gestão de Sobreposição (Overlap) - Matriz / CCA:", "overlap", "entry")
            
            # Fill some defaults
            self.protocol_widgets['limite_ano_inicio'].insert(0, "2018")
            self.protocol_widgets['limite_ano_fim'].insert(0, str(pd.Timestamp.now().year))
            self.protocol_widgets['criterios_inclusao'].insert(tk.END, "Disponível com acesso público\n")
            self.protocol_widgets['campos_extracao'].insert(tk.END, "Objetivo do Estudo\nMétodo / Abordagem\nParticipantes / Amostra\nPrincipais Resultados\nConclusões / Limitações\n")
            
        # 6. Scoping Review (PRISMA-ScR)
        elif proto_type == "Scoping Review (PRISMA-ScR)":
            self.add_protocol_field(self.protocol_form_inner_frame, "1. Título do Projeto (com PCC):", "titulo", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "2. Plataforma de Registo Alvo:", "registro_alvo", "combobox", values=["OSF", "JBI Library", "Outra"])
            self.add_protocol_field(self.protocol_form_inner_frame, "3. Justificação e Objetivos:", "objetivo", "entry")
            
            # PCC sub-frame
            pcc_lbl = ttk.Label(self.protocol_form_inner_frame, text="Framework PCC (Detalhamento):", style="Bold.TLabel", foreground=self.primary_color)
            pcc_lbl.pack(anchor="w", pady=(10, 2))
            
            pcc_frame = ttk.Frame(self.protocol_form_inner_frame, padding=5)
            pcc_frame.pack(fill="x", pady=2)
            
            self.add_protocol_field(pcc_frame, "  * População (P):", "pcc_p", "entry")
            self.add_protocol_field(pcc_frame, "  * Conceito (C):", "pcc_c1", "entry")
            self.add_protocol_field(pcc_frame, "  * Contexto (C):", "pcc_c2", "entry")
            
            self.add_protocol_field(self.protocol_form_inner_frame, "4. Bases de Dados a Consultar:", "databases", "databases")
            self.add_protocol_field(self.protocol_form_inner_frame, "5. Estratégia de Busca (Descritores / Strings por linha):", "busca", "text", height=4)
            
            # Year fields side by side
            years_frame = ttk.Frame(self.protocol_form_inner_frame)
            years_frame.pack(fill="x", pady=4)
            
            y_start_frame = ttk.Frame(years_frame)
            y_start_frame.pack(side="left", fill="x", expand=True, padx=(0, 5))
            self.add_protocol_field(y_start_frame, "6. Ano Inicial (Filtro Temporal):", "limite_ano_inicio", "entry")
            
            y_end_frame = ttk.Frame(years_frame)
            y_end_frame.pack(side="left", fill="x", expand=True, padx=(5, 0))
            self.add_protocol_field(y_end_frame, "7. Ano Final (Filtro Temporal):", "limite_ano_fim", "entry")
            
            self.add_protocol_field(self.protocol_form_inner_frame, "8. Idioma(s) Elegível(is) (ex: por, eng):", "idioma", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "9. Critérios de Inclusão (Um por linha):", "criterios_inclusao", "text", height=4)
            self.add_protocol_field(self.protocol_form_inner_frame, "10. Critérios de Exclusão (Um por linha):", "criterios_exclusao", "text", height=4)
            self.add_protocol_field(self.protocol_form_inner_frame, "11. Questões / Campos de Extração de Dados (Um por linha):", "campos_extracao", "text", height=4)
            self.add_protocol_field(self.protocol_form_inner_frame, "12. Plano de Extração e Mapeamento de Evidências:", "mapeamento", "entry")
            
            # Fill some defaults
            self.protocol_widgets['idioma'].insert(0, "por, eng")
            self.protocol_widgets['limite_ano_inicio'].insert(0, "2018")
            self.protocol_widgets['limite_ano_fim'].insert(0, str(pd.Timestamp.now().year))
            self.protocol_widgets['criterios_inclusao'].insert(tk.END, "Disponível com acesso público\n")
            self.protocol_widgets['campos_extracao'].insert(tk.END, "Objetivo do Estudo\nMétodo / Abordagem\nParticipantes / Amostra\nPrincipais Resultados\nConclusões / Limitações\n")
            
        # 7. Methodi Ordinatio
        elif proto_type == "Methodi Ordinatio":
            self.add_protocol_field(self.protocol_form_inner_frame, "1. Título do Projeto:", "titulo", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "2. Autores / Equipe:", "autores", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "3. Objetivos / Pergunta de Pesquisa:", "objetivo", "entry")
            self.add_protocol_field(self.protocol_form_inner_frame, "4. Bases de Dados a Consultar:", "databases", "databases")
            self.add_protocol_field(self.protocol_form_inner_frame, "5. Estratégia de Busca (Descritores / Strings por linha):", "busca", "text", height=4)
            
            # Inordinatio params side by side
            params_frame = ttk.Frame(self.protocol_form_inner_frame)
            params_frame.pack(fill="x", pady=4)
            
            ki_frame = ttk.Frame(params_frame)
            ki_frame.pack(side="left", fill="x", expand=True, padx=(0, 5))
            self.add_protocol_field(ki_frame, "6. Ano da Busca (Ki):", "ano_busca", "entry")
            
            alpha_frame = ttk.Frame(params_frame)
            alpha_frame.pack(side="left", fill="x", expand=True, padx=(5, 0))
            self.add_protocol_field(alpha_frame, "7. Fator Alpha (Peso de Citação):", "fator_alpha", "entry")
            
            # Filtering params side by side
            filt_frame = ttk.Frame(self.protocol_form_inner_frame)
            filt_frame.pack(fill="x", pady=4)
            
            ystart_frame = ttk.Frame(filt_frame)
            ystart_frame.pack(side="left", fill="x", expand=True, padx=(0, 5))
            self.add_protocol_field(ystart_frame, "8. Ano Inicial de Publicação:", "limite_ano_inicio", "entry")
            
            jcr_frame = ttk.Frame(filt_frame)
            jcr_frame.pack(side="left", fill="x", expand=True, padx=(5, 0))
            self.add_protocol_field(jcr_frame, "9. Fator de Impacto Mínimo (ex: SJR > 0.1):", "fator_impacto", "entry")
            
            self.add_protocol_field(self.protocol_form_inner_frame, "10. Critérios de Inclusão (Um por linha):", "criterios_inclusao", "text", height=4)
            self.add_protocol_field(self.protocol_form_inner_frame, "11. Critérios de Exclusão (Um por linha):", "criterios_exclusao", "text", height=4)
            self.add_protocol_field(self.protocol_form_inner_frame, "12. Questões / Campos de Extração de Dados (Um por linha):", "campos_extracao", "text", height=4)
            
            # Reviewers side by side
            revs_frame = ttk.Frame(self.protocol_form_inner_frame)
            revs_frame.pack(fill="x", pady=4)
            
            num_rev_frame = ttk.Frame(revs_frame)
            num_rev_frame.pack(side="left", fill="x", expand=True, padx=(0, 5))
            self.add_protocol_field(num_rev_frame, "13. Número de Revisores:", "num_revisores", "entry")
            
            read_frame = ttk.Frame(revs_frame)
            read_frame.pack(side="left", fill="x", expand=True, padx=(5, 0))
            self.add_protocol_field(read_frame, "14. Fase de Leitura:", "leitura", "combobox", values=["Título/Resumo + Íntegra", "Apenas Íntegra"])
            
            # Fill some defaults
            self.protocol_widgets['ano_busca'].insert(0, str(pd.Timestamp.now().year))
            self.protocol_widgets['fator_alpha'].insert(0, "10")
            self.protocol_widgets['limite_ano_inicio'].insert(0, "2018")
            self.protocol_widgets['num_revisores'].insert(0, "2")
            self.protocol_widgets['criterios_inclusao'].insert(tk.END, "Disponível com acesso público\n")
            self.protocol_widgets['campos_extracao'].insert(tk.END, "Objetivo do Estudo\nMétodo / Abordagem\nParticipantes / Amostra\nPrincipais Resultados\nConclusões / Limitações\n")

    def collect_protocol_data(self):
        """Serializes current protocol fields into a dict."""
        proto_type = self.cb_protocol_type.get()
        data = {
            "protocol_type": proto_type,
            "fields": {}
        }
        
        for field, widget in self.protocol_widgets.items():
            if isinstance(widget, ttk.Entry):
                data["fields"][field] = widget.get().strip()
            elif isinstance(widget, scrolledtext.ScrolledText):
                data["fields"][field] = widget.get("1.0", tk.END).strip()
            elif isinstance(widget, ttk.Combobox):
                data["fields"][field] = widget.get()
            elif isinstance(widget, dict): # databases
                data["fields"][field] = {db: var.get() for db, var in widget.items()}
                
        return data

    def create_empty_unified_schema(self):
        """Returns an empty unified JSON schema with all sections initialized."""
        from datetime import datetime
        now = datetime.now().isoformat(timespec='seconds')
        return {
            "meta": {
                "versao_schema": "1.0",
                "criado_em": now,
                "atualizado_em": now
            },
            "protocolo": {
                "protocol_type": "",
                "fields": {}
            },
            "config_busca": {
                "systematic_review": {
                    "project_name": "",
                    "keywords": [],
                    "global_limit": None,
                    "global_delay": 2.5
                },
                "sources": {
                    "bdtd": {"enabled": False},
                    "scielo": {"enabled": False},
                    "openalex": {"enabled": False},
                    "pubmed": {"enabled": False},
                    "scopus": {"enabled": False}
                }
            },
            "triagem": {
                "arquivos_origem": [],
                "criterios_inclusao": [],
                "criterios_exclusao": [],
                "perguntas": [],
                "campos_extracao": [],
                "trabalhos": []
            }
        }

    def build_unified_data(self):
        """Consolidates all current app state into the unified JSON structure."""
        from datetime import datetime

        unified = self.create_empty_unified_schema()

        # --- Protocolo ---
        try:
            proto_data = self.collect_protocol_data()
            if proto_data and proto_data.get("protocol_type"):
                unified["protocolo"] = proto_data
        except Exception:
            pass

        # --- Config de Busca ---
        try:
            config_data = self.collect_data()
            if config_data:
                unified["config_busca"] = config_data
        except Exception:
            pass

        # --- Triagem / Extração ---
        if self.current_session and self.current_session.get('trabalhos'):
            # Save any pending paper decisions/extraction to session state
            try:
                self.save_current_paper_decisions()
            except Exception:
                pass
            try:
                self.save_current_paper_extraction()
            except Exception:
                pass
            self.current_session['campos_extracao'] = self.campos_extracao.copy()
            unified["triagem"] = self.current_session

        # --- Meta ---
        unified["meta"]["atualizado_em"] = datetime.now().isoformat(timespec='seconds')

        return unified

    def _save_unified_json(self, default_name="revisao_sistematica.json"):
        """Saves the unified JSON file, reusing the last opened path if available."""
        unified = self.build_unified_data()

        initial_dir = None
        if self.unified_file_path:
            initial_dir = os.path.dirname(self.unified_file_path)
            default_name = os.path.basename(self.unified_file_path)

        file_path = filedialog.asksaveasfilename(
            initialdir=initial_dir,
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialfile=default_name
        )

        if file_path:
            try:
                # Preserve original creation timestamp if file already exists
                if os.path.exists(file_path):
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            existing = json.load(f)
                        if 'meta' in existing and 'criado_em' in existing['meta']:
                            unified['meta']['criado_em'] = existing['meta']['criado_em']
                    except Exception:
                        pass

                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(unified, f, ensure_ascii=False, indent=4)

                self.unified_file_path = file_path
                self.status_var.set(f"Projeto salvo em: {os.path.basename(file_path)}")
                messagebox.showinfo("Sucesso", f"Projeto salvo com sucesso!\n\nArquivo: {file_path}")
            except Exception as e:
                self.status_var.set("Erro ao salvar arquivo JSON.")
                messagebox.showerror("Erro", f"Não foi possível salvar o projeto:\n{str(e)}")

    def _save_unified_json_quietly(self):
        """Saves the unified JSON file, reusing the last opened path if available, without dialog prompts."""
        if not self.unified_file_path:
            # Auto-generate a path if none was set yet
            out_dir = self.ent_output_dir.get().strip() if hasattr(self, 'ent_output_dir') else ""
            if out_dir and os.path.exists(out_dir):
                self.unified_file_path = os.path.join(out_dir, "revisao_sistematica.json").replace("\\", "/")
            else:
                return
        try:
            unified = self.build_unified_data()
            if os.path.exists(self.unified_file_path):
                try:
                    with open(self.unified_file_path, 'r', encoding='utf-8') as f:
                        existing = json.load(f)
                    if 'meta' in existing and 'criado_em' in existing['meta']:
                        unified['meta']['criado_em'] = existing['meta']['criado_em']
                except Exception:
                    pass

            win_path = fix_win_long_path(self.unified_file_path)
            with open(win_path, 'w', encoding='utf-8') as f:
                json.dump(unified, f, ensure_ascii=False, indent=4)
            self.status_var.set(f"Sessão auto-salva em: {os.path.basename(self.unified_file_path)}")
        except Exception as e:
            self.status_var.set(f"Erro ao auto-salvar: {str(e)}")

    def _load_unified_or_legacy(self, file_path):
        """Detects JSON format (unified or legacy) and populates all app state accordingly.
        Returns True on success, False on failure."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível ler o arquivo JSON:\n{e}")
            return False

        # Auto-detect PDF folder as a sibling of the loaded JSON file
        project_dir = os.path.dirname(file_path)
        pdf_dir = os.path.join(project_dir, "pdfs").replace("\\", "/")
        self.pdf_download_dir.set(pdf_dir)

        is_unified = 'meta' in data and 'versao_schema' in data.get('meta', {})

        if is_unified:
            self.unified_file_path = file_path

            # --- Load Protocol ---
            proto = data.get('protocolo', {})
            proto_type = proto.get('protocol_type', '')
            if proto_type:
                valid_protos = [
                    "PRISMA-P (Saúde)", "Campbell (Sociais)", "CEE/ROSES (Ecologia)",
                    "EBSE (Software)", "Umbrella Review (Overview)",
                    "Scoping Review (PRISMA-ScR)", "Methodi Ordinatio"
                ]
                if proto_type in valid_protos:
                    self.cb_protocol_type.set(proto_type)
                    self.on_protocol_type_changed()
                    fields = proto.get("fields", {})
                    for field, val in fields.items():
                        if field in self.protocol_widgets:
                            widget = self.protocol_widgets[field]
                            if isinstance(widget, ttk.Entry):
                                widget.delete(0, tk.END)
                                widget.insert(0, val)
                            elif isinstance(widget, scrolledtext.ScrolledText):
                                widget.delete("1.0", tk.END)
                                widget.insert(tk.END, val)
                            elif isinstance(widget, ttk.Combobox):
                                widget.set(val)
                            elif isinstance(widget, dict):
                                for db, db_val in val.items():
                                    if db in widget:
                                        widget[db].set(db_val)

            # --- Load Config de Busca ---
            config = data.get('config_busca', {})
            if config.get('systematic_review') or config.get('sources'):
                self._populate_config_from_dict(config)

            # --- Load Triagem ---
            triagem = data.get('triagem', {})
            if triagem.get('trabalhos'):
                self._populate_triagem_from_dict(triagem)

            return True
        else:
            # Legacy format detection
            if 'protocol_type' in data:
                # Legacy protocol file
                return self._load_legacy_protocol(data, file_path)
            elif 'systematic_review' in data or 'sources' in data:
                # Legacy config file
                self._populate_config_from_dict(data)
                return True
            elif 'trabalhos' in data or 'arquivos_origem' in data:
                # Legacy triagem/extraction file
                self._populate_triagem_from_dict(data)
                return True
            elif 'metadata' in data and 'session' in data:
                # Legacy V2 format (broken duplicate save): extract session data
                self.unified_file_path = file_path
                session = data.get('session', {})
                if session.get('trabalhos') or session.get('arquivos_origem'):
                    self._populate_triagem_from_dict(session)
                return True
            else:
                messagebox.showerror("Erro", "Formato de arquivo JSON não reconhecido.")
                return False

    def _load_legacy_protocol(self, data, file_path):
        """Loads a legacy protocol JSON and populates the protocol form."""
        proto_type = data.get("protocol_type")
        valid_protos = [
            "PRISMA-P (Saúde)", "Campbell (Sociais)", "CEE/ROSES (Ecologia)",
            "EBSE (Software)", "Umbrella Review (Overview)",
            "Scoping Review (PRISMA-ScR)", "Methodi Ordinatio"
        ]
        if not proto_type or proto_type not in valid_protos:
            messagebox.showerror("Erro", "Arquivo JSON inválido ou formato de protocolo desconhecido.")
            return False

        self.cb_protocol_type.set(proto_type)
        self.on_protocol_type_changed()

        fields = data.get("fields", {})
        for field, val in fields.items():
            if field in self.protocol_widgets:
                widget = self.protocol_widgets[field]
                if isinstance(widget, ttk.Entry):
                    widget.delete(0, tk.END)
                    widget.insert(0, val)
                elif isinstance(widget, scrolledtext.ScrolledText):
                    widget.delete("1.0", tk.END)
                    widget.insert(tk.END, val)
                elif isinstance(widget, ttk.Combobox):
                    widget.set(val)
                elif isinstance(widget, dict):
                    for db, db_val in val.items():
                        if db in widget:
                            widget[db].set(db_val)
        return True

    def _populate_config_from_dict(self, config):
        """Populates Config Geral and Harvester tabs from a config dictionary."""
        gen = config.get('systematic_review', config.get('general', {}))
        self.ent_project_name.delete(0, tk.END)
        self.ent_project_name.insert(0, gen.get('project_name', ''))

        self.ent_global_limit.delete(0, tk.END)
        limit_val = gen.get('global_limit', gen.get('limit'))
        self.ent_global_limit.insert(0, str(limit_val) if limit_val is not None else "")

        self.ent_global_delay.delete(0, tk.END)
        self.ent_global_delay.insert(0, str(gen.get('global_delay', gen.get('delay', 2.5))))

        self.keywords = gen.get('keywords', [])
        self.update_keywords_listbox()

        # BDTD
        bdtd = config.get('sources', {}).get('bdtd', {})
        self.var_bdtd_enabled.set(bdtd.get('enabled', False))
        self.toggle_bdtd_fields()
        self.ent_bdtd_db.delete(0, tk.END)
        self.ent_bdtd_db.insert(0, bdtd.get('db_path', ''))
        self.ent_bdtd_export.delete(0, tk.END)
        self.ent_bdtd_export.insert(0, bdtd.get('export_path', ''))
        self.cb_bdtd_search.set(bdtd.get('search_type', 'AllFields'))
        self.cb_bdtd_sort.set(bdtd.get('sort_order', 'year'))
        if hasattr(self, 'var_bdtd_scrape_details'):
            self.var_bdtd_scrape_details.set(bdtd.get('scrape_details', True))
        filters = bdtd.get('filters', {})
        self.cb_bdtd_filter_format.set(filters.get('format', ''))
        self.ent_bdtd_filter_inst.delete(0, tk.END)
        self.ent_bdtd_filter_inst.insert(0, filters.get('institution', ''))
        self.ent_bdtd_filter_date.delete(0, tk.END)
        self.ent_bdtd_filter_date.insert(0, filters.get('publishDate', ''))
        self.ent_bdtd_filter_lang.delete(0, tk.END)
        self.ent_bdtd_filter_lang.insert(0, filters.get('language', ''))

        # SciELO
        scielo = config.get('sources', {}).get('scielo', {})
        self.var_scielo_enabled.set(scielo.get('enabled', False))
        self.toggle_scielo_fields()
        self.ent_scielo_db.delete(0, tk.END)
        self.ent_scielo_db.insert(0, scielo.get('db_path', ''))
        self.ent_scielo_export.delete(0, tk.END)
        self.ent_scielo_export.insert(0, scielo.get('export_path', ''))
        self.ent_scielo_search_field.delete(0, tk.END)
        self.ent_scielo_search_field.insert(0, scielo.get('search_field', ''))

        # OpenAlex
        openalex = config.get('sources', {}).get('openalex', {})
        self.var_openalex_enabled.set(openalex.get('enabled', False))
        self.toggle_openalex_fields()
        self.ent_openalex_db.delete(0, tk.END)
        self.ent_openalex_db.insert(0, openalex.get('db_path', ''))
        self.ent_openalex_export.delete(0, tk.END)
        self.ent_openalex_export.insert(0, openalex.get('export_path', ''))
        self.ent_openalex_email.delete(0, tk.END)
        self.ent_openalex_email.insert(0, openalex.get('email', ''))
        self.ent_openalex_api_key.delete(0, tk.END)
        self.ent_openalex_api_key.insert(0, openalex.get('api_key', ''))
        filters_openalex = openalex.get('filters', {})
        self.cb_openalex_filter_type.set(filters_openalex.get('type', ''))
        self.ent_openalex_filter_year.delete(0, tk.END)
        self.ent_openalex_filter_year.insert(0, filters_openalex.get('publication_year', ''))
        self.ent_openalex_filter_lang.delete(0, tk.END)
        self.ent_openalex_filter_lang.insert(0, filters_openalex.get('language', ''))

        # PubMed
        pubmed = config.get('sources', {}).get('pubmed', {})
        self.var_pubmed_enabled.set(pubmed.get('enabled', False))
        self.toggle_pubmed_fields()
        self.ent_pubmed_db.delete(0, tk.END)
        self.ent_pubmed_db.insert(0, pubmed.get('db_path', ''))
        self.ent_pubmed_export.delete(0, tk.END)
        self.ent_pubmed_export.insert(0, pubmed.get('export_path', ''))
        self.ent_pubmed_api_key.delete(0, tk.END)
        self.ent_pubmed_api_key.insert(0, pubmed.get('api_key', ''))

        # Scopus
        scopus = config.get('sources', {}).get('scopus', {})
        self.var_scopus_enabled.set(scopus.get('enabled', False))
        self.toggle_scopus_fields()
        self.ent_scopus_db.delete(0, tk.END)
        self.ent_scopus_db.insert(0, scopus.get('db_path', ''))
        self.ent_scopus_export.delete(0, tk.END)
        self.ent_scopus_export.insert(0, scopus.get('export_path', ''))
        self.ent_scopus_api_key.delete(0, tk.END)
        self.ent_scopus_api_key.insert(0, scopus.get('api_key', ''))
        self.cb_scopus_view.set(scopus.get('view', 'COMPLETE'))

        # Infer output directory
        db_path = bdtd.get('db_path', '')
        if db_path:
            dir_name = os.path.dirname(db_path)
            self.ent_output_dir.delete(0, tk.END)
            self.ent_output_dir.insert(0, dir_name)

    def _populate_triagem_from_dict(self, session):
        """Populates Triagem and Extraction tabs from a session dictionary."""
        self.current_session = session

        self.triagem_csv_files = session.get('arquivos_origem', [])
        self.inclusion_criteria = session.get('criterios_inclusao', [])
        self.exclusion_criteria = session.get('criterios_exclusao', [])
        self.triagem_questions = session.get('perguntas', [])
        self.campos_extracao = session.get('campos_extracao', [])

        # Rebuild Left Pane widgets lists
        self.lst_triagem_files.delete(0, tk.END)
        for f_name in self.triagem_csv_files:
            self.lst_triagem_files.insert(tk.END, os.path.basename(f_name))

        self.lst_inc_criteria.delete(0, tk.END)
        for c in self.inclusion_criteria:
            self.lst_inc_criteria.insert(tk.END, c)

        self.lst_exc_criteria.delete(0, tk.END)
        for c in self.exclusion_criteria:
            self.lst_exc_criteria.insert(tk.END, c)

        self.lst_triagem_questions.delete(0, tk.END)
        for q in self.triagem_questions:
            self.lst_triagem_questions.insert(tk.END, q)

        # Populate extraction fields listbox
        try:
            self.lst_ext_fields.delete(0, tk.END)
            for cf in self.campos_extracao:
                self.lst_ext_fields.insert(tk.END, cf)
        except AttributeError:
            pass

        # Populate Treeview
        self.populate_treeview()

        # Populate Treeview for Triagem 2
        try:
            self.populate_treeview_t2()
            self.scan_pdf_directory_t2(show_message=False)
        except Exception:
            pass

        # Select first item
        children = self.tree_triagem.get_children()
        if children:
            self.tree_triagem.selection_set(children[0])

        # Select first item in Triagem 2
        try:
            children_t2 = self.tree_triagem_2.get_children()
            if children_t2:
                self.tree_triagem_2.selection_set(children_t2[0])

            num_included = len(children_t2)
            num_done = sum(1 for t in self.current_session.get('trabalhos', []) if t.get('Decisao') == 'Incluído' and t.get('Extracao', {}).get('status_extracao') == 'Concluída')
            self.lbl_t2_session_status.configure(
                text=f"Sessão ativa: {len(session.get('trabalhos', []))} trabalhos.\nIncluídos: {num_included} ({num_done} extraídos).",
                foreground="#1f497d"
            )
        except Exception:
            pass

    def save_protocol_json(self):
        """Saves the entire project (unified JSON) from the Protocol tab."""
        self._save_unified_json()

    def load_protocol_json(self):
        """Loads a project JSON (unified or legacy protocol) and populates the form."""
        file_path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if not file_path:
            return

        if self._load_unified_or_legacy(file_path):
            self.status_var.set(f"Projeto carregado de: {os.path.basename(file_path)}")
            messagebox.showinfo("Sucesso", f"Projeto carregado com sucesso!\n\nArquivo: {file_path}")

    def run_ai_protocol_partner(self):
        """Uses Gemini AI to generate protocol suggestions based on user prompt and selected protocol model."""
        if not self._has_gemini_keys():
            messagebox.showwarning("Chave de API ausente", "Nenhuma chave de API do Gemini configurada.\nPor favor, adicione pelo menos uma API Key na aba 'Configuração Geral'.")
            return

        user_prompt = self.txt_ai_research_prompt.get("1.0", tk.END).strip()
        if not user_prompt:
            messagebox.showwarning("Campo Vazio", "Por favor, digite a descrição da pesquisa que você deseja realizar no campo do Parceiro de Pesquisa.")
            return

        proto_type = self.cb_protocol_type.get()
        keys_list = list(self.protocol_widgets.keys())

        self.btn_ai_fill_protocol.configure(state="disabled")
        self.lbl_ai_protocol_status.configure(text="🤖 Gerando sugestão com I.A...")
        self.status_var.set(f"Gerando sugestões com a I.A. para o protocolo {proto_type}...")

        def worker():
            try:
                # Build list of fields to request from Gemini
                fields_example = {}
                for k in keys_list:
                    if k == "databases":
                        fields_example[k] = {"SciELO": True, "BDTD": True, "OpenAlex": True, "PubMed": True, "Scopus": True}
                    elif k in ["busca", "criterios_inclusao", "criterios_exclusao", "campos_extracao", "wohlin_seed"]:
                        fields_example[k] = "Item 1\nItem 2\nItem 3"
                    elif k in ["limite_ano_inicio", "limite_ano_fim", "ano_busca"]:
                        fields_example[k] = "2018"
                    else:
                        fields_example[k] = "Texto de sugestão aqui"

                prompt = (
                    f"O usuário deseja realizar a seguinte pesquisa:\n"
                    f"\"{user_prompt}\"\n\n"
                    f"O protocolo de pesquisa selecionado é: \"{proto_type}\".\n\n"
                    f"Por favor, preencha a estrutura JSON abaixo com sugestões completas, objetivas, diretas e rigorosas para este protocolo de pesquisa.\n"
                    f"A estrutura JSON deve conter exatamente as seguintes chaves:\n"
                    f"{json.dumps(fields_example, ensure_ascii=False, indent=2)}\n\n"
                    f"Nota para 'criterios_inclusao', 'criterios_exclusao', 'campos_extracao' e 'busca': forneça itens separados por quebra de linha (\\n).\n"
                    f"Nota para 'busca': forneça APENAS a string booleana pura (ex: '(\"termo 1\" OR \"termo 2\") AND (\"termo 3\" OR \"termo 4\")'). NÃO inclua nomes de bases nem prefixos como 'SciELO/BDTD:', 'PubMed:', '[SciELO]:' etc.\n"
                    f"Nota para 'campos_extracao': sugira questões/campos específicos de extração de dados fundamentais para responder às perguntas de pesquisa deste estudo."
                )

                raw_text = self.call_gemini_api(prompt, system_instruction=SYSTEM_PROMPT_RESEARCH_PARTNER)
                if not raw_text:
                    raise RuntimeError("Resposta vazia retornada pela API do Gemini.")

                res_json = json.loads(raw_text)

                def update_gui():
                    # Update protocol widgets with AI suggestions
                    for key, val in res_json.items():
                        if key in self.protocol_widgets:
                            widget = self.protocol_widgets[key]
                            if isinstance(widget, ttk.Entry):
                                widget.delete(0, tk.END)
                                widget.insert(0, str(val))
                            elif isinstance(widget, scrolledtext.ScrolledText):
                                widget.delete("1.0", tk.END)
                                widget.insert(tk.END, str(val))
                            elif isinstance(widget, ttk.Combobox):
                                if isinstance(val, str):
                                    widget.set(val)
                            elif isinstance(widget, dict) and isinstance(val, dict):
                                for db_name, db_val in val.items():
                                    if db_name in widget:
                                        widget[db_name].set(bool(db_val))

                    # Advance settings automatically so keywords, criteria, and extraction fields propagate
                    self.advance_from_protocol(show_msg=False)

                    self.btn_ai_fill_protocol.configure(state="normal")
                    self.lbl_ai_protocol_status.configure(text="✅ Sugestão gerada!")
                    self.status_var.set("Protocolo preenchido com sucesso pela I.A.!")
                    messagebox.showinfo("Sucesso", f"Protocolo '{proto_type}' preenchido com sucesso com as sugestões da I.A.!")

                self.after(0, update_gui)

            except Exception as e:
                def on_err(msg=str(e)):
                    self.btn_ai_fill_protocol.configure(state="normal")
                    self.lbl_ai_protocol_status.configure(text="❌ Erro na geração")
                    self.status_var.set(f"Erro no Parceiro de Pesquisa I.A.: {msg}")
                    messagebox.showerror("Erro da I.A.", f"Falha ao gerar sugestão de protocolo com a I.A.:\n\n{msg}")
                self.after(0, on_err)

        threading.Thread(target=worker, daemon=True).start()

    def advance_from_protocol(self, show_msg=True):
        """Passes protocol configurations to Configuração Geral and Triagem tabs and switches tabs."""
        proto_data = self.collect_protocol_data()
        fields = proto_data.get("fields", {})
        
        # 1. Project Title
        title = fields.get("titulo", "").strip()
        if title:
            self.ent_project_name.delete(0, tk.END)
            self.ent_project_name.insert(0, title)
            
        # 2. Keywords / Search Strategy
        busca_text = fields.get("busca", "").strip()
        self.keywords = []
        
        def parse_and_expand_query(query_str):
            query_str = query_str.strip()
            if not query_str:
                return []
                
            # Parse parts separated by top-level ' AND ' (outside parentheses and quotes)
            parts = []
            current_part = []
            paren_depth = 0
            in_quotes = False
            i = 0
            while i < len(query_str):
                c = query_str[i]
                if c == '"':
                    in_quotes = not in_quotes
                    current_part.append(c)
                elif c == '(' and not in_quotes:
                    paren_depth += 1
                    current_part.append(c)
                elif c == ')' and not in_quotes:
                    paren_depth -= 1
                    current_part.append(c)
                elif not in_quotes and paren_depth == 0 and query_str[i:i+5].upper() == ' AND ':
                    parts.append("".join(current_part).strip())
                    current_part = []
                    i += 4  # skip ' AND'
                else:
                    current_part.append(c)
                i += 1
            if current_part:
                parts.append("".join(current_part).strip())
                
            expanded_lists = []
            for part in parts:
                part_clean = part.strip()
                # Strip outer wrapping parentheses if they wrap the entire part, e.g. "(A OR B)" -> "A OR B"
                if part_clean.startswith('(') and part_clean.endswith(')'):
                    # Check paren balance to make sure the outer parens actually match
                    depth = 0
                    is_wrapped = True
                    for char in part_clean[1:-1]:
                        if char == '(':
                            depth += 1
                        elif char == ')':
                            depth -= 1
                        if depth < 0:
                            is_wrapped = False
                            break
                    if is_wrapped:
                        part_clean = part_clean[1:-1].strip()
                        
                # Split this part by top-level ' OR ' (outside quotes/parentheses)
                terms = []
                current_term = []
                paren_depth = 0
                in_quotes = False
                j = 0
                while j < len(part_clean):
                    c = part_clean[j]
                    if c == '"':
                        in_quotes = not in_quotes
                        current_term.append(c)
                    elif c == '(' and not in_quotes:
                        paren_depth += 1
                        current_term.append(c)
                    elif c == ')' and not in_quotes:
                        paren_depth -= 1
                        current_term.append(c)
                    elif not in_quotes and paren_depth == 0 and part_clean[j:j+4].upper() == ' OR ':
                        terms.append("".join(current_term).strip())
                        current_term = []
                        j += 3  # skip ' OR'
                    else:
                        current_term.append(c)
                    j += 1
                if current_term:
                    terms.append("".join(current_term).strip())
                    
                expanded_lists.append(terms)
                
            import itertools
            combinations = []
            for prod in itertools.product(*expanded_lists):
                combinations.append(" AND ".join(prod))
            return combinations

        if busca_text:
            for line in busca_text.split('\n'):
                line_clean = line.strip()
                if line_clean:
                    # Strip any leading database prefixes, labels or markers (e.g. SCIELO/BDTD: ..., [SciELO]: ..., PubMed: ...)
                    match_bracket = re.match(r'^\[([^\]]+)\]\s*:\s*(.+)$', line_clean)
                    if match_bracket:
                        line_clean = match_bracket.group(2).strip()
                    else:
                        match_prefix = re.match(r'^(?:SciELO|BDTD|OpenAlex|PubMed|Scopus|Google\s*Scholar|Bases?|Estrat[ée]gia|String(?:\s+de\s+busca)?|Busca)(?:\s*/\s*(?:SciELO|BDTD|OpenAlex|PubMed|Scopus|Google\s*Scholar))*\s*:\s*(.+)$', line_clean, re.IGNORECASE)
                        if match_prefix:
                            line_clean = match_prefix.group(1).strip()
                        else:
                            match_generic = re.match(r'^[A-Za-z0-9_\s/\[\]\.-]+\s*:\s*([\("].+)$', line_clean)
                            if match_generic:
                                line_clean = match_generic.group(1).strip()

                    if line_clean:
                        expanded = parse_and_expand_query(line_clean)
                        for q in expanded:
                            if q and q not in self.keywords:
                                self.keywords.append(q)
        self.update_keywords_listbox()
        
        # 3. Enabled databases
        dbs = fields.get("databases", {})
        self.var_scielo_enabled.set(dbs.get("SciELO", False))
        self.var_run_scielo.set(dbs.get("SciELO", False))
        self.toggle_scielo_fields()
        
        self.var_bdtd_enabled.set(dbs.get("BDTD", False))
        self.var_run_bdtd.set(dbs.get("BDTD", False))
        self.toggle_bdtd_fields()
        
        # 4. Temporal Limits (mapping to BDTD publishDate)
        ano_inicio = fields.get("limite_ano_inicio", "").strip()
        if ano_inicio:
            ano_fim = fields.get("limite_ano_fim", "").strip()
            if not ano_fim:
                ano_fim = str(pd.Timestamp.now().year)
            
            date_range = f"[{ano_inicio} TO {ano_fim}]"
            self.ent_bdtd_filter_date.delete(0, tk.END)
            self.ent_bdtd_filter_date.insert(0, date_range)
            
        # 5. Language Limits (mapping to BDTD language filter)
        idioma = fields.get("idioma", "").strip()
        if idioma:
            self.ent_bdtd_filter_lang.delete(0, tk.END)
            self.ent_bdtd_filter_lang.insert(0, idioma)
            
        # 6. Inclusion / Exclusion Criteria (mapping to Triagem de Trabalhos)
        inc_text = fields.get("criterios_inclusao", "").strip()
        self.inclusion_criteria = []
        if inc_text:
            for line in inc_text.split('\n'):
                line_clean = line.strip()
                if line_clean:
                    self.inclusion_criteria.append(line_clean)
        
        # Always enforce that "Disponível com acesso público" is present
        if not any("acesso p" in c.lower() for c in self.inclusion_criteria):
            self.inclusion_criteria.append("Disponível com acesso público")
                    
        exc_text = fields.get("criterios_exclusao", "").strip()
        self.exclusion_criteria = []
        if exc_text:
            for line in exc_text.split('\n'):
                line_clean = line.strip()
                if line_clean:
                    self.exclusion_criteria.append(line_clean)
                    
        # Update Triagem listboxes
        self.lst_inc_criteria.delete(0, tk.END)
        for c in self.inclusion_criteria:
            self.lst_inc_criteria.insert(tk.END, c)
            
        self.lst_exc_criteria.delete(0, tk.END)
        for c in self.exclusion_criteria:
            self.lst_exc_criteria.insert(tk.END, c)
            
        # 7. Extraction Questions / Fields (mapping to Triagem 2 - Extração)
        ext_text = fields.get("campos_extracao", "").strip()
        self.campos_extracao = []
        if ext_text:
            for line in ext_text.split('\n'):
                line_clean = line.strip()
                if line_clean:
                    self.campos_extracao.append(line_clean)
                    
        if not self.campos_extracao:
            self.campos_extracao = [
                "Objetivo do Estudo",
                "Método / Abordagem",
                "Participantes / Amostra",
                "Principais Resultados",
                "Conclusões / Limitações"
            ]
            
        if hasattr(self, 'lst_ext_fields') and self.lst_ext_fields.winfo_exists():
            self.lst_ext_fields.delete(0, tk.END)
            for f in self.campos_extracao:
                self.lst_ext_fields.insert(tk.END, f)
            
        # Inform the user and transition to Tab 1 (Configuração Geral)
        if show_msg:
            messagebox.showinfo(
                "Configurações Geradas",
                "Configurações geradas a partir do protocolo com sucesso!\n\n"
                "As abas 'Configuração Geral', 'Triagem de Trabalhos' e 'Triagem 2 - Extração' foram pré-preenchidas com os dados informados."
            )
        
        self.notebook.select(self.tab_general)
        self.status_var.set("Aba de Configuração Geral pré-preenchida a partir do protocolo.")

    def load_protocol_and_configure(self):
        """Loads a project JSON (unified or legacy protocol), populates the form, and auto-configures search paths."""
        file_path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if not file_path:
            return
            
        try:
            if not self._load_unified_or_legacy(file_path):
                return

            # Auto-configure output directory to the folder containing the file
            proto_dir = os.path.dirname(file_path)
            proto_dir = proto_dir.replace("\\", "/")
            
            # Only auto-set paths if they are not already populated (from unified config)
            if not self.ent_output_dir.get().strip():
                self.ent_output_dir.delete(0, tk.END)
                self.ent_output_dir.insert(0, proto_dir)

            if not self.ent_bdtd_db.get().strip():
                self.ent_bdtd_db.delete(0, tk.END)
                self.ent_bdtd_db.insert(0, f"{proto_dir}/2_bdtd_metadata.db")
                self.ent_bdtd_export.delete(0, tk.END)
                self.ent_bdtd_export.insert(0, f"{proto_dir}/2_bdtd_resultados.xlsx")
                self.ent_scielo_db.delete(0, tk.END)
                self.ent_scielo_db.insert(0, f"{proto_dir}/2_scielo_metadata.db")
                self.ent_scielo_export.delete(0, tk.END)
                self.ent_scielo_export.insert(0, f"{proto_dir}/2_scielo_resultados.xlsx")
                self.ent_openalex_db.delete(0, tk.END)
                self.ent_openalex_db.insert(0, f"{proto_dir}/2_openalex_metadata.db")
                self.ent_openalex_export.delete(0, tk.END)
                self.ent_openalex_export.insert(0, f"{proto_dir}/2_openalex_resultados.xlsx")
                self.ent_pubmed_db.delete(0, tk.END)
                self.ent_pubmed_db.insert(0, f"{proto_dir}/2_pubmed_metadata.db")
                self.ent_pubmed_export.delete(0, tk.END)
                self.ent_pubmed_export.insert(0, f"{proto_dir}/2_pubmed_resultados.xlsx")
                self.ent_scopus_db.delete(0, tk.END)
                self.ent_scopus_db.insert(0, f"{proto_dir}/2_scopus_metadata.db")
                self.ent_scopus_export.delete(0, tk.END)
                self.ent_scopus_export.insert(0, f"{proto_dir}/2_scopus_resultados.xlsx")
            
            # Run the configuration transfer logic (without double alerts)
            self.advance_from_protocol(show_msg=False)
            
            self.status_var.set(f"Projeto carregado e busca configurada a partir de: {os.path.basename(file_path)}")
            messagebox.showinfo(
                "Projeto Carregado",
                f"Projeto carregado e configurado com sucesso!\n\n"
                f"Arquivo: {file_path}\n"
                f"Pasta de Saída definida: {self.ent_output_dir.get()}"
            )
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível carregar e configurar o projeto:\n{e}")

    def setup_tab_general(self):
        """Builds the General Settings tab."""
        inner = self._make_scrollable_tab(self.tab_general)
        # Project Name Card
        project_frame = ttk.LabelFrame(inner, text="Dados do Projeto", padding=15)
        project_frame.pack(fill="x", pady=(0, 15))
        project_frame.columnconfigure(1, weight=1)
        
        ttk.Label(project_frame, text="Nome da Revisão Sistemática:", style="Bold.TLabel").grid(row=0, column=0, sticky="w", pady=5)
        self.ent_project_name = ttk.Entry(project_frame)
        self.ent_project_name.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
        
        btn_import_proto = ttk.Button(
            project_frame,
            text="Carregar de Protocolo...",
            style="Secondary.TButton",
            command=self.load_protocol_and_configure
        )
        btn_import_proto.grid(row=0, column=2, sticky="w", padx=10, pady=5)
        
        # Keywords Card
        keywords_frame = ttk.LabelFrame(inner, text="Termos de Busca / Palavras-chave", padding=15)
        keywords_frame.pack(fill="x", pady=(0, 15))
        
        # Left side: Keywords List
        list_frame = ttk.Frame(keywords_frame)
        list_frame.pack(side="left", fill="both", expand=True)
        
        self.keyword_listbox = tk.Listbox(
            list_frame, 
            height=4, 
            selectmode=tk.SINGLE,
            font=("Segoe UI", 10),
            bd=1,
            highlightthickness=0,
            relief="solid"
        )
        self.keyword_listbox.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.keyword_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.keyword_listbox.config(yscrollcommand=scrollbar.set)
        
        # Right side: Add/Remove buttons and input
        actions_frame = ttk.Frame(keywords_frame, padding=(15, 0, 0, 0))
        actions_frame.pack(side="right", fill="y", anchor="n")
        
        ttk.Label(actions_frame, text="Novo Termo (Suporta operadores booleanos):", style="Bold.TLabel").pack(anchor="w", pady=(0, 5))
        self.ent_new_keyword = ttk.Entry(actions_frame, width=35)
        self.ent_new_keyword.pack(fill="x", pady=(0, 10))
        self.ent_new_keyword.bind("<Return>", lambda e: self.add_keyword())
        
        btn_add = ttk.Button(actions_frame, text="Adicionar Termo", style="Primary.TButton", command=self.add_keyword)
        btn_add.pack(fill="x", pady=2)
        
        btn_remove = ttk.Button(actions_frame, text="Remover Selecionado", style="Secondary.TButton", command=self.remove_keyword)
        btn_remove.pack(fill="x", pady=2)
        
        # Limits and delays Card
        limits_frame = ttk.LabelFrame(inner, text="Limites e Performance Globais", padding=15)
        limits_frame.pack(fill="x")
        
        ttk.Label(limits_frame, text="Limite Geral por Termo (Deixe em branco para todos):", style="Bold.TLabel").grid(row=0, column=0, sticky="w", pady=5)
        self.ent_global_limit = ttk.Entry(limits_frame, width=15)
        self.ent_global_limit.grid(row=0, column=1, sticky="w", padx=10, pady=5)
        
        ttk.Label(limits_frame, text="Intervalo entre Requisições (segundos):", style="Bold.TLabel").grid(row=1, column=0, sticky="w", pady=5)
        self.ent_global_delay = ttk.Entry(limits_frame, width=15)
        self.ent_global_delay.grid(row=1, column=1, sticky="w", padx=10, pady=5)

        # Search Execution Card
        exec_frame = ttk.LabelFrame(inner, text="Execução da Busca", padding=15)
        exec_frame.pack(fill="x", pady=(15, 0))
        exec_frame.columnconfigure(1, weight=1)
        
        # Folder selection
        ttk.Label(exec_frame, text="Pasta de Destino para Resultados:", style="Bold.TLabel").grid(row=0, column=0, sticky="w", pady=5)
        self.ent_output_dir = ttk.Entry(exec_frame)
        self.ent_output_dir.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
        
        btn_sel_dir = ttk.Button(exec_frame, text="Selecionar...", style="Secondary.TButton", command=self.select_output_dir)
        btn_sel_dir.grid(row=0, column=2, sticky="w", padx=5, pady=5)
        
        # Harvester execution checkboxes
        chk_frame = ttk.Frame(exec_frame)
        chk_frame.grid(row=1, column=0, columnspan=3, sticky="w", pady=10)
        
        ttk.Checkbutton(chk_frame, text="Executar BDTD", variable=self.var_run_bdtd).pack(side="left", padx=(0, 10))
        ttk.Checkbutton(chk_frame, text="Executar SciELO", variable=self.var_run_scielo).pack(side="left", padx=10)
        ttk.Checkbutton(chk_frame, text="Executar OpenAlex", variable=self.var_run_openalex).pack(side="left", padx=10)
        ttk.Checkbutton(chk_frame, text="Executar PubMed", variable=self.var_run_pubmed).pack(side="left", padx=10)
        ttk.Checkbutton(chk_frame, text="Executar Scopus", variable=self.var_run_scopus).pack(side="left", padx=10)
        
        # Execute button
        btn_run = ttk.Button(exec_frame, text="Executar Busca", style="Primary.TButton", command=self.run_search_execution)
        btn_run.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(5, 0))

        # Gemini AI Configuration Card
        gemini_frame = ttk.LabelFrame(inner, text="Configuração do Gemini AI (Parceiro de Triagem)", padding=15)
        gemini_frame.pack(fill="x", pady=(15, 0))
        gemini_frame.columnconfigure(1, weight=1)

        # --- Multi API Key Management ---
        ttk.Label(gemini_frame, text="Chaves de API do Gemini:", style="Bold.TLabel").grid(row=0, column=0, sticky="nw", pady=5)

        keys_container = ttk.Frame(gemini_frame)
        keys_container.grid(row=0, column=1, columnspan=2, sticky="ew", padx=10, pady=5)
        keys_container.columnconfigure(0, weight=1)

        self.lst_gemini_keys = tk.Listbox(keys_container, height=4, font=("Segoe UI", 9), selectmode=tk.SINGLE)
        self.lst_gemini_keys.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self._refresh_gemini_keys_listbox()

        self.lbl_gemini_key_status = ttk.Label(keys_container, text="", foreground="#555555", font=("Segoe UI", 8))
        self.lbl_gemini_key_status.grid(row=1, column=0, sticky="w")
        self._update_gemini_key_status_label()

        # Add key row
        add_key_frame = ttk.Frame(keys_container)
        add_key_frame.grid(row=2, column=0, sticky="ew", pady=(5, 0))
        add_key_frame.columnconfigure(0, weight=1)

        self.ent_new_gemini_key = ttk.Entry(add_key_frame, show="*", width=40)
        self.ent_new_gemini_key.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.ent_new_gemini_key.bind("<Return>", lambda e: self._add_gemini_key())

        btn_keys_frame = ttk.Frame(add_key_frame)
        btn_keys_frame.grid(row=0, column=1, sticky="e")

        ttk.Button(btn_keys_frame, text="+ Adicionar", style="Secondary.TButton", command=self._add_gemini_key).pack(side="left", padx=2)
        ttk.Button(btn_keys_frame, text="- Remover", style="Secondary.TButton", command=self._remove_gemini_key).pack(side="left", padx=2)

        # --- Model selector ---
        ttk.Label(gemini_frame, text="Modelo do Gemini:", style="Bold.TLabel").grid(row=1, column=0, sticky="w", pady=5)
        cb_gemini_model = ttk.Combobox(
            gemini_frame,
            textvariable=self.gemini_model,
            values=["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash", "gemini-1.5-flash", "gemini-2.5-pro"],
            state="normal",
            width=25
        )
        cb_gemini_model.grid(row=1, column=1, sticky="w", padx=10, pady=5)

        # --- Action buttons ---
        btn_gemini_actions = ttk.Frame(gemini_frame)
        btn_gemini_actions.grid(row=2, column=0, columnspan=3, sticky="w", pady=(10, 0))

        btn_save_gemini = ttk.Button(btn_gemini_actions, text="Salvar Configuração", style="Primary.TButton", command=self.save_gemini_config)
        btn_save_gemini.pack(side="left", padx=(0, 10))

        btn_test_gemini = ttk.Button(btn_gemini_actions, text="Testar Conexão API", style="Secondary.TButton", command=self.test_gemini_connection)
        btn_test_gemini.pack(side="left")

    def setup_tab_bdtd(self):
        """Builds the BDTD Harvester settings tab."""
        inner = self._make_scrollable_tab(self.tab_bdtd)
        # Enable Source
        self.var_bdtd_enabled = tk.BooleanVar(value=True)
        chk_enabled = ttk.Checkbutton(inner, text="Ativar Coleta na BDTD", variable=self.var_bdtd_enabled, command=self.toggle_bdtd_fields)
        chk_enabled.pack(anchor="w", pady=(0, 10))
        
        self.bdtd_container = ttk.LabelFrame(inner, text="Parâmetros de Coleta da BDTD", padding=15)
        self.bdtd_container.pack(fill="x")
        self.bdtd_container.columnconfigure(1, weight=1)
        
        # File paths
        ttk.Label(self.bdtd_container, text="Arquivo de Banco SQLite:", style="Bold.TLabel").grid(row=0, column=0, sticky="w", pady=5)
        self.ent_bdtd_db = ttk.Entry(self.bdtd_container)
        self.ent_bdtd_db.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
        btn_bdtd_db_browse = ttk.Button(self.bdtd_container, text="Procurar...", style="Secondary.TButton", command=lambda: self.browse_file(self.ent_bdtd_db, [("SQLite Database", "*.db")]))
        btn_bdtd_db_browse.grid(row=0, column=2, sticky="w", pady=5)
        
        ttk.Label(self.bdtd_container, text="Excel de Saída:", style="Bold.TLabel").grid(row=1, column=0, sticky="w", pady=5)
        self.ent_bdtd_export = ttk.Entry(self.bdtd_container)
        self.ent_bdtd_export.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        btn_bdtd_exp_browse = ttk.Button(self.bdtd_container, text="Procurar...", style="Secondary.TButton", command=lambda: self.browse_file(self.ent_bdtd_export, [("Excel Spreadsheet", "*.xlsx")], save=True))
        btn_bdtd_exp_browse.grid(row=1, column=2, sticky="w", pady=5)
        
        # Search & Sort API parameters
        ttk.Label(self.bdtd_container, text="Tipo de Busca (Campo):", style="Bold.TLabel").grid(row=2, column=0, sticky="w", pady=5)
        self.cb_bdtd_search = ttk.Combobox(self.bdtd_container, values=["AllFields", "Title", "Author", "Subject", "Advisor"], state="readonly", width=18)
        self.cb_bdtd_search.grid(row=2, column=1, sticky="w", padx=10, pady=5)
        
        ttk.Label(self.bdtd_container, text="Ordenação:", style="Bold.TLabel").grid(row=3, column=0, sticky="w", pady=5)
        self.cb_bdtd_sort = ttk.Combobox(self.bdtd_container, values=["year", "year asc", "relevance", "title", "author"], state="readonly", width=18)
        self.cb_bdtd_sort.grid(row=3, column=1, sticky="w", padx=10, pady=5)
        
        # Scrape details mode (Raspagem de Detalhes vs Coleta Rápida)
        ttk.Label(self.bdtd_container, text="Modo de Coleta (Scraping):", style="Bold.TLabel").grid(row=4, column=0, sticky="w", pady=5)
        self.var_bdtd_scrape_details = tk.BooleanVar(value=True)
        self.chk_bdtd_scrape = ttk.Checkbutton(
            self.bdtd_container,
            text="Coletar Detalhes (Orientador e Instituição na página web - Lento mas completo)",
            variable=self.var_bdtd_scrape_details
        )
        self.chk_bdtd_scrape.grid(row=4, column=1, columnspan=2, sticky="w", padx=10, pady=5)
        
        # Filters sub-frame
        filters_frame = ttk.LabelFrame(self.bdtd_container, text="Filtros Específicos BDTD (Opcional)", padding=10)
        filters_frame.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=(15, 0))
        
        # Configure filters
        ttk.Label(filters_frame, text="Tipo de Documento:", style="Bold.TLabel").grid(row=0, column=0, sticky="w", pady=5)
        self.cb_bdtd_filter_format = ttk.Combobox(filters_frame, values=["", "doctoralThesis", "masterThesis", "article"], state="readonly", width=18)
        self.cb_bdtd_filter_format.grid(row=0, column=1, sticky="w", padx=10, pady=5)
        
        ttk.Label(filters_frame, text="Instituição (Sigla):", style="Bold.TLabel").grid(row=0, column=2, sticky="w", padx=10, pady=5)
        self.ent_bdtd_filter_inst = ttk.Entry(filters_frame, width=15)
        self.ent_bdtd_filter_inst.grid(row=0, column=3, sticky="w", pady=5)
        
        ttk.Label(filters_frame, text="Ano Publicação (ex: 2025 ou [2020 TO 2026]):", style="Bold.TLabel").grid(row=1, column=0, sticky="w", pady=5)
        self.ent_bdtd_filter_date = ttk.Entry(filters_frame, width=20)
        self.ent_bdtd_filter_date.grid(row=1, column=1, sticky="w", padx=10, pady=5)
        
        ttk.Label(filters_frame, text="Idioma (ex: por, eng, spa):", style="Bold.TLabel").grid(row=1, column=2, sticky="w", padx=10, pady=5)
        self.ent_bdtd_filter_lang = ttk.Entry(filters_frame, width=15)
        self.ent_bdtd_filter_lang.grid(row=1, column=3, sticky="w", pady=5)

    def setup_tab_scielo(self):
        """Builds the SciELO Harvester settings tab."""
        inner = self._make_scrollable_tab(self.tab_scielo)
        # Enable Source
        self.var_scielo_enabled = tk.BooleanVar(value=True)
        chk_enabled = ttk.Checkbutton(inner, text="Ativar Coleta no SciELO", variable=self.var_scielo_enabled, command=self.toggle_scielo_fields)
        chk_enabled.pack(anchor="w", pady=(0, 10))
        
        self.scielo_container = ttk.LabelFrame(inner, text="Parâmetros de Coleta do SciELO", padding=15)
        self.scielo_container.pack(fill="x")
        self.scielo_container.columnconfigure(1, weight=1)
        
        # File paths
        ttk.Label(self.scielo_container, text="Arquivo de Banco SQLite:", style="Bold.TLabel").grid(row=0, column=0, sticky="w", pady=5)
        self.ent_scielo_db = ttk.Entry(self.scielo_container)
        self.ent_scielo_db.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
        btn_scielo_db_browse = ttk.Button(self.scielo_container, text="Procurar...", style="Secondary.TButton", command=lambda: self.browse_file(self.ent_scielo_db, [("SQLite Database", "*.db")]))
        btn_scielo_db_browse.grid(row=0, column=2, sticky="w", pady=5)
        
        ttk.Label(self.scielo_container, text="Excel de Saída:", style="Bold.TLabel").grid(row=1, column=0, sticky="w", pady=5)
        self.ent_scielo_export = ttk.Entry(self.scielo_container)
        self.ent_scielo_export.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        btn_scielo_exp_browse = ttk.Button(self.scielo_container, text="Procurar...", style="Secondary.TButton", command=lambda: self.browse_file(self.ent_scielo_export, [("Excel Spreadsheet", "*.xlsx")], save=True))
        btn_scielo_exp_browse.grid(row=1, column=2, sticky="w", pady=5)
        
        # Search API parameters
        ttk.Label(self.scielo_container, text="Campo de Busca (Vazio = todos):", style="Bold.TLabel").grid(row=2, column=0, sticky="w", pady=5)
        self.ent_scielo_search_field = ttk.Entry(self.scielo_container, width=20)
        self.ent_scielo_search_field.grid(row=2, column=1, sticky="w", padx=10, pady=5)

    def setup_tab_openalex(self):
        """Builds the OpenAlex Harvester settings tab."""
        inner = self._make_scrollable_tab(self.tab_openalex)
        self.var_openalex_enabled = tk.BooleanVar(value=True)
        chk_enabled = ttk.Checkbutton(inner, text="Ativar Coleta no OpenAlex", variable=self.var_openalex_enabled, command=self.toggle_openalex_fields)
        chk_enabled.pack(anchor="w", pady=(0, 10))
        
        self.openalex_container = ttk.LabelFrame(inner, text="Parâmetros de Coleta do OpenAlex", padding=15)
        self.openalex_container.pack(fill="x")
        self.openalex_container.columnconfigure(1, weight=1)
        
        # File paths
        ttk.Label(self.openalex_container, text="Arquivo de Banco SQLite:", style="Bold.TLabel").grid(row=0, column=0, sticky="w", pady=5)
        self.ent_openalex_db = ttk.Entry(self.openalex_container)
        self.ent_openalex_db.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
        btn_db_browse = ttk.Button(self.openalex_container, text="Procurar...", style="Secondary.TButton", command=lambda: self.browse_file(self.ent_openalex_db, [("SQLite Database", "*.db")]))
        btn_db_browse.grid(row=0, column=2, sticky="w", pady=5)
        
        ttk.Label(self.openalex_container, text="Excel de Saída:", style="Bold.TLabel").grid(row=1, column=0, sticky="w", pady=5)
        self.ent_openalex_export = ttk.Entry(self.openalex_container)
        self.ent_openalex_export.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        btn_exp_browse = ttk.Button(self.openalex_container, text="Procurar...", style="Secondary.TButton", command=lambda: self.browse_file(self.ent_openalex_export, [("Excel Spreadsheet", "*.xlsx")], save=True))
        btn_exp_browse.grid(row=1, column=2, sticky="w", pady=5)
        
        # Contact email and API key
        ttk.Label(self.openalex_container, text="E-mail de Contato (Polite Pool):", style="Bold.TLabel").grid(row=2, column=0, sticky="w", pady=5)
        self.ent_openalex_email = ttk.Entry(self.openalex_container, width=30)
        self.ent_openalex_email.grid(row=2, column=1, sticky="w", padx=10, pady=5)
        
        ttk.Label(self.openalex_container, text="API Key (Opcional):", style="Bold.TLabel").grid(row=3, column=0, sticky="w", pady=5)
        self.ent_openalex_api_key = ttk.Entry(self.openalex_container, width=30)
        self.ent_openalex_api_key.grid(row=3, column=1, sticky="w", padx=10, pady=5)
        
        # Filters sub-frame
        filters_frame = ttk.LabelFrame(self.openalex_container, text="Filtros Específicos OpenAlex (Opcional)", padding=10)
        filters_frame.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=(15, 0))
        
        ttk.Label(filters_frame, text="Tipo de Obra (Work Type):", style="Bold.TLabel").grid(row=0, column=0, sticky="w", pady=5)
        self.cb_openalex_filter_type = ttk.Combobox(filters_frame, values=["", "article", "book", "dataset", "dissertation", "reference-entry"], state="readonly", width=18)
        self.cb_openalex_filter_type.grid(row=0, column=1, sticky="w", padx=10, pady=5)
        
        ttk.Label(filters_frame, text="Ano Publicação (ex: 2025 ou 2020-2026):", style="Bold.TLabel").grid(row=0, column=2, sticky="w", padx=10, pady=5)
        self.ent_openalex_filter_year = ttk.Entry(filters_frame, width=15)
        self.ent_openalex_filter_year.grid(row=0, column=3, sticky="w", pady=5)
        
        ttk.Label(filters_frame, text="Idioma (ex: pt, en, es):", style="Bold.TLabel").grid(row=1, column=0, sticky="w", pady=5)
        self.ent_openalex_filter_lang = ttk.Entry(filters_frame, width=15)
        self.ent_openalex_filter_lang.grid(row=1, column=1, sticky="w", padx=10, pady=5)

    def setup_tab_pubmed(self):
        """Builds the PubMed Harvester settings tab."""
        inner = self._make_scrollable_tab(self.tab_pubmed)
        self.var_pubmed_enabled = tk.BooleanVar(value=True)
        chk_enabled = ttk.Checkbutton(inner, text="Ativar Coleta no PubMed", variable=self.var_pubmed_enabled, command=self.toggle_pubmed_fields)
        chk_enabled.pack(anchor="w", pady=(0, 10))
        
        self.pubmed_container = ttk.LabelFrame(inner, text="Parâmetros de Coleta do PubMed", padding=15)
        self.pubmed_container.pack(fill="x")
        self.pubmed_container.columnconfigure(1, weight=1)
        
        # File paths
        ttk.Label(self.pubmed_container, text="Arquivo de Banco SQLite:", style="Bold.TLabel").grid(row=0, column=0, sticky="w", pady=5)
        self.ent_pubmed_db = ttk.Entry(self.pubmed_container)
        self.ent_pubmed_db.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
        btn_db_browse = ttk.Button(self.pubmed_container, text="Procurar...", style="Secondary.TButton", command=lambda: self.browse_file(self.ent_pubmed_db, [("SQLite Database", "*.db")]))
        btn_db_browse.grid(row=0, column=2, sticky="w", pady=5)
        
        ttk.Label(self.pubmed_container, text="Excel de Saída:", style="Bold.TLabel").grid(row=1, column=0, sticky="w", pady=5)
        self.ent_pubmed_export = ttk.Entry(self.pubmed_container)
        self.ent_pubmed_export.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        btn_exp_browse = ttk.Button(self.pubmed_container, text="Procurar...", style="Secondary.TButton", command=lambda: self.browse_file(self.ent_pubmed_export, [("Excel Spreadsheet", "*.xlsx")], save=True))
        btn_exp_browse.grid(row=1, column=2, sticky="w", pady=5)
        
        # API key
        ttk.Label(self.pubmed_container, text="API Key (Opcional):", style="Bold.TLabel").grid(row=2, column=0, sticky="w", pady=5)
        self.ent_pubmed_api_key = ttk.Entry(self.pubmed_container, width=30)
        self.ent_pubmed_api_key.grid(row=2, column=1, sticky="w", padx=10, pady=5)

    def setup_tab_scopus(self):
        """Builds the Scopus Harvester settings tab."""
        inner = self._make_scrollable_tab(self.tab_scopus)
        self.var_scopus_enabled = tk.BooleanVar(value=True)
        chk_enabled = ttk.Checkbutton(inner, text="Ativar Coleta no Scopus", variable=self.var_scopus_enabled, command=self.toggle_scopus_fields)
        chk_enabled.pack(anchor="w", pady=(0, 10))
        
        self.scopus_container = ttk.LabelFrame(inner, text="Parâmetros de Coleta do Scopus", padding=15)
        self.scopus_container.pack(fill="x")
        self.scopus_container.columnconfigure(1, weight=1)
        
        # File paths
        ttk.Label(self.scopus_container, text="Arquivo de Banco SQLite:", style="Bold.TLabel").grid(row=0, column=0, sticky="w", pady=5)
        self.ent_scopus_db = ttk.Entry(self.scopus_container)
        self.ent_scopus_db.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
        btn_db_browse = ttk.Button(self.scopus_container, text="Procurar...", style="Secondary.TButton", command=lambda: self.browse_file(self.ent_scopus_db, [("SQLite Database", "*.db")]))
        btn_db_browse.grid(row=0, column=2, sticky="w", pady=5)
        
        ttk.Label(self.scopus_container, text="Excel de Saída:", style="Bold.TLabel").grid(row=1, column=0, sticky="w", pady=5)
        self.ent_scopus_export = ttk.Entry(self.scopus_container)
        self.ent_scopus_export.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        btn_exp_browse = ttk.Button(self.scopus_container, text="Procurar...", style="Secondary.TButton", command=lambda: self.browse_file(self.ent_scopus_export, [("Excel Spreadsheet", "*.xlsx")], save=True))
        btn_exp_browse.grid(row=1, column=2, sticky="w", pady=5)
        
        # API key and View
        ttk.Label(self.scopus_container, text="API Key (Obrigatória):", style="Bold.TLabel").grid(row=2, column=0, sticky="w", pady=5)
        self.ent_scopus_api_key = ttk.Entry(self.scopus_container, width=35)
        self.ent_scopus_api_key.grid(row=2, column=1, sticky="w", padx=10, pady=5)
        
        ttk.Label(self.scopus_container, text="API View (Detalhe):", style="Bold.TLabel").grid(row=3, column=0, sticky="w", pady=5)
        self.cb_scopus_view = ttk.Combobox(self.scopus_container, values=["COMPLETE", "STANDARD"], state="readonly", width=12)
        self.cb_scopus_view.grid(row=3, column=1, sticky="w", padx=10, pady=5)
        self.cb_scopus_view.set("COMPLETE")

    def load_default_values(self):
        """Fills the inputs with initial default settings."""
        self.ent_project_name.insert(0, "Revisão Sistemática de Planejamento")
        self.ent_global_limit.insert(0, "")
        self.ent_global_delay.insert(0, "2.5")
        
        # Keywords
        default_kws = [
            '("Inferencia causal" OR "descoberta causal")',
            "desenvolvimento regional",
            "planejamento urbano"
        ]
        for kw in default_kws:
            self.keywords.append(kw)
            self.keyword_listbox.insert(tk.END, kw)
            
        # BDTD defaults
        self.ent_bdtd_db.insert(0, "2_bdtd_metadata.db")
        self.ent_bdtd_export.insert(0, "2_bdtd_resultados.xlsx")
        self.cb_bdtd_search.set("AllFields")
        self.cb_bdtd_sort.set("year")
        if hasattr(self, 'var_bdtd_scrape_details'):
            self.var_bdtd_scrape_details.set(True)
        
        # SciELO defaults
        self.ent_scielo_db.insert(0, "2_scielo_metadata.db")
        self.ent_scielo_export.insert(0, "2_scielo_resultados.xlsx")
        self.ent_scielo_search_field.insert(0, "")
        
        # OpenAlex defaults
        self.ent_openalex_db.insert(0, "2_openalex_metadata.db")
        self.ent_openalex_export.insert(0, "2_openalex_resultados.xlsx")
        self.ent_openalex_email.insert(0, "eduardo.figueira@sou.unijui.edu.br")
        self.ent_openalex_api_key.insert(0, "sdAhuGYkdFV4Wz3UQdIGPr")
        self.cb_openalex_filter_type.set("")
        self.ent_openalex_filter_year.insert(0, "")
        self.ent_openalex_filter_lang.insert(0, "")
        
        # PubMed defaults
        self.ent_pubmed_db.insert(0, "2_pubmed_metadata.db")
        self.ent_pubmed_export.insert(0, "2_pubmed_resultados.xlsx")
        self.ent_pubmed_api_key.insert(0, "")
        
        # Scopus defaults
        self.ent_scopus_db.insert(0, "2_scopus_metadata.db")
        self.ent_scopus_export.insert(0, "2_scopus_resultados.xlsx")
        self.ent_scopus_api_key.insert(0, "33698870c47d2706e3a3fc4c03397832")
        self.cb_scopus_view.set("COMPLETE")

    def toggle_bdtd_fields(self):
        """Enables/disables BDTD inputs based on enabled checkbox."""
        state = "normal" if self.var_bdtd_enabled.get() else "disabled"
        for child in self.bdtd_container.winfo_children():
            # Check recursively if child contains other frames (like filters)
            if isinstance(child, ttk.LabelFrame):
                for sub_child in child.winfo_children():
                    if hasattr(sub_child, "configure"):
                        # Keep state readonly for comboboxes if they are enabled
                        if isinstance(sub_child, ttk.Combobox) and state == "normal":
                            sub_child.configure(state="readonly")
                        else:
                            sub_child.configure(state=state)
            else:
                if hasattr(child, "configure"):
                    if isinstance(child, ttk.Combobox) and state == "normal":
                        child.configure(state="readonly")
                    else:
                        child.configure(state=state)

    def toggle_scielo_fields(self):
        """Enables/disables SciELO inputs based on enabled checkbox."""
        state = "normal" if self.var_scielo_enabled.get() else "disabled"
        for child in self.scielo_container.winfo_children():
            if hasattr(child, "configure"):
                child.configure(state=state)

    def toggle_openalex_fields(self):
        """Enables/disables OpenAlex inputs based on enabled checkbox."""
        state = "normal" if self.var_openalex_enabled.get() else "disabled"
        for child in self.openalex_container.winfo_children():
            if isinstance(child, ttk.LabelFrame):
                for sub_child in child.winfo_children():
                    if hasattr(sub_child, "configure"):
                        if isinstance(sub_child, ttk.Combobox) and state == "normal":
                            sub_child.configure(state="readonly")
                        else:
                            sub_child.configure(state=state)
            else:
                if hasattr(child, "configure"):
                    if isinstance(child, ttk.Combobox) and state == "normal":
                        child.configure(state="readonly")
                    else:
                        child.configure(state=state)

    def toggle_pubmed_fields(self):
        """Enables/disables PubMed inputs based on enabled checkbox."""
        state = "normal" if self.var_pubmed_enabled.get() else "disabled"
        for child in self.pubmed_container.winfo_children():
            if hasattr(child, "configure"):
                child.configure(state=state)

    def toggle_scopus_fields(self):
        """Enables/disables Scopus inputs based on enabled checkbox."""
        state = "normal" if self.var_scopus_enabled.get() else "disabled"
        for child in self.scopus_container.winfo_children():
            if hasattr(child, "configure"):
                if isinstance(child, ttk.Combobox) and state == "normal":
                    child.configure(state="readonly")
                else:
                    child.configure(state=state)

    def browse_file(self, entry_widget, filetypes, save=False):
        """Opens a file dialog to pick database or excel paths."""
        if save:
            filename = filedialog.asksaveasfilename(defaultextension=filetypes[0][1][1:], filetypes=filetypes)
        else:
            filename = filedialog.askopenfilename(filetypes=filetypes)
            
        if filename:
            # Normalize path to relative if it is inside the workspace
            try:
                relpath = os.path.relpath(filename)
                if not relpath.startswith(".."):
                    filename = relpath
            except ValueError:
                pass
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, filename)

    def add_keyword(self):
        """Adds a keyword to the listbox."""
        kw = self.ent_new_keyword.get().strip()
        if kw:
            if kw not in self.keywords:
                self.keywords.append(kw)
                self.keyword_listbox.insert(tk.END, kw)
                self.ent_new_keyword.delete(0, tk.END)
                self.status_var.set(f"Termo adicionado: '{kw}'")
            else:
                messagebox.showwarning("Aviso", "Este termo de busca já existe na lista.")
        else:
            messagebox.showwarning("Aviso", "Digite um termo de busca válido.")

    def remove_keyword(self):
        """Removes the selected keyword from the listbox."""
        try:
            index = self.keyword_listbox.curselection()[0]
            kw = self.keywords.pop(index)
            self.keyword_listbox.delete(index)
            self.status_var.set(f"Termo removido: '{kw}'")
        except IndexError:
            messagebox.showwarning("Aviso", "Selecione um termo na lista para remover.")

    def update_keywords_listbox(self):
        """Refreshes the keyword listbox to match self.keywords."""
        self.keyword_listbox.delete(0, tk.END)
        for kw in self.keywords:
            self.keyword_listbox.insert(tk.END, kw)

    def collect_data(self):
        """Aggregates all form data into the unified config structure."""
        # Basic validation
        project_name = self.ent_project_name.get().strip()
        if not project_name:
            messagebox.showerror("Erro", "O Nome da Revisão Sistemática é obrigatório.")
            return None
            
        if not self.keywords:
            messagebox.showerror("Erro", "Adicione pelo menos um Termo de Busca.")
            return None
            
        limit_val = self.ent_global_limit.get().strip()
        limit = None
        if limit_val:
            try:
                limit = int(limit_val)
            except ValueError:
                messagebox.showerror("Erro", "O Limite Geral deve ser um número inteiro válido ou vazio.")
                return None
                
        delay_val = self.ent_global_delay.get().strip()
        try:
            delay = float(delay_val)
        except ValueError:
            messagebox.showerror("Erro", "O Intervalo entre Requisições deve ser um número decimal válido (ex: 2.5).")
            return None
            
        # Build systematic_review metadata
        config = {
            "systematic_review": {
                "project_name": project_name,
                "keywords": self.keywords,
                "global_limit": limit,
                "global_delay": delay
            },
            "sources": {}
        }
        
        # BDTD configurations
        bdtd_enabled = self.var_bdtd_enabled.get()
        if bdtd_enabled:
            db_path = self.ent_bdtd_db.get().strip()
            export_path = self.ent_bdtd_export.get().strip()
            
            if not db_path or not export_path:
                messagebox.showerror("Erro", "Para coletar na BDTD, os caminhos do Banco de Dados e do Excel são obrigatórios.")
                return None
                
            config["sources"]["bdtd"] = {
                "enabled": True,
                "db_path": db_path,
                "export_path": export_path,
                "search_type": self.cb_bdtd_search.get(),
                "sort_order": self.cb_bdtd_sort.get(),
                "scrape_details": self.var_bdtd_scrape_details.get() if hasattr(self, 'var_bdtd_scrape_details') else True,
                "filters": {
                    "format": self.cb_bdtd_filter_format.get(),
                    "institution": self.ent_bdtd_filter_inst.get().strip(),
                    "publishDate": self.ent_bdtd_filter_date.get().strip(),
                    "language": self.ent_bdtd_filter_lang.get().strip()
                }
            }
        else:
            config["sources"]["bdtd"] = {"enabled": False}
            
        # SciELO configurations
        scielo_enabled = self.var_scielo_enabled.get()
        if scielo_enabled:
            db_path = self.ent_scielo_db.get().strip()
            export_path = self.ent_scielo_export.get().strip()
            
            if not db_path or not export_path:
                messagebox.showerror("Erro", "Para coletar no SciELO, os caminhos do Banco de Dados e do Excel são obrigatórios.")
                return None
                
            config["sources"]["scielo"] = {
                "enabled": True,
                "db_path": db_path,
                "export_path": export_path,
                "search_field": self.ent_scielo_search_field.get().strip()
            }
        else:
            config["sources"]["scielo"] = {"enabled": False}
            
        # OpenAlex configurations
        openalex_enabled = self.var_openalex_enabled.get()
        if openalex_enabled:
            db_path = self.ent_openalex_db.get().strip()
            export_path = self.ent_openalex_export.get().strip()
            email = self.ent_openalex_email.get().strip()
            
            if not db_path or not export_path or not email:
                messagebox.showerror("Erro", "Para coletar na OpenAlex, os caminhos do Banco de Dados, do Excel e o E-mail de contato são obrigatórios.")
                return None
                
            config["sources"]["openalex"] = {
                "enabled": True,
                "db_path": db_path,
                "export_path": export_path,
                "email": email,
                "api_key": self.ent_openalex_api_key.get().strip(),
                "filters": {
                    "type": self.cb_openalex_filter_type.get(),
                    "publication_year": self.ent_openalex_filter_year.get().strip(),
                    "language": self.ent_openalex_filter_lang.get().strip()
                }
            }
        else:
            config["sources"]["openalex"] = {"enabled": False}

        # PubMed configurations
        pubmed_enabled = self.var_pubmed_enabled.get()
        if pubmed_enabled:
            db_path = self.ent_pubmed_db.get().strip()
            export_path = self.ent_pubmed_export.get().strip()
            
            if not db_path or not export_path:
                messagebox.showerror("Erro", "Para coletar no PubMed, os caminhos do Banco de Dados e do Excel são obrigatórios.")
                return None
                
            config["sources"]["pubmed"] = {
                "enabled": True,
                "db_path": db_path,
                "export_path": export_path,
                "api_key": self.ent_pubmed_api_key.get().strip()
            }
        else:
            config["sources"]["pubmed"] = {"enabled": False}

        # Scopus configurations
        scopus_enabled = self.var_scopus_enabled.get()
        if scopus_enabled:
            db_path = self.ent_scopus_db.get().strip()
            export_path = self.ent_scopus_export.get().strip()
            api_key = self.ent_scopus_api_key.get().strip()
            
            if not db_path or not export_path or not api_key:
                messagebox.showerror("Erro", "Para coletar no Scopus, os caminhos do Banco de Dados, do Excel e a API Key são obrigatórios.")
                return None
                
            config["sources"]["scopus"] = {
                "enabled": True,
                "db_path": db_path,
                "export_path": export_path,
                "api_key": api_key,
                "view": self.cb_scopus_view.get()
            }
        else:
            config["sources"]["scopus"] = {"enabled": False}
            
        return config

    def save_configuration(self):
        """Saves the entire project (unified JSON) from the Config Geral tab."""
        # Validate that config data is at least minimally valid before saving
        config_data = self.collect_data()
        if config_data is None:
            return # Validation failed
        self._save_unified_json()

    def setup_tab_triagem(self):
        """Builds the Screening (Triagem) tab layout."""
        # Main split: Left for configuration/controls, Right for review area
        paned = ttk.Panedwindow(self.tab_triagem, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True)
        
        # Left Panel (Configuration)
        left_panel = ttk.Frame(paned, width=320)
        paned.add(left_panel, weight=0)
        
        # Make left panel scrollable
        canvas = tk.Canvas(left_panel, borderwidth=0, highlightthickness=0, bg=self.bg_color)
        scrollbar = ttk.Scrollbar(left_panel, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        
        self.triagem_scroll_frame = ttk.Frame(canvas, padding=10)
        self.triagem_scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.triagem_scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Bind mouse wheel to scroll left panel
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        def _bind_triagem_mw(event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
        def _unbind_triagem_mw(event):
            canvas.unbind_all("<MouseWheel>")
        canvas.bind('<Enter>', _bind_triagem_mw)
        canvas.bind('<Leave>', _unbind_triagem_mw)
        
        # 1. Sources (CSV Files)
        files_frame = ttk.LabelFrame(self.triagem_scroll_frame, text="Arquivos de Resultados (.csv, .xlsx)", padding=10)
        files_frame.pack(fill="x", pady=5)
        
        self.lst_triagem_files = tk.Listbox(files_frame, height=4, font=("Segoe UI", 9))
        self.lst_triagem_files.pack(fill="x", pady=(0, 5))
        
        btn_files_frame = ttk.Frame(files_frame)
        btn_files_frame.pack(fill="x")
        ttk.Button(btn_files_frame, text="+ Adicionar", style="Secondary.TButton", command=self.add_triagem_csv).pack(side="left", padx=2)
        ttk.Button(btn_files_frame, text="- Remover", style="Secondary.TButton", command=self.remove_triagem_csv).pack(side="left", padx=2)
        
        # 2. Inclusion Criteria
        inc_frame = ttk.LabelFrame(self.triagem_scroll_frame, text="Critérios de Inclusão", padding=10)
        inc_frame.pack(fill="x", pady=5)
        
        self.lst_inc_criteria = tk.Listbox(inc_frame, height=4, font=("Segoe UI", 9))
        self.lst_inc_criteria.pack(fill="x", pady=(0, 5))
        
        self.ent_new_inc = ttk.Entry(inc_frame)
        self.ent_new_inc.pack(fill="x", pady=(0, 5))
        self.ent_new_inc.bind("<Return>", lambda e: self.add_inclusion_criterion())
        
        btn_inc_frame = ttk.Frame(inc_frame)
        btn_inc_frame.pack(fill="x")
        ttk.Button(btn_inc_frame, text="+ Adicionar", style="Secondary.TButton", command=self.add_inclusion_criterion).pack(side="left", padx=2)
        ttk.Button(btn_inc_frame, text="- Remover", style="Secondary.TButton", command=self.remove_inclusion_criterion).pack(side="left", padx=2)
        
        # 3. Exclusion Criteria
        exc_frame = ttk.LabelFrame(self.triagem_scroll_frame, text="Critérios de Exclusão", padding=10)
        exc_frame.pack(fill="x", pady=5)
        
        self.lst_exc_criteria = tk.Listbox(exc_frame, height=4, font=("Segoe UI", 9))
        self.lst_exc_criteria.pack(fill="x", pady=(0, 5))
        
        self.ent_new_exc = ttk.Entry(exc_frame)
        self.ent_new_exc.pack(fill="x", pady=(0, 5))
        self.ent_new_exc.bind("<Return>", lambda e: self.add_exclusion_criterion())
        
        btn_exc_frame = ttk.Frame(exc_frame)
        btn_exc_frame.pack(fill="x")
        ttk.Button(btn_exc_frame, text="+ Adicionar", style="Secondary.TButton", command=self.add_exclusion_criterion).pack(side="left", padx=2)
        ttk.Button(btn_exc_frame, text="- Remover", style="Secondary.TButton", command=self.remove_exclusion_criterion).pack(side="left", padx=2)
        
        # 4. Custom Questions
        q_frame = ttk.LabelFrame(self.triagem_scroll_frame, text="Perguntas da Triagem", padding=10)
        q_frame.pack(fill="x", pady=5)
        
        self.lst_triagem_questions = tk.Listbox(q_frame, height=4, font=("Segoe UI", 9))
        self.lst_triagem_questions.pack(fill="x", pady=(0, 5))
        
        self.ent_new_q = ttk.Entry(q_frame)
        self.ent_new_q.pack(fill="x", pady=(0, 5))
        self.ent_new_q.bind("<Return>", lambda e: self.add_triagem_question())
        
        btn_q_frame = ttk.Frame(q_frame)
        btn_q_frame.pack(fill="x")
        ttk.Button(btn_q_frame, text="+ Adicionar", style="Secondary.TButton", command=self.add_triagem_question).pack(side="left", padx=2)
        ttk.Button(btn_q_frame, text="- Remover", style="Secondary.TButton", command=self.remove_triagem_question).pack(side="left", padx=2)
        
        # 5. Session Actions
        actions_frame = ttk.LabelFrame(self.triagem_scroll_frame, text="Ações de Sessão", padding=10)
        actions_frame.pack(fill="x", pady=5)
        
        ttk.Button(actions_frame, text="Iniciar Triagem (Deduplicar)", style="Primary.TButton", command=self.start_triagem).pack(fill="x", pady=2)
        ttk.Button(actions_frame, text="Carregar Progresso (.json)", style="Secondary.TButton", command=self.load_triagem_session).pack(fill="x", pady=2)
        ttk.Button(actions_frame, text="Salvar Progresso (.json)", style="Primary.TButton", command=self.save_triagem_session).pack(fill="x", pady=2)
        
        # Right Panel (Work Area)
        right_panel = ttk.Frame(paned)
        paned.add(right_panel, weight=1)
        
        # Vertical split: Top for Treeview table, Bottom for paper details
        v_paned = ttk.Panedwindow(right_panel, orient=tk.VERTICAL)
        v_paned.pack(fill="both", expand=True)
        
        # Top Pane: Treeview list of papers
        tree_frame = ttk.LabelFrame(v_paned, text="Planilha de Revisão de Trabalhos", padding=10)
        v_paned.add(tree_frame, weight=1)
        
        # Toolbar for Batch AI Loop Screening
        tree_toolbar = ttk.Frame(tree_frame)
        tree_toolbar.pack(fill="x", pady=(0, 5))
        
        self.btn_batch_gemini_t1 = ttk.Button(tree_toolbar, text="⚡ Triar Todos com IA (Loop Contínuo)", style="Secondary.TButton", command=self.start_batch_gemini_triagem)
        self.btn_batch_gemini_t1.pack(side="left", padx=2)
        
        self.btn_stop_batch_t1 = ttk.Button(tree_toolbar, text="🛑 Parar Loop de Triagem", style="Secondary.TButton", command=self.stop_batch_gemini_triagem, state="disabled")
        self.btn_stop_batch_t1.pack(side="left", padx=2)
        
        # Treeview setup
        cols = ("ID", "Título", "Autores", "Ano", "Fonte", "Decisão")
        self.tree_triagem = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        
        self.tree_triagem.heading("ID", text="ID")
        self.tree_triagem.heading("Título", text="Título")
        self.tree_triagem.heading("Autores", text="Autores")
        self.tree_triagem.heading("Ano", text="Ano")
        self.tree_triagem.heading("Fonte", text="Fonte")
        self.tree_triagem.heading("Decisão", text="Decisão")
        
        self.tree_triagem.column("ID", width=40, anchor="center")
        self.tree_triagem.column("Título", width=300, anchor="w")
        self.tree_triagem.column("Autores", width=150, anchor="w")
        self.tree_triagem.column("Ano", width=50, anchor="center")
        self.tree_triagem.column("Fonte", width=80, anchor="center")
        self.tree_triagem.column("Decisão", width=80, anchor="center")
        
        # Tags for colored rows
        self.tree_triagem.tag_configure("Incluído", background="#e2f0d9")
        self.tree_triagem.tag_configure("Excluído", background="#fce4d6")
        self.tree_triagem.tag_configure("Pendente", background="#ffffff")
        
        # Treeview Scrollbars
        y_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree_triagem.yview)
        x_scroll = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree_triagem.xview)
        self.tree_triagem.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        
        self.tree_triagem.pack(fill="both", expand=True, side="left")
        y_scroll.pack(fill="y", side="right")
        x_scroll.pack(fill="x", side="bottom")
        
        self.tree_triagem.bind("<<TreeviewSelect>>", self.on_treeview_select)
        
        # Bottom Pane: Paper Details & Screening inputs
        self.detail_frame = ttk.LabelFrame(v_paned, text="Detalhes do Trabalho Selecionado", padding=10)
        v_paned.add(self.detail_frame, weight=1)
        
        # Details layout split: Left (Metadata & Abstract), Right (Screening form)
        self.detail_left = ttk.Frame(self.detail_frame)
        self.detail_left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        self.lbl_paper_title = ttk.Label(self.detail_left, text="Selecione um trabalho na tabela acima.", font=("Segoe UI", 11, "bold"), foreground=self.primary_color)
        self.lbl_paper_title.pack(anchor="w", fill="x", pady=(0, 5))
        # Dynamic wraplength: adjust to parent width
        def _update_title_wrap(event):
            self.lbl_paper_title.configure(wraplength=event.width - 20)
        self.detail_left.bind("<Configure>", _update_title_wrap)
        
        self.lbl_paper_meta = ttk.Label(self.detail_left, text="", font=("Segoe UI", 9, "italic"))
        self.lbl_paper_meta.pack(anchor="w", pady=(0, 5))
        
        self.lbl_paper_link = ttk.Label(self.detail_left, text="", font=("Segoe UI", 9, "underline"), cursor="hand2")
        self.lbl_paper_link.pack(anchor="w", pady=(0, 5))
        
        ttk.Label(self.detail_left, text="Resumo (Editável):", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(5, 2))
        
        self.txt_paper_abstract = tk.Text(self.detail_left, wrap="word", font=("Segoe UI", 9), height=8)
        self.txt_paper_abstract.pack(fill="both", expand=True)
        
        # Right details pane (Screening forms)
        self.detail_right = ttk.Frame(self.detail_frame)
        self.detail_right.pack(side="right", fill="both", expand=True)
        
        # Canvas scrollable for dynamic form
        form_canvas = tk.Canvas(self.detail_right, borderwidth=0, highlightthickness=0)
        form_scrollbar = ttk.Scrollbar(self.detail_right, orient="vertical", command=form_canvas.yview)
        form_scrollbar.pack(side="right", fill="y")
        form_canvas.pack(side="left", fill="both", expand=True)
        
        self.dynamic_form_frame = ttk.Frame(form_canvas, padding=5)
        self.dynamic_form_frame.bind(
            "<Configure>",
            lambda e: form_canvas.configure(scrollregion=form_canvas.bbox("all"))
        )
        form_canvas.create_window((0, 0), window=self.dynamic_form_frame, anchor="nw")
        form_canvas.configure(yscrollcommand=form_scrollbar.set)
        
        self.dynamic_form_inner_frame = ttk.Frame(self.dynamic_form_frame)
        self.dynamic_form_inner_frame.pack(fill="both", expand=True)
        
        # Enable mouse wheel scrolling when hovering over the canvas
        def _on_mousewheel(event):
            form_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            
        def _bind_to_mousewheel(event):
            form_canvas.bind_all("<MouseWheel>", _on_mousewheel)
            
        def _unbind_from_mousewheel(event):
            form_canvas.unbind_all("<MouseWheel>")
            
        form_canvas.bind('<Enter>', _bind_to_mousewheel)
        form_canvas.bind('<Leave>', _unbind_from_mousewheel)


    def setup_tab_triagem_2(self):
        """Builds the Data Extraction (Triagem 2) tab layout."""
        # Main split: Left for configuration/controls, Right for review area
        paned = ttk.Panedwindow(self.tab_triagem_2, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True)
        
        # Left Panel (Configuration)
        left_panel = ttk.Frame(paned, width=320)
        paned.add(left_panel, weight=0)
        
        # Make left panel scrollable
        canvas = tk.Canvas(left_panel, borderwidth=0, highlightthickness=0, bg=self.bg_color)
        scrollbar = ttk.Scrollbar(left_panel, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        
        self.triagem_2_scroll_frame = ttk.Frame(canvas, padding=10)
        self.triagem_2_scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.triagem_2_scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Bind mouse wheel to scroll left panel
        def _on_mousewheel_left(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        def _bind_left_mw(event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel_left)
            
        def _unbind_left_mw(event):
            canvas.unbind_all("<MouseWheel>")
            
        canvas.bind('<Enter>', _bind_left_mw)
        canvas.bind('<Leave>', _unbind_left_mw)
        
        # 1. Session Control Frame
        session_frame = ttk.LabelFrame(self.triagem_2_scroll_frame, text="Controle da Sessão", padding=10)
        session_frame.pack(fill="x", pady=5)
        
        self.lbl_t2_session_status = ttk.Label(session_frame, text="Nenhuma sessão ativa carregada.", font=("Segoe UI", 9, "bold"), foreground="#c00000")
        self.lbl_t2_session_status.pack(anchor="w", fill="x", pady=(0, 5))
        
        ttk.Button(session_frame, text="Sincronizar com Triagem 1", style="Secondary.TButton", command=self.sync_with_triagem_1).pack(fill="x", pady=2)
        ttk.Button(session_frame, text="Carregar Progresso (.json)", style="Secondary.TButton", command=self.load_triagem_session).pack(fill="x", pady=2)
        ttk.Button(session_frame, text="Salvar Progresso (.json)", style="Primary.TButton", command=self.save_triagem_session).pack(fill="x", pady=2)
        
        # 2. Extraction Fields Frame
        fields_frame = ttk.LabelFrame(self.triagem_2_scroll_frame, text="Campos de Extração de Dados", padding=10)
        fields_frame.pack(fill="x", pady=5)
        
        self.lst_ext_fields = tk.Listbox(fields_frame, height=5, font=("Segoe UI", 9))
        self.lst_ext_fields.pack(fill="x", pady=(0, 5))
        
        self.ent_new_ext_field = ttk.Entry(fields_frame)
        self.ent_new_ext_field.pack(fill="x", pady=(0, 5))
        self.ent_new_ext_field.bind("<Return>", lambda e: self.add_extraction_field())
        
        btn_fields_action = ttk.Frame(fields_frame)
        btn_fields_action.pack(fill="x")
        ttk.Button(btn_fields_action, text="+ Adicionar", style="Secondary.TButton", command=self.add_extraction_field).pack(side="left", padx=2)
        ttk.Button(btn_fields_action, text="- Remover", style="Secondary.TButton", command=self.remove_extraction_field).pack(side="left", padx=2)
        ttk.Button(fields_frame, text="Carregar Campos Padrão (PICO)", style="Secondary.TButton", command=self.load_default_extraction_fields).pack(fill="x", pady=(5, 2))
        
        self.btn_suggest_field_gemini = ttk.Button(fields_frame, text="✨ Sugerir Campo com IA (Gemini)", style="Secondary.TButton", command=self.suggest_extraction_field_with_gemini)
        self.btn_suggest_field_gemini.pack(fill="x", pady=2)
        
        # 3. PDF Settings Frame
        pdf_frame = ttk.LabelFrame(self.triagem_2_scroll_frame, text="Configuração dos PDFs", padding=10)
        pdf_frame.pack(fill="x", pady=5)
        
        ttk.Label(pdf_frame, text="Pasta de Downloads:", style="Bold.TLabel").pack(anchor="w", pady=(0, 2))
        ent_pdf_dir = ttk.Entry(pdf_frame, textvariable=self.pdf_download_dir)
        ent_pdf_dir.pack(fill="x", pady=(0, 5))
        
        ttk.Button(pdf_frame, text="Selecionar Pasta...", style="Secondary.TButton", command=self.select_pdf_download_dir).pack(fill="x", pady=(0, 5))
        
        self.btn_download_all_pdfs = ttk.Button(pdf_frame, text="Baixar todos os PDFs", style="Secondary.TButton", command=self.download_all_pdfs_bg)
        self.btn_download_all_pdfs.pack(fill="x", pady=2)
        
        self.btn_scan_pdfs = ttk.Button(pdf_frame, text="Escanear Pasta de PDFs", style="Secondary.TButton", command=self.scan_pdf_directory_t2)
        self.btn_scan_pdfs.pack(fill="x", pady=2)

        
        # 4. Export Frame
        export_frame = ttk.LabelFrame(self.triagem_2_scroll_frame, text="Exportação dos Dados", padding=10)
        export_frame.pack(fill="x", pady=5)
        
        ttk.Button(export_frame, text="Exportar Planilha de Extração (.xlsx)", style="Primary.TButton", command=self.export_extraction_excel).pack(fill="x", pady=2)
        
        # Right Panel (Work Area)
        right_panel = ttk.Frame(paned)
        paned.add(right_panel, weight=1)
        
        # Vertical split: Top for Treeview table, Bottom for paper details
        v_paned = ttk.Panedwindow(right_panel, orient=tk.VERTICAL)
        v_paned.pack(fill="both", expand=True)
        
        # Top Pane: Treeview list of papers (Included only)
        tree_frame = ttk.LabelFrame(v_paned, text="Trabalhos Incluídos (Fase 2)", padding=10)
        v_paned.add(tree_frame, weight=1)
        
        cols = ("ID", "Título", "Autores", "Ano", "Status PDF", "Extração")
        self.tree_triagem_2 = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        
        self.tree_triagem_2.heading("ID", text="ID")
        self.tree_triagem_2.heading("Título", text="Título")
        self.tree_triagem_2.heading("Autores", text="Autores")
        self.tree_triagem_2.heading("Ano", text="Ano")
        self.tree_triagem_2.heading("Status PDF", text="Status PDF")
        self.tree_triagem_2.heading("Extração", text="Extração")
        
        self.tree_triagem_2.column("ID", width=40, anchor="center")
        self.tree_triagem_2.column("Título", width=300, anchor="w")
        self.tree_triagem_2.column("Autores", width=150, anchor="w")
        self.tree_triagem_2.column("Ano", width=50, anchor="center")
        self.tree_triagem_2.column("Status PDF", width=100, anchor="center")
        self.tree_triagem_2.column("Extração", width=80, anchor="center")
        
        self.tree_triagem_2.tag_configure("Concluída", background="#e2f0d9")
        self.tree_triagem_2.tag_configure("Pendente", background="#ffffff")
        self.tree_triagem_2.tag_configure("Baixado", background="#e2f0d9")
        self.tree_triagem_2.tag_configure("Erro", background="#fce4d6")
        
        # Treeview Scrollbars
        y_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree_triagem_2.yview)
        x_scroll = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree_triagem_2.xview)
        self.tree_triagem_2.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        
        self.tree_triagem_2.pack(fill="both", expand=True, side="left")
        y_scroll.pack(fill="y", side="right")
        x_scroll.pack(fill="x", side="bottom")
        
        self.tree_triagem_2.bind("<<TreeviewSelect>>", self.on_treeview_select_t2)
        
        # Bottom Pane: PDF text viewer and dynamic extraction forms
        self.detail_frame_t2 = ttk.LabelFrame(v_paned, text="Trabalho Selecionado: Detalhes e Extração", padding=10)
        v_paned.add(self.detail_frame_t2, weight=2)
        
        # Bottom split: Left 50% for PDF Text, Right 50% for Extraction Form
        bottom_split = ttk.Panedwindow(self.detail_frame_t2, orient=tk.HORIZONTAL)
        bottom_split.pack(fill="both", expand=True)
        
        # PDF Text Frame (Left)
        pdf_text_frame = ttk.LabelFrame(bottom_split, text="Texto Extraído do PDF (Arraste e solte o PDF aqui)", padding=5)
        bottom_split.add(pdf_text_frame, weight=1)
        
        # Search inside PDF frame
        search_frame = ttk.Frame(pdf_text_frame)
        search_frame.pack(fill="x", pady=(0, 5))
        
        ttk.Label(search_frame, text="Buscar no PDF:", font=("Segoe UI", 9, "bold")).pack(side="left", padx=2)
        self.ent_search_pdf_t2 = ttk.Entry(search_frame, width=20)
        self.ent_search_pdf_t2.pack(side="left", padx=2)
        self.ent_search_pdf_t2.bind("<Return>", lambda e: self.search_text_in_pdf())
        
        ttk.Button(search_frame, text="Buscar", style="Secondary.TButton", command=self.search_text_in_pdf).pack(side="left", padx=2)
        
        self.btn_search_prev_t2 = ttk.Button(search_frame, text="←", width=3, style="Secondary.TButton", command=lambda: self.navigate_search_match(-1))
        self.btn_search_prev_t2.pack(side="left", padx=1)
        self.btn_search_next_t2 = ttk.Button(search_frame, text="→", width=3, style="Secondary.TButton", command=lambda: self.navigate_search_match(1))
        self.btn_search_next_t2.pack(side="left", padx=1)
        
        self.lbl_search_count_t2 = ttk.Label(search_frame, text="0/0", font=("Segoe UI", 9))
        self.lbl_search_count_t2.pack(side="left", padx=5)
        
        # Scrollable text widget for PDF text
        self.txt_pdf_text_t2 = scrolledtext.ScrolledText(pdf_text_frame, wrap="word", font=("Segoe UI", 9), bg="#ffffff")
        self.txt_pdf_text_t2.pack(fill="both", expand=True)
        self.txt_pdf_text_t2.tag_configure("match", background="yellow", foreground="black")
        self.txt_pdf_text_t2.tag_configure("current_match", background="orange", foreground="black")
        self.txt_pdf_text_t2.configure(state="disabled")
        
        # Enable Drag and Drop on PDF text box and panel
        enable_win_dnd(self.txt_pdf_text_t2, self.on_pdf_drop_t2)
        enable_win_dnd(pdf_text_frame, self.on_pdf_drop_t2)
        
        # PDF buttons frame
        pdf_buttons_frame = ttk.Frame(pdf_text_frame, padding=(0, 5, 0, 0))
        pdf_buttons_frame.pack(fill="x")
        
        self.btn_download_single_pdf = ttk.Button(pdf_buttons_frame, text="Baixar PDF", style="Secondary.TButton", command=self.download_current_pdf_t2)
        self.btn_download_single_pdf.pack(side="left", padx=2)
        
        self.btn_associate_local_pdf = ttk.Button(pdf_buttons_frame, text="Associar PDF Local", style="Secondary.TButton", command=self.associate_local_pdf_t2)
        self.btn_associate_local_pdf.pack(side="left", padx=2)
        
        self.btn_open_external_pdf = ttk.Button(pdf_buttons_frame, text="Abrir PDF no Leitor", style="Secondary.TButton", command=self.open_current_pdf_externally)
        self.btn_open_external_pdf.pack(side="left", padx=2)
        
        self.btn_open_pdf_link = ttk.Button(pdf_buttons_frame, text="Abrir Link do Artigo", style="Secondary.TButton", command=self.open_current_pdf_link)
        self.btn_open_pdf_link.pack(side="left", padx=2)
        
        self.btn_gemini_pdf_t2 = ttk.Button(pdf_buttons_frame, text="✨ Extrair Dados com IA", style="Secondary.TButton", command=self.run_gemini_extracao_partner)
        self.btn_gemini_pdf_t2.pack(side="left", padx=2)

        
        # Extraction Form Frame (Right)
        self.form_container_frame_t2 = ttk.LabelFrame(bottom_split, text="Campos de Extração", padding=5)
        bottom_split.add(self.form_container_frame_t2, weight=1)
        
        # Canvas scrollable for dynamic fields
        form_canvas_t2 = tk.Canvas(self.form_container_frame_t2, borderwidth=0, highlightthickness=0)
        form_scrollbar_t2 = ttk.Scrollbar(self.form_container_frame_t2, orient="vertical", command=form_canvas_t2.yview)
        form_scrollbar_t2.pack(side="right", fill="y")
        form_canvas_t2.pack(side="left", fill="both", expand=True)
        
        self.dynamic_form_frame_t2 = ttk.Frame(form_canvas_t2, padding=5)
        self.dynamic_form_frame_t2.bind(
            "<Configure>",
            lambda e: form_canvas_t2.configure(scrollregion=form_canvas_t2.bbox("all"))
        )
        form_canvas_t2.create_window((0, 0), window=self.dynamic_form_frame_t2, anchor="nw")
        form_canvas_t2.configure(yscrollcommand=form_scrollbar_t2.set)
        
        self.dynamic_form_inner_frame_t2 = ttk.Frame(self.dynamic_form_frame_t2)
        self.dynamic_form_inner_frame_t2.pack(fill="both", expand=True)
        
        # Enable mouse wheel scrolling when hovering over the canvas
        def _on_mousewheel_right_t2(event):
            form_canvas_t2.yview_scroll(int(-1 * (event.delta / 120)), "units")
            
        form_canvas_t2.bind('<Enter>', lambda e: form_canvas_t2.bind_all("<MouseWheel>", _on_mousewheel_right_t2))
        form_canvas_t2.bind('<Leave>', lambda e: form_canvas_t2.unbind_all("<MouseWheel>"))

    def sync_with_triagem_1(self):
        """Synchronizes the current memory session with Triagem 2."""
        self.save_current_paper_decisions()
        if not self.current_session.get('trabalhos'):
            messagebox.showwarning("Aviso", "Não há trabalhos na sessão ativa. Inicie ou carregue a Triagem 1 primeiro.")
            return
        
        self.populate_treeview_t2()
        self.scan_pdf_directory_t2(show_message=False)
        
        num_included = len(self.tree_triagem_2.get_children())
        num_done = sum(1 for t in self.current_session.get('trabalhos', []) if t.get('Decisao') == 'Incluído' and t.get('Extracao', {}).get('status_extracao') == 'Concluída')
        self.lbl_t2_session_status.configure(
            text=f"Sincronizado! Incluídos: {num_included} ({num_done} extraídos).",
            foreground="#1f497d"
        )


    def populate_treeview_t2(self):
        """Populates the Triagem 2 treeview with papers marked as 'Incluído'."""
        for item in self.tree_triagem_2.get_children():
            self.tree_triagem_2.delete(item)
            
        for t in self.current_session.get('trabalhos', []):
            if t.get('Decisao') == 'Incluído':
                ext = t.get('Extracao', {})
                if not isinstance(ext, dict):
                    ext = {}
                    t['Extracao'] = ext
                
                status_pdf = ext.get('status_pdf', 'Pendente')
                status_ext = ext.get('status_extracao', 'Pendente')
                
                self.tree_triagem_2.insert(
                    "", 
                    tk.END, 
                    iid="t2_" + t['id'],
                    values=(t['id'], t['Título'], t['Autores'], t['Ano'], status_pdf, status_ext),
                    tags=(status_ext, status_pdf)
                )

    def on_treeview_select_t2(self, event):
        """Fires when a paper row is selected in Triagem 2 treeview."""
        selected = self.tree_triagem_2.selection()
        if not selected:
            return
            
        # First save current paper extraction answers
        self.save_current_paper_extraction()
        
        t2_id = selected[0]
        paper_id = t2_id.replace("t2_", "")
        
        for idx, t in enumerate(self.current_session.get('trabalhos', [])):
            if t['id'] == paper_id:
                self.selected_paper_index_t2 = idx
                self.update_dynamic_form_t2(t)
                
                # Update PDF Text Area
                ext = t.get('Extracao', {})
                pdf_text = ext.get('texto_extraido', '')
                status_pdf = ext.get('status_pdf', 'Pendente')
                
                self.txt_pdf_text_t2.configure(state="normal")
                self.txt_pdf_text_t2.delete("1.0", tk.END)
                
                if pdf_text:
                    self.txt_pdf_text_t2.insert(tk.END, pdf_text)
                    self.status_var.set(f"Texto do PDF carregado para: {t['Título'][:40]}...")
                elif status_pdf == 'Baixado':
                    pdf_path = ext.get('caminho_pdf', '')
                    if pdf_path and os.path.exists(pdf_path):
                        self.status_var.set("Extraindo texto do PDF...")
                        # Run extraction in a separate thread so UI does not hang
                        threading.Thread(target=self.extract_and_display_pdf_text, args=(t, pdf_path), daemon=True).start()
                    else:
                        self.txt_pdf_text_t2.insert(tk.END, "PDF marcado como baixado, mas arquivo não encontrado localmente.\nPor favor, tente baixar novamente ou associe o PDF manualmente.")
                else:
                    self.txt_pdf_text_t2.insert(tk.END, "Nenhum PDF disponível para este trabalho.\nClique em 'Baixar PDF', 'Associar PDF Local' ou Arraste e Solte o arquivo PDF aqui nesta área.")
                
                self.txt_pdf_text_t2.configure(state="disabled")
                
                # Reset search fields
                self.ent_search_pdf_t2.delete(0, tk.END)
                self.lbl_search_count_t2.configure(text="0/0")
                self.search_matches_t2 = []
                self.current_search_idx_t2 = -1
                break

    def extract_and_display_pdf_text(self, paper, pdf_path):
        text = self.extract_text_from_pdf_file(pdf_path)
        paper['Extracao']['texto_extraido'] = text
        
        # Check if still selected
        if self.selected_paper_index_t2 is not None:
            curr_paper = self.current_session['trabalhos'][self.selected_paper_index_t2]
            if curr_paper['id'] == paper['id']:
                self.txt_pdf_text_t2.configure(state="normal")
                self.txt_pdf_text_t2.delete("1.0", tk.END)
                if text:
                    self.txt_pdf_text_t2.insert(tk.END, text)
                else:
                    self.txt_pdf_text_t2.insert(tk.END, "[AVISO] PDF lido, mas nenhum texto pôde ser extraído (PDF pode conter apenas imagens/escaneado).")
                self.txt_pdf_text_t2.configure(state="disabled")
        self.status_var.set("Extração de texto concluída.")

    def add_extraction_field(self):
        """Adds a field to the data extraction list."""
        field = self.ent_new_ext_field.get().strip()
        if field:
            if field not in self.campos_extracao:
                self.campos_extracao.append(field)
                self.lst_ext_fields.insert(tk.END, field)
                self.ent_new_ext_field.delete(0, tk.END)
                self.status_var.set(f"Campo de extração adicionado: '{field}'")
                
                # Refresh dynamic form if paper is selected
                if self.selected_paper_index_t2 is not None:
                    paper = self.current_session['trabalhos'][self.selected_paper_index_t2]
                    self.update_dynamic_form_t2(paper)
            else:
                messagebox.showwarning("Aviso", "Este campo já existe.")
        else:
            messagebox.showwarning("Aviso", "Digite um nome de campo válido.")

    def remove_extraction_field(self):
        """Removes the selected field from the extraction list."""
        try:
            index = self.lst_ext_fields.curselection()[0]
            field = self.campos_extracao.pop(index)
            self.lst_ext_fields.delete(index)
            self.status_var.set(f"Campo removido: '{field}'")
            
            # Refresh dynamic form if paper is selected
            if self.selected_paper_index_t2 is not None:
                paper = self.current_session['trabalhos'][self.selected_paper_index_t2]
                self.update_dynamic_form_t2(paper)
        except IndexError:
            messagebox.showwarning("Aviso", "Selecione um campo na lista para remover.")

    def load_default_extraction_fields(self):
        """Loads suggested standard extraction fields."""
        defaults = ["Objetivo do Estudo", "Método / Abordagem", "Participantes / Amostra", "Principais Resultados", "Conclusões / Limitações"]
        for f in defaults:
            if f not in self.campos_extracao:
                self.campos_extracao.append(f)
                self.lst_ext_fields.insert(tk.END, f)
        self.status_var.set("Campos de extração padrão adicionados.")
        
        # Refresh dynamic form if paper is selected
        if self.selected_paper_index_t2 is not None:
            paper = self.current_session['trabalhos'][self.selected_paper_index_t2]
            self.update_dynamic_form_t2(paper)

    def select_pdf_download_dir(self):
        """Opens a directory dialog to choose PDF folder."""
        dir_path = filedialog.askdirectory()
        if dir_path:
            # Normalize path
            dir_path = dir_path.replace("\\", "/")
            self.pdf_download_dir.set(dir_path)
            self.status_var.set(f"Pasta de download de PDFs: {os.path.basename(dir_path)}")

    def resolve_pdf_url(self, url):
        """Helper to resolve direct PDF download URL from landing page URLs."""
        if not url:
            return ""
        url_lower = url.lower()
        if url_lower.endswith(".pdf") or ".pdf?" in url_lower:
            return url
        if "scielo" in url_lower and "script=sci_arttext" in url_lower:
            return url.replace("script=sci_arttext", "script=sci_pdf")
        return url

    def download_current_pdf_t2(self):
        """Downloads the PDF for the selected paper in a background thread."""
        if self.selected_paper_index_t2 is None:
            messagebox.showwarning("Aviso", "Selecione um trabalho para baixar.")
            return
            
        paper = self.current_session['trabalhos'][self.selected_paper_index_t2]
        url = paper.get('Link para Download', '')
        if not url:
            messagebox.showwarning("Aviso", "Este trabalho não possui Link para Download cadastrado.")
            return
            
        download_dir = self.pdf_download_dir.get().strip()
        if not download_dir:
            messagebox.showerror("Erro", "Configure o diretório de downloads de PDFs.")
            return
            
        self.btn_download_single_pdf.configure(state="disabled")
        self.status_var.set(f"Baixando PDF de: {paper['Título'][:30]}...")
        
        threading.Thread(target=self.download_single_pdf_worker, args=(paper, download_dir), daemon=True).start()

    def download_single_pdf_worker(self, paper, download_dir):
        success = self.download_pdf_file(paper, download_dir)
        
        def update_gui():
            self.btn_download_single_pdf.configure(state="normal")
            if success:
                ext = paper.get('Extracao', {})
                self.tree_triagem_2.item("t2_" + paper['id'], values=(paper['id'], paper['Título'], paper['Autores'], paper['Ano'], ext.get('status_pdf'), ext.get('status_extracao')))
                if self.selected_paper_index_t2 is not None:
                    curr_paper = self.current_session['trabalhos'][self.selected_paper_index_t2]
                    if curr_paper['id'] == paper['id']:
                        self.on_treeview_select_t2(None)
                messagebox.showinfo("Sucesso", f"PDF baixado com sucesso!\nSalvo em: {ext.get('caminho_pdf')}")
            else:
                messagebox.showerror("Erro", f"Falha ao baixar PDF do artigo.\nLink: {paper.get('Link para Download')}\n\nVocê pode associar um arquivo local baixado manualmente.")
        
        self.after(0, update_gui)

    def download_pdf_file(self, paper, download_dir):
        """Downloads the PDF and updates the paper state. Returns True on success, False on failure."""
        url = paper.get('Link para Download', '')
        if not url:
            return False
            
        try:
            win_download_dir = fix_win_long_path(download_dir)
            os.makedirs(win_download_dir, exist_ok=True)
            
            clean_title = "".join(c for c in paper['Título'][:20] if c.isalnum() or c in (' ', '_', '-')).strip()
            clean_title = clean_title.replace(' ', '_')
            filename = f"ID_{paper['id']}_{clean_title}.pdf"
            pdf_path = os.path.join(download_dir, filename).replace("\\", "/")
            win_pdf_path = fix_win_long_path(pdf_path)
            
            resolved_url = self.resolve_pdf_url(url)
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            if 'Extracao' not in paper or not isinstance(paper['Extracao'], dict):
                paper['Extracao'] = {}
            ext = paper['Extracao']

                
            ext['status_pdf'] = "Baixando..."
            
            response = requests.get(resolved_url, headers=headers, timeout=20, allow_redirects=True)
            
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '')
                if 'text/html' in content_type and not response.content.startswith(b'%PDF'):
                    ext['status_pdf'] = "Erro"
                    return False
                    
                with open(win_pdf_path, 'wb') as f:
                    f.write(response.content)
                    
                ext['status_pdf'] = "Baixado"
                ext['caminho_pdf'] = pdf_path
                
                # Extract text right away
                text = self.extract_text_from_pdf_file(pdf_path)
                ext['texto_extraido'] = text
                return True
            else:
                ext['status_pdf'] = "Erro"
                return False
        except Exception:
            if 'Extracao' in paper:
                paper['Extracao']['status_pdf'] = "Erro"
            return False

    def download_all_pdfs_bg(self):
        """Launches a background thread to download all PDFs of included papers."""
        if not self.current_session.get('trabalhos'):
            messagebox.showwarning("Aviso", "Não há trabalhos na sessão.")
            return
            
        download_dir = self.pdf_download_dir.get().strip()
        if not download_dir:
            messagebox.showerror("Erro", "Configure o diretório de downloads de PDFs.")
            return
            
        self.btn_download_all_pdfs.configure(state="disabled")
        self.status_var.set("Iniciando download em lote de PDFs...")
        
        threading.Thread(target=self.download_all_pdfs_worker, args=(download_dir,), daemon=True).start()

    def download_all_pdfs_worker(self, download_dir):
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading

        included_papers = [t for t in self.current_session['trabalhos'] if t.get('Decisao') == 'Incluído']
        
        # Filter papers to download
        to_download = []
        already_done = 0
        for paper in included_papers:
            ext = paper.get('Extracao', {})
            if ext.get('status_pdf') == 'Baixado' and ext.get('caminho_pdf') and os.path.exists(ext.get('caminho_pdf')):
                already_done += 1
            else:
                to_download.append(paper)
                
        total = len(to_download)
        
        if total == 0:
            def finish_empty():
                self.btn_download_all_pdfs.configure(state="normal")
                self.status_var.set("Download em lote concluído.")
                messagebox.showinfo("Lote Concluído", f"Todos os PDFs já foram baixados!\nTotal: {already_done}")
            self.after(0, finish_empty)
            return

        downloaded = 0
        failed = 0
        completed = 0
        
        os.makedirs(download_dir, exist_ok=True)
        counter_lock = threading.Lock()
        
        def download_task(paper):
            nonlocal downloaded, failed, completed
            p_id = paper['id']
            ext = paper.get('Extracao', {})
            
            def set_downloading():
                try:
                    self.tree_triagem_2.item("t2_" + p_id, values=(p_id, paper['Título'], paper['Autores'], paper['Ano'], "Baixando...", ext.get('status_extracao', 'Pendente')))
                except Exception:
                    pass
            self.after(0, set_downloading)
            
            success = self.download_pdf_file(paper, download_dir)
            
            with counter_lock:
                completed += 1
                if success:
                    downloaded += 1
                else:
                    failed += 1
                current_completed = completed
            
            def update_status():
                try:
                    self.status_var.set(f"Baixando ({current_completed}/{total}): {paper['Título'][:30]}...")
                    ext_current = paper.get('Extracao', {})
                    self.tree_triagem_2.item("t2_" + p_id, values=(p_id, paper['Título'], paper['Autores'], paper['Ano'], ext_current.get('status_pdf'), ext_current.get('status_extracao')))
                    if self.selected_paper_index_t2 is not None:
                        curr_selected = self.current_session['trabalhos'][self.selected_paper_index_t2]
                        if curr_selected['id'] == paper['id']:
                            self.on_treeview_select_t2(None)
                except Exception:
                    pass
            self.after(0, update_status)
            
            return success

        # 8 parallel download threads
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(download_task, paper) for paper in to_download]
            for future in as_completed(futures):
                pass
                
        def finish():
            self.btn_download_all_pdfs.configure(state="normal")
            self.status_var.set("Download em lote concluído.")
            messagebox.showinfo("Lote Concluído", f"Download de PDFs finalizado!\n\nNovos baixados: {downloaded}\nFalhas/Ignorados: {failed}\nMantidos anteriormente: {already_done}")
        self.after(0, finish)

    def extract_text_from_pdf_file(self, pdf_path):
        """Extracts text page by page from PDF using pypdf."""
        if not pdf_path:
            return ""
        win_path = fix_win_long_path(pdf_path)
        if not os.path.exists(win_path):
            return ""
        try:
            reader = pypdf.PdfReader(win_path)
            pages_text = []
            for i, page in enumerate(reader.pages):
                txt = page.extract_text()
                if txt:
                    pages_text.append(f"--- PÁGINA {i+1} ---\n{txt}\n")
            return "\n".join(pages_text)
        except Exception as e:
            return f"[Erro ao ler PDF: {str(e)}]"

    def attach_pdf_to_paper_t2(self, paper, source_pdf_path):
        """Attaches a local PDF file to the specified paper, copies it to download_dir, extracts text, and updates UI."""
        if not source_pdf_path:
            messagebox.showerror("Erro", "O arquivo PDF especificado não existe.")
            return False
            
        win_source = fix_win_long_path(source_pdf_path)
        if not os.path.exists(win_source):
            messagebox.showerror("Erro", f"O arquivo PDF especificado não foi encontrado:\n{source_pdf_path}")
            return False
            
        if not source_pdf_path.lower().endswith(".pdf"):
            messagebox.showerror("Erro", "O arquivo selecionado/arrastado não é um arquivo PDF (.pdf).")
            return False

        download_dir = self.pdf_download_dir.get().strip()
        if not download_dir:
            download_dir = "./pdfs"
            self.pdf_download_dir.set(download_dir)
            
        try:
            win_download_dir = fix_win_long_path(download_dir)
            os.makedirs(win_download_dir, exist_ok=True)
            
            clean_title = "".join(c for c in paper['Título'][:20] if c.isalnum() or c in (' ', '_', '-')).strip()
            clean_title = clean_title.replace(' ', '_')
            dest_filename = f"ID_{paper['id']}_{clean_title}.pdf"
            dest_path = os.path.join(download_dir, dest_filename).replace("\\", "/")
            win_dest_path = fix_win_long_path(dest_path)
            
            # Copy file if not already at destination path
            if os.path.abspath(source_pdf_path) != os.path.abspath(dest_path):
                import shutil
                shutil.copy(win_source, win_dest_path)
            
            if 'Extracao' not in paper or not isinstance(paper['Extracao'], dict):
                paper['Extracao'] = {}
            ext = paper['Extracao']
            
            ext['status_pdf'] = "Baixado"
            ext['caminho_pdf'] = dest_path
            
            self.status_var.set("Extraindo texto do PDF associado...")
            text = self.extract_text_from_pdf_file(dest_path)
            ext['texto_extraido'] = text
            
            self.tree_triagem_2.item("t2_" + paper['id'], values=(paper['id'], paper['Título'], paper['Autores'], paper['Ano'], "Baixado", ext.get('status_extracao', 'Pendente')))
            self.on_treeview_select_t2(None)
            
            messagebox.showinfo("Sucesso", f"PDF associado e vinculado com sucesso!\nSalvo em: {dest_path}")
            return True
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível associar o PDF local:\n{str(e)}")
            return False

    def associate_local_pdf_t2(self):
        """Allows user to manually select a local PDF file for the selected paper."""
        if self.selected_paper_index_t2 is None:
            messagebox.showwarning("Aviso", "Selecione um trabalho para associar o PDF.")
            return
            
        paper = self.current_session['trabalhos'][self.selected_paper_index_t2]
        
        filename = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if not filename:
            return
            
        self.attach_pdf_to_paper_t2(paper, filename)

    def on_pdf_drop_t2(self, files):
        """Fires when files are dragged and dropped onto the PDF text area in Triagem 2."""
        if not files:
            return
            
        if self.selected_paper_index_t2 is None:
            messagebox.showwarning("Aviso", "Selecione um trabalho na tabela de Triagem 2 antes de arrastar e soltar o PDF.")
            return
            
        paper = self.current_session['trabalhos'][self.selected_paper_index_t2]
        
        # Safely convert/decode dropped file paths
        decoded_files = []
        for f in files:
            if isinstance(f, bytes):
                try:
                    f = f.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        f = f.decode('ansi')
                    except UnicodeDecodeError:
                        f = f.decode('mbcs', errors='ignore')
            if isinstance(f, str):
                decoded_files.append(f.strip())
        
        # Filter for .pdf files dropped
        pdf_files = [f for f in decoded_files if f.lower().endswith('.pdf')]
        if not pdf_files:
            messagebox.showwarning("Aviso", "Nenhum arquivo .pdf válido foi encontrado nos arquivos arrastados.")
            return
            
        # Attach the first PDF file
        dropped_pdf = pdf_files[0]
        self.attach_pdf_to_paper_t2(paper, dropped_pdf)

    def open_current_pdf_externally(self):
        """Opens the downloaded PDF in the system's default PDF reader."""
        if self.selected_paper_index_t2 is None:
            return
            
        paper = self.current_session['trabalhos'][self.selected_paper_index_t2]
        ext = paper.get('Extracao', {})
        pdf_path = ext.get('caminho_pdf', '')
        
        if pdf_path and os.path.exists(pdf_path):
            try:
                open_file_with_default_app(pdf_path)
                self.status_var.set(f"Abrindo PDF: {os.path.basename(pdf_path)}")
            except Exception as e:
                messagebox.showerror("Erro", f"Não foi possível abrir o PDF:\n{str(e)}")
        else:
            messagebox.showwarning("Aviso", "O PDF deste artigo ainda não foi baixado ou o arquivo local não existe.")

    def open_current_pdf_link(self):
        """Opens the download link of the current paper in the web browser."""
        if self.selected_paper_index_t2 is None:
            messagebox.showwarning("Aviso", "Selecione um trabalho para abrir o link.")
            return
            
        paper = self.current_session['trabalhos'][self.selected_paper_index_t2]
        url = paper.get('Link para Download', '')
        if url:
            try:
                webbrowser.open_new_tab(url)
                self.status_var.set(f"Abrindo link no navegador: {url[:50]}...")
            except Exception as e:
                messagebox.showerror("Erro", f"Não foi possível abrir o link:\n{str(e)}")
        else:
            messagebox.showwarning("Aviso", "Este trabalho não possui link cadastrado.")

    def scan_pdf_directory_t2(self, show_message=True):
        """Scans the PDF download directory to track which papers already have their PDFs locally."""
        if not self.current_session.get('trabalhos'):
            if show_message:
                messagebox.showwarning("Aviso", "Não há nenhuma sessão de triagem ativa.")
            return
            
        download_dir = self.pdf_download_dir.get().strip()
        if not download_dir or not os.path.exists(download_dir):
            if show_message:
                messagebox.showerror("Erro", f"Pasta de downloads não encontrada: '{download_dir}'")
            return
            
        try:
            files = os.listdir(download_dir)
        except Exception:
            return
            
        pattern = re.compile(r"^ID_(\d+)(?:_.*)?\.pdf$", re.IGNORECASE)
        
        local_pdfs = {}
        for f in files:
            m = pattern.match(f)
            if m:
                p_id = m.group(1)
                full_path = os.path.join(download_dir, f).replace("\\", "/")
                local_pdfs[p_id] = full_path
                
        updated_count = 0
        newly_found = []
        
        for paper in self.current_session['trabalhos']:
            if paper.get('Decisao') == 'Incluído':
                p_id = paper['id']
                if 'Extracao' not in paper or not isinstance(paper['Extracao'], dict):
                    paper['Extracao'] = {}
                ext = paper['Extracao']
                    
                prev_status = ext.get('status_pdf', 'Pendente')
                
                if p_id in local_pdfs:
                    path = local_pdfs[p_id]
                    if prev_status != 'Baixado' or ext.get('caminho_pdf') != path:
                        ext['status_pdf'] = 'Baixado'
                        ext['caminho_pdf'] = path
                        updated_count += 1
                        
                    if not ext.get('texto_extraido'):
                        newly_found.append((paper, path))
                else:
                    if prev_status == 'Baixado':
                        ext['status_pdf'] = 'Pendente'
                        ext['caminho_pdf'] = ''
                        # Mantém o texto extraído para não perder o progresso
                        # ext['texto_extraido'] = ''
                        updated_count += 1
                        
        self.populate_treeview_t2()
        
        if self.selected_paper_index_t2 is not None:
            self.on_treeview_select_t2(None)
            
        if updated_count > 0:
            self.after(0, self._save_unified_json_quietly)
            
        if newly_found:
            def extract_batch():
                self.status_var.set(f"Extraindo texto de {len(newly_found)} novos PDFs encontrados...")
                for p, path in newly_found:
                    text = self.extract_text_from_pdf_file(path)
                    p['Extracao']['texto_extraido'] = text
                    if self.selected_paper_index_t2 is not None:
                        curr_paper = self.current_session['trabalhos'][self.selected_paper_index_t2]
                        if curr_paper['id'] == p['id']:
                            def load_text(t=text):
                                self.txt_pdf_text_t2.configure(state="normal")
                                self.txt_pdf_text_t2.delete("1.0", tk.END)
                                self.txt_pdf_text_t2.insert(tk.END, t)
                                self.txt_pdf_text_t2.configure(state="disabled")
                            self.after(0, load_text)
                self.status_var.set("Extração de texto da varredura concluída.")
                self.after(0, self._save_unified_json_quietly)
            threading.Thread(target=extract_batch, daemon=True).start()
            
        if show_message:
            messagebox.showinfo(
                "Varredura Concluída",
                f"Escaneamento de PDFs finalizado!\n\n"
                f"Total de PDFs locais correspondentes: {len(local_pdfs)}\n"
                f"Status de trabalhos atualizados: {updated_count}\n"
                f"Novos arquivos com extração de texto iniciada: {len(newly_found)}"
            )
        else:
            self.status_var.set(f"Varredura automática: {len(local_pdfs)} PDFs locais associados.")


    def update_dynamic_form_t2(self, paper):
        """Updates the dynamic extraction fields in the right panel."""
        for child in self.dynamic_form_inner_frame_t2.winfo_children():
            child.destroy()
            
        if 'Extracao' not in paper or not isinstance(paper['Extracao'], dict):
            paper['Extracao'] = {}
        ext = paper['Extracao']

            
        respostas = ext.get('respostas', {})
        if not isinstance(respostas, dict):
            respostas = {}
            ext['respostas'] = respostas
            
        self.dynamic_vars_t2 = {
            'respostas': {},
            'status_extracao': tk.StringVar(value=ext.get('status_extracao', 'Pendente'))
        }
        
        row_idx = 0
        
        if not self.campos_extracao:
            ttk.Label(self.dynamic_form_inner_frame_t2, text="Nenhum campo de extração definido.\nAdicione campos no painel lateral esquerdo.", font=("Segoe UI", 9, "italic")).grid(row=row_idx, column=0, sticky="w", pady=10)
            return
            
        for field in self.campos_extracao:
            ttk.Label(self.dynamic_form_inner_frame_t2, text=field, font=("Segoe UI", 9, "bold"), foreground=self.primary_color).grid(row=row_idx, column=0, sticky="w", pady=(5, 2))
            row_idx += 1
            
            txt_reply = scrolledtext.ScrolledText(self.dynamic_form_inner_frame_t2, wrap="word", font=("Segoe UI", 9), height=3, width=35)
            txt_reply.grid(row=row_idx, column=0, sticky="ew", padx=10, pady=(0, 5))
            
            val = respostas.get(field, "")
            txt_reply.insert(tk.END, val)
            
            self.dynamic_vars_t2['respostas'][field] = txt_reply
            row_idx += 1
            
        # Observações em Triagem 2
        ttk.Separator(self.dynamic_form_inner_frame_t2, orient="horizontal").grid(row=row_idx, column=0, sticky="ew", pady=10)
        row_idx += 1

        ttk.Label(self.dynamic_form_inner_frame_t2, text="Observações / Limitações Metodológicas:", font=("Segoe UI", 9, "bold"), foreground=self.primary_color).grid(row=row_idx, column=0, sticky="w", pady=2)
        row_idx += 1

        self.txt_observacoes_t2 = scrolledtext.ScrolledText(self.dynamic_form_inner_frame_t2, wrap="word", font=("Segoe UI", 9), height=4, width=35)
        self.txt_observacoes_t2.grid(row=row_idx, column=0, sticky="ew", padx=10, pady=(0, 5))
        val_obs = ext.get('observacoes', paper.get('Observacoes', ''))
        self.txt_observacoes_t2.insert(tk.END, val_obs)
        self.txt_observacoes_t2.bind("<FocusOut>", lambda e: self.save_current_paper_extraction())
        self.txt_observacoes_t2.bind("<KeyRelease>", lambda e: self.save_current_paper_extraction())
        row_idx += 1

        ttk.Label(self.dynamic_form_inner_frame_t2, text="Status da Extração:", font=("Segoe UI", 9, "bold")).grid(row=row_idx, column=0, sticky="w", pady=2)
        row_idx += 1

        cb_status = ttk.Combobox(self.dynamic_form_inner_frame_t2, textvariable=self.dynamic_vars_t2['status_extracao'], values=["Pendente", "Concluída"], state="readonly", width=15)
        cb_status.grid(row=row_idx, column=0, sticky="w", pady=2)
        row_idx += 1

        btn_action_frame_t2 = ttk.Frame(self.dynamic_form_inner_frame_t2)
        btn_action_frame_t2.grid(row=row_idx, column=0, sticky="ew", pady=(15, 5))
        btn_action_frame_t2.columnconfigure(0, weight=1)
        btn_action_frame_t2.columnconfigure(1, weight=1)

        self.btn_gemini_t2 = ttk.Button(btn_action_frame_t2, text="✨ Parceiro de Extração (Gemini)", style="Secondary.TButton", command=self.run_gemini_extracao_partner)
        self.btn_gemini_t2.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        btn_save = ttk.Button(btn_action_frame_t2, text="Salvar Extração e Próximo", style="Primary.TButton", command=self.save_extraction_and_next_t2)
        btn_save.grid(row=0, column=1, sticky="ew")
        row_idx += 1

    def save_current_paper_extraction(self):
        """Saves current dynamic extraction answers into the active paper state."""
        if self.selected_paper_index_t2 is None:
            return

        paper = self.current_session['trabalhos'][self.selected_paper_index_t2]
        if 'Extracao' not in paper or not isinstance(paper['Extracao'], dict):
            paper['Extracao'] = {}
        ext = paper['Extracao']

        respostas = ext.get('respostas', {})
        if not isinstance(respostas, dict):
            respostas = {}
            ext['respostas'] = respostas

        for field, txt_widget in self.dynamic_vars_t2.get('respostas', {}).items():
            respostas[field] = txt_widget.get("1.0", tk.END).strip()

        if hasattr(self, 'txt_observacoes_t2') and self.txt_observacoes_t2.winfo_exists():
            obs = self.txt_observacoes_t2.get("1.0", tk.END).strip()
            ext['observacoes'] = obs
            paper['Observacoes'] = obs
            
        status_ext = self.dynamic_vars_t2.get('status_extracao').get()
        ext['status_extracao'] = status_ext
        
        self.tree_triagem_2.item("t2_" + paper['id'], values=(paper['id'], paper['Título'], paper['Autores'], paper['Ano'], ext.get('status_pdf', 'Pendente'), status_ext), tags=(status_ext, ext.get('status_pdf', 'Pendente')))
        
        children_t2 = self.tree_triagem_2.get_children()
        num_included = len(children_t2)
        num_done = sum(1 for t in self.current_session.get('trabalhos', []) if t.get('Decisao') == 'Incluído' and t.get('Extracao', {}).get('status_extracao') == 'Concluída')
        self.lbl_t2_session_status.configure(
            text=f"Sessão ativa: {len(self.current_session.get('trabalhos', []))} trabalhos.\nIncluídos: {num_included} ({num_done} extraídos).",
            foreground="#1f497d"
        )

    def save_extraction_and_next_t2(self):
        """Saves decisions for current paper and moves selection to next paper in Triagem 2."""
        self.save_current_paper_extraction()
        
        current_selection = self.tree_triagem_2.selection()
        if not current_selection:
            return
            
        current_id = current_selection[0]
        children = self.tree_triagem_2.get_children()
        try:
            current_index = children.index(current_id)
            if current_index + 1 < len(children):
                next_id = children[current_index + 1]
                self.tree_triagem_2.selection_set(next_id)
                self.tree_triagem_2.see(next_id)
            else:
                self.status_var.set("Fim da lista de extração alcançado.")
                messagebox.showinfo("Fim da Lista", "Você preencheu a extração do último trabalho incluído.")
        except ValueError:
            pass

    def export_extraction_excel(self):
        """Consolidates extraction answers and exports them to an Excel file."""
        if not self.current_session.get('trabalhos'):
            messagebox.showwarning("Aviso", "Não há dados de sessão para exportar.")
            return
            
        self.save_current_paper_extraction()
        
        included_papers = [t for t in self.current_session['trabalhos'] if t.get('Decisao') == 'Incluído']
        if not included_papers:
            messagebox.showwarning("Aviso", "Não há trabalhos marcados como 'Incluído' nesta sessão.")
            return
            
        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx"), ("CSV files", "*.csv")],
            initialfile="4_matriz_extracao.xlsx"
        )
        
        if not file_path:
            return
            
        rows = []
        for paper in included_papers:
            ext = paper.get('Extracao', {})
            respostas = ext.get('respostas', {})
            
            row = {
                "ID": paper['id'],
                "Título": paper['Título'],
                "Autores": paper['Autores'],
                "Ano": paper['Ano'],
                "Fonte": paper['Fonte'],
                "Tipo de Pesquisa": paper.get('Tipo de Pesquisa', ''),
                "Universidade / Revista": paper.get('Universidade / Editora / Revista', ''),
                "Link de Acesso": paper.get('Link para Download', ''),
                "Status PDF": ext.get('status_pdf', 'Pendente'),
                "Status Extração": ext.get('status_extracao', 'Pendente'),
                "Observações": ext.get('observacoes', paper.get('Observacoes', ''))
            }
            
            for field in self.campos_extracao:
                row[field] = respostas.get(field, "")
                
            rows.append(row)
            
        df = pd.DataFrame(rows)
        
        try:
            if file_path.endswith('.csv'):
                df.to_csv(file_path, index=False, encoding='utf-8-sig')
            else:
                df.to_excel(file_path, index=False)
                
            self.status_var.set(f"Matriz de extração exportada com sucesso: {os.path.basename(file_path)}")
            messagebox.showinfo("Sucesso", f"Matriz de extração exportada com sucesso!\n\nArquivo: {file_path}")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao exportar dados:\n{str(e)}")

    def search_text_in_pdf(self):
        """Searches for a text pattern in the PDF text widget and highlights occurrences."""
        self.txt_pdf_text_t2.tag_remove("match", "1.0", tk.END)
        self.txt_pdf_text_t2.tag_remove("current_match", "1.0", tk.END)
        self.search_matches_t2 = []
        self.current_search_idx_t2 = -1
        self.lbl_search_count_t2.configure(text="0/0")
        
        query = self.ent_search_pdf_t2.get().strip()
        if not query:
            return
            
        start = "1.0"
        while True:
            pos = self.txt_pdf_text_t2.search(query, start, stopindex=tk.END, nocase=True)
            if not pos:
                break
            self.search_matches_t2.append(pos)
            self.txt_pdf_text_t2.tag_add("match", pos, f"{pos} + {len(query)}c")
            start = f"{pos} + 1c"
            
        total = len(self.search_matches_t2)
        if total > 0:
            self.current_search_idx_t2 = 0
            self.lbl_search_count_t2.configure(text=f"1/{total}")
            self.highlight_current_search_match()
        else:
            self.lbl_search_count_t2.configure(text="0/0")
            self.status_var.set("Nenhuma ocorrência encontrada no texto.")
            
    def highlight_current_search_match(self):
        """Highlights the active search match and scrolls it into view."""
        self.txt_pdf_text_t2.tag_remove("current_match", "1.0", tk.END)
        if 0 <= self.current_search_idx_t2 < len(self.search_matches_t2):
            pos = self.search_matches_t2[self.current_search_idx_t2]
            query_len = len(self.ent_search_pdf_t2.get())
            end_pos = f"{pos} + {query_len}c"
            
            self.txt_pdf_text_t2.tag_add("current_match", pos, end_pos)
            self.txt_pdf_text_t2.see(pos)
            
            total = len(self.search_matches_t2)
            self.lbl_search_count_t2.configure(text=f"{self.current_search_idx_t2 + 1}/{total}")
            
    def navigate_search_match(self, direction):
        """Navigates through search results: direction can be 1 (next) or -1 (prev)."""
        total = len(self.search_matches_t2)
        if total == 0:
            return
            
        self.current_search_idx_t2 = (self.current_search_idx_t2 + direction) % total
        self.highlight_current_search_match()

    def add_triagem_csv(self):
        """Browse and add a CSV or Excel file to the triagem file list."""
        filename = filedialog.askopenfilename(
            filetypes=[
                ("Resultados de Coleta", "*.csv;*.xlsx;*.xls"),
                ("CSV files", "*.csv"),
                ("Excel files", "*.xlsx;*.xls")
            ]
        )
        if filename:
            try:
                relpath = os.path.relpath(filename)
                if not relpath.startswith(".."):
                    filename = relpath
            except ValueError:
                pass
            if filename not in self.triagem_csv_files:
                self.triagem_csv_files.append(filename)
                self.lst_triagem_files.insert(tk.END, os.path.basename(filename))
                self.status_var.set(f"Arquivo de triagem adicionado: {os.path.basename(filename)}")
            else:
                messagebox.showwarning("Aviso", "Este arquivo já foi adicionado.")

    def remove_triagem_csv(self):
        """Remove selected CSV file from the list."""
        try:
            index = self.lst_triagem_files.curselection()[0]
            removed = self.triagem_csv_files.pop(index)
            self.lst_triagem_files.delete(index)
            self.status_var.set(f"Arquivo removido: {os.path.basename(removed)}")
        except IndexError:
            messagebox.showwarning("Aviso", "Selecione um arquivo na lista para remover.")

    def add_inclusion_criterion(self):
        """Add inclusion criterion to list."""
        crit = self.ent_new_inc.get().strip()
        if crit:
            if crit not in self.inclusion_criteria:
                self.inclusion_criteria.append(crit)
                self.lst_inc_criteria.insert(tk.END, crit)
                self.ent_new_inc.delete(0, tk.END)
                self.status_var.set(f"Critério de inclusão adicionado: '{crit}'")
            else:
                messagebox.showwarning("Aviso", "Este critério já existe.")
        else:
            messagebox.showwarning("Aviso", "Digite um critério válido.")

    def remove_inclusion_criterion(self):
        """Remove selected inclusion criterion."""
        try:
            index = self.lst_inc_criteria.curselection()[0]
            removed = self.inclusion_criteria.pop(index)
            self.lst_inc_criteria.delete(index)
            self.status_var.set(f"Critério removido: '{removed}'")
        except IndexError:
            messagebox.showwarning("Aviso", "Selecione um critério na lista para remover.")

    def add_exclusion_criterion(self):
        """Add exclusion criterion to list."""
        crit = self.ent_new_exc.get().strip()
        if crit:
            if crit not in self.exclusion_criteria:
                self.exclusion_criteria.append(crit)
                self.lst_exc_criteria.insert(tk.END, crit)
                self.ent_new_exc.delete(0, tk.END)
                self.status_var.set(f"Critério de exclusão adicionado: '{crit}'")
            else:
                messagebox.showwarning("Aviso", "Este critério já existe.")
        else:
            messagebox.showwarning("Aviso", "Digite um critério válido.")

    def remove_exclusion_criterion(self):
        """Remove selected exclusion criterion."""
        try:
            index = self.lst_exc_criteria.curselection()[0]
            removed = self.exclusion_criteria.pop(index)
            self.lst_exc_criteria.delete(index)
            self.status_var.set(f"Critério removido: '{removed}'")
        except IndexError:
            messagebox.showwarning("Aviso", "Selecione um critério na lista para remover.")

    def add_triagem_question(self):
        """Add a custom question to the list."""
        q = self.ent_new_q.get().strip()
        if q:
            if q not in self.triagem_questions:
                self.triagem_questions.append(q)
                self.lst_triagem_questions.insert(tk.END, q)
                self.ent_new_q.delete(0, tk.END)
                self.status_var.set(f"Pergunta adicionada: '{q}'")
            else:
                messagebox.showwarning("Aviso", "Esta pergunta já existe.")
        else:
            messagebox.showwarning("Aviso", "Digite uma pergunta válida.")

    def remove_triagem_question(self):
        """Remove selected question."""
        try:
            index = self.lst_triagem_questions.curselection()[0]
            removed = self.triagem_questions.pop(index)
            self.lst_triagem_questions.delete(index)
            self.status_var.set(f"Pergunta removida: '{removed}'")
        except IndexError:
            messagebox.showwarning("Aviso", "Selecione uma pergunta na lista para remover.")

    def normalize_title(self, title):
        if not title:
            return ""
        t = str(title).lower()
        t = "".join(
            c for c in unicodedata.normalize('NFKD', t)
            if not unicodedata.combining(c)
        )
        t = re.sub(r'[^a-z0-9\s]', '', t)
        t = re.sub(r'\s+', ' ', t).strip()
        return t

    def start_triagem(self):
        """Loads and deduplicates the selected CSV files to initialize screening."""
        if not self.triagem_csv_files:
            messagebox.showerror("Erro", "Selecione pelo menos um arquivo CSV para a triagem.")
            return

        # Build lookup map from existing session to preserve previous screening decisions
        existing_lookup = {}
        if self.current_session and 'trabalhos' in self.current_session:
            for t in self.current_session['trabalhos']:
                norm = self.normalize_title(t.get('Título', ''))
                existing_lookup[norm] = {
                    'Criterios': t.get('Criterios', {}),
                    'Perguntas': t.get('Perguntas', {}),
                    'Decisao': t.get('Decisao', 'Pendente')
                }

        all_dfs = []
        for f in self.triagem_csv_files:
            if not os.path.exists(f):
                messagebox.showwarning("Aviso", f"Arquivo não encontrado: {f}")
                continue
            try:
                if f.lower().endswith(('.xlsx', '.xls')):
                    df = pd.read_excel(f)
                else:
                    try:
                        df = pd.read_csv(f, encoding='utf-8')
                    except UnicodeDecodeError:
                        try:
                            df = pd.read_csv(f, encoding='utf-8-sig')
                        except UnicodeDecodeError:
                            df = pd.read_csv(f, encoding='latin-1')
                
                # Determine source
                filename = os.path.basename(f).lower()
                if 'scielo' in filename:
                    source = 'SciELO'
                elif 'openalex' in filename:
                    source = 'OpenAlex'
                elif 'pubmed' in filename:
                    source = 'PubMed'
                elif 'scopus' in filename:
                    source = 'Scopus'
                elif 'bdtd' in filename or 'resultados' in filename:
                    source = 'BDTD'
                else:
                    source = os.path.splitext(os.path.basename(f))[0].upper()
                
                df['__source__'] = source
                all_dfs.append(df)
            except Exception as e:
                messagebox.showerror("Erro", f"Não foi possível ler o arquivo {os.path.basename(f)}:\n{str(e)}")
                return

        if not all_dfs:
            return

        combined_df = pd.concat(all_dfs, ignore_index=True)
        
        expected_cols = [
            "Autores", "Título", "Ano", "Tipo de Pesquisa", 
            "Nome do Orientador", "Universidade / Editora / Revista", 
            "Resumo", "Link para Download"
        ]
        for col in expected_cols:
            if col not in combined_df.columns:
                combined_df[col] = ""
            else:
                combined_df[col] = combined_df[col].fillna("")

        combined_df['__normalized_title__'] = combined_df['Título'].apply(self.normalize_title)
        
        deduped_trabalhos = []
        duplicatas_encontradas = []
        grouped = combined_df.groupby('__normalized_title__')
        
        idx = 1
        for norm_title, group in grouped:
            if not norm_title:
                continue
            best_row_idx = group['Resumo'].str.len().idxmax()
            best_row = group.loc[best_row_idx].copy()
            
            sources = sorted(list(group['__source__'].unique()))
            source_str = " | ".join(sources)
            
            title = str(best_row['Título'])
            authors = str(best_row['Autores'])
            year = str(best_row['Ano'])
            # Clean decimal years from float conversions
            if year.endswith('.0'):
                year = year[:-2]
            
            # Check for duplicates
            if len(group) > 1:
                all_sources = group['__source__'].tolist()
                duplicatas_encontradas.append({
                    'titulo': title,
                    'autores': authors,
                    'ano': year,
                    'fontes': all_sources
                })
            
            # Check if this paper was already screened previously
            prev = existing_lookup.get(norm_title, {})
            prev_criterios = prev.get('Criterios', {})
            prev_perguntas = prev.get('Perguntas', {})
            prev_decisao = prev.get('Decisao', 'Pendente')

            # Initialize criteria
            criterios = {}
            for c in self.inclusion_criteria + self.exclusion_criteria:
                criterios[c] = prev_criterios.get(c, False)
                
            # Initialize questions
            perguntas = {}
            for q in self.triagem_questions:
                perguntas[q] = prev_perguntas.get(q, "")

            rec = {
                'id': str(idx),
                'Autores': authors,
                'Título': title,
                'Ano': year,
                'Tipo de Pesquisa': str(best_row['Tipo de Pesquisa']),
                'Nome do Orientador': str(best_row['Nome do Orientador']),
                'Universidade / Editora / Revista': str(best_row['Universidade / Editora / Revista']),
                'Resumo': str(best_row['Resumo']),
                'Link para Download': str(best_row['Link para Download']),
                'Fonte': source_str,
                'Criterios': criterios,
                'Perguntas': perguntas,
                'Decisao': prev_decisao
            }
            deduped_trabalhos.append(rec)
            idx += 1

        deduped_trabalhos.sort(key=lambda x: x.get('Ano', ''), reverse=True)
        
        # Re-index
        for i, t in enumerate(deduped_trabalhos, start=1):
            t['id'] = str(i)

        self.current_session = {
            'arquivos_origem': self.triagem_csv_files.copy(),
            'criterios_inclusao': self.inclusion_criteria.copy(),
            'criterios_exclusao': self.exclusion_criteria.copy(),
            'perguntas': self.triagem_questions.copy(),
            'trabalhos': deduped_trabalhos
        }

        self.populate_treeview()
        self.status_var.set(f"Triagem iniciada: {len(deduped_trabalhos)} trabalhos únicos.")
        
        # Generate the Report Text
        report_lines = []
        report_lines.append("==================================================")
        report_lines.append("             RELATÓRIO DE DEDUPLICAÇÃO            ")
        report_lines.append("==================================================")
        report_lines.append(f"Gerado em: {pd.Timestamp.now().strftime('%d/%m/%Y às %H:%M:%S')}\n")
        
        report_lines.append("--- ARQUIVOS FONTES PROCESSADOS ---")
        for f in self.triagem_csv_files:
            report_lines.append(f" - {os.path.basename(f)} ({f})")
        report_lines.append("")
        
        report_lines.append("--- ESTATÍSTICAS ---")
        report_lines.append(f"Total de registros lidos inicialmente: {len(combined_df)}")
        source_counts = combined_df['__source__'].value_counts()
        for src, count in source_counts.items():
            report_lines.append(f"  * Fonte '{src}': {count} registros")
        report_lines.append(f"Trabalhos únicos após deduplicação: {len(deduped_trabalhos)}")
        report_lines.append(f"Registros duplicados excluídos: {len(combined_df) - len(deduped_trabalhos)}")
        report_lines.append("")
        
        report_lines.append("--- TRABALHOS DUPLICADOS ENCONTRADOS ---")
        if duplicatas_encontradas:
            for j, dup in enumerate(duplicatas_encontradas, start=1):
                report_lines.append(f"{j}. Título: {dup['titulo']}")
                report_lines.append(f"   Autores: {dup['autores']} ({dup['ano']})")
                report_lines.append(f"   Ocorrências em fontes: {', '.join(dup['fontes'])}")
                report_lines.append("")
        else:
            report_lines.append("Nenhum trabalho duplicado foi identificado (títulos 100% distintos).")
            
        report_text = "\n".join(report_lines)
        
        # Show Report Modal
        self.show_deduplication_report(report_text)

    def show_deduplication_report(self, report_text):
        """Displays the deduplication report in a scrollable pop-up window."""
        report_win = tk.Toplevel(self)
        report_win.title("Relatório de Deduplicação")
        report_win.geometry("700x550")
        report_win.minsize(550, 400)
        report_win.grab_set() # Focus modal
        
        # Frame
        frame = ttk.Frame(report_win, padding=15)
        frame.pack(fill="both", expand=True)
        
        # Title
        ttk.Label(frame, text="Relatório de Deduplicação e Fusão de Fontes", font=("Segoe UI", 12, "bold"), foreground=self.primary_color).pack(anchor="w", pady=(0, 10))
        
        # Scrollable Text
        txt_area = tk.Text(frame, wrap="word", font=("Consolas", 9), bg="#ffffff")
        txt_area.insert("1.0", report_text)
        txt_area.configure(state="disabled")
        
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=txt_area.yview)
        txt_area.configure(yscrollcommand=scrollbar.set)
        
        txt_area.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Bottom Frame for Buttons
        btn_frame = ttk.Frame(report_win, padding=10)
        btn_frame.pack(fill="x")
        
        def save_to_txt():
            file_path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt")],
                initialfile="3_relatorio_deduplicacao.txt"
            )
            if file_path:
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(report_text)
                    messagebox.showinfo("Sucesso", f"Relatório salvo com sucesso em:\n{file_path}")
                except Exception as e:
                    messagebox.showerror("Erro", f"Erro ao salvar arquivo:\n{str(e)}")
                    
        ttk.Button(btn_frame, text="Salvar Relatório (.txt)", style="Primary.TButton", command=save_to_txt).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Fechar", style="Secondary.TButton", command=report_win.destroy).pack(side="right", padx=5)

    def populate_treeview(self):
        """Populates the Treeview widget with the current session papers."""
        # Clear existing items
        for item in self.tree_triagem.get_children():
            self.tree_triagem.delete(item)
            
        for t in self.current_session.get('trabalhos', []):
            t_id = str(t['id'])
            self.tree_triagem.insert(
                "", 
                tk.END, 
                iid=t_id,
                values=(t['id'], t['Título'], t['Autores'], t['Ano'], t['Fonte'], t['Decisao']),
                tags=(t['Decisao'],)
            )

    def on_treeview_select(self, event):
        """Fires when a paper row is selected in the Treeview."""
        selected_items = self.tree_triagem.selection()
        if not selected_items:
            return
        
        # Only save current paper decisions if NOT in automated batch mode
        if not getattr(self, 'batch_t1_running', False):
            self.save_current_paper_decisions()
        
        paper_id = str(selected_items[0])
        # Find paper index in session
        for idx, t in enumerate(self.current_session.get('trabalhos', [])):
            if str(t['id']) == paper_id:
                self.selected_paper_index = idx
                self.update_dynamic_form(t)
                break

    def save_current_paper_abstract_only(self):
        """Saves only the abstract content into the active paper state."""
        if self.selected_paper_index is not None:
            paper = self.current_session['trabalhos'][self.selected_paper_index]
            paper['Resumo'] = self.txt_paper_abstract.get("1.0", tk.END).strip()

    def update_dynamic_form(self, paper):
        """Updates the details and build the dynamic criteria checklist/question inputs."""
        # Update metadata details
        self.lbl_paper_title.configure(text=paper['Título'])
        meta_str = f"Autores: {paper['Autores']} | Ano: {paper['Ano']} | Fonte: {paper['Fonte']}\nTipo: {paper['Tipo de Pesquisa']} | Inst: {paper['Universidade / Editora / Revista']}"
        self.lbl_paper_meta.configure(text=meta_str)
        
        # Update link details
        url = paper.get('Link para Download', '')
        if url:
            self.lbl_paper_link.configure(text="Abrir link de acesso ao trabalho ↗", foreground="#0066cc")
            self.lbl_paper_link.bind("<Button-1>", lambda e: webbrowser.open_new_tab(url))
        else:
            self.lbl_paper_link.configure(text="Link não disponível", foreground="#666666")
            self.lbl_paper_link.unbind("<Button-1>")
            
        self.txt_paper_abstract.configure(state="normal")
        self.txt_paper_abstract.delete("1.0", tk.END)
        self.txt_paper_abstract.insert(tk.END, paper.get('Resumo', ''))
        # Auto-save abstract when edited or focus lost
        self.txt_paper_abstract.bind("<FocusOut>", lambda e: self.save_current_paper_abstract_only())
        self.txt_paper_abstract.bind("<KeyRelease>", lambda e: self.save_current_paper_abstract_only())
        
        # Clear previous dynamic form widgets
        for child in self.dynamic_form_inner_frame.winfo_children():
            child.destroy()
            
        # Store vars for saving later
        self.dynamic_vars = {
            'criterios': {},
            'perguntas': {},
            'decisao': tk.StringVar(value=paper.get('Decisao', 'Pendente'))
        }
        
        row_idx = 0
        
        # 1. Inclusion Criteria Header & Checklist
        if self.inclusion_criteria:
            ttk.Label(self.dynamic_form_inner_frame, text="Critérios de Inclusão:", font=("Segoe UI", 9, "bold"), foreground=self.primary_color).grid(row=row_idx, column=0, sticky="w", pady=(5, 2))
            row_idx += 1
            for c in self.inclusion_criteria:
                val = paper['Criterios'].get(c, False)
                var = tk.BooleanVar(value=val)
                self.dynamic_vars['criterios'][c] = var
                cb = tk.Checkbutton(
                    self.dynamic_form_inner_frame, 
                    text=c, 
                    variable=var, 
                    command=self.save_current_paper_decisions, 
                    wraplength=0,
                    justify="left",
                    anchor="w",
                    bg="#f0f0f0",
                    activebackground="#f0f0f0",
                    bd=0,
                    highlightthickness=0
                )
                cb.grid(row=row_idx, column=0, sticky="w", padx=10, pady=1)
                row_idx += 1
                
        # 2. Exclusion Criteria Header & Checklist
        if self.exclusion_criteria:
            ttk.Label(self.dynamic_form_inner_frame, text="Critérios de Exclusão:", font=("Segoe UI", 9, "bold"), foreground="#c00000").grid(row=row_idx, column=0, sticky="w", pady=(8, 2))
            row_idx += 1
            for c in self.exclusion_criteria:
                val = paper['Criterios'].get(c, False)
                var = tk.BooleanVar(value=val)
                self.dynamic_vars['criterios'][c] = var
                cb = tk.Checkbutton(
                    self.dynamic_form_inner_frame, 
                    text=c, 
                    variable=var, 
                    command=self.save_current_paper_decisions, 
                    wraplength=0,
                    justify="left",
                    anchor="w",
                    bg="#f0f0f0",
                    activebackground="#f0f0f0",
                    bd=0,
                    highlightthickness=0
                )
                cb.grid(row=row_idx, column=0, sticky="w", padx=10, pady=1)
                row_idx += 1

        # 3. Custom Questions
        if self.triagem_questions:
            ttk.Label(self.dynamic_form_inner_frame, text="Perguntas Analíticas:", font=("Segoe UI", 9, "bold")).grid(row=row_idx, column=0, sticky="w", pady=(8, 2))
            row_idx += 1
            for q in self.triagem_questions:
                ttk.Label(self.dynamic_form_inner_frame, text=q, font=("Segoe UI", 9)).grid(row=row_idx, column=0, sticky="ew", padx=10, pady=(2, 0))
                row_idx += 1
                val = paper['Perguntas'].get(q, "")
                var = tk.StringVar(value=val)
                self.dynamic_vars['perguntas'][q] = var
                ent = ttk.Entry(self.dynamic_form_inner_frame, textvariable=var, width=30)
                ent.grid(row=row_idx, column=0, sticky="ew", padx=10, pady=(0, 4))
                # Auto-save questions on edit
                ent.bind("<FocusOut>", lambda e: self.save_current_paper_decisions())
                ent.bind("<KeyRelease>", lambda e: self.save_current_paper_decisions())
                row_idx += 1
                
        # 4. Observações / Justificativa
        ttk.Separator(self.dynamic_form_inner_frame, orient="horizontal").grid(row=row_idx, column=0, sticky="ew", pady=10)
        row_idx += 1

        ttk.Label(self.dynamic_form_inner_frame, text="Observações / Justificativa:", font=("Segoe UI", 9, "bold"), foreground=self.primary_color).grid(row=row_idx, column=0, sticky="w", pady=2)
        row_idx += 1

        self.txt_observacoes = scrolledtext.ScrolledText(self.dynamic_form_inner_frame, wrap="word", font=("Segoe UI", 9), height=4, width=30)
        self.txt_observacoes.grid(row=row_idx, column=0, sticky="ew", padx=5, pady=(0, 5))
        self.txt_observacoes.insert(tk.END, paper.get('Observacoes', ''))
        self.txt_observacoes.bind("<FocusOut>", lambda e: self.save_current_paper_decisions())
        self.txt_observacoes.bind("<KeyRelease>", lambda e: self.save_current_paper_decisions())
        row_idx += 1

        # 5. Decision Dropdown & Action buttons
        ttk.Label(self.dynamic_form_inner_frame, text="Decisão do Trabalho:", font=("Segoe UI", 9, "bold")).grid(row=row_idx, column=0, sticky="w", pady=2)
        row_idx += 1

        cb_dec = ttk.Combobox(self.dynamic_form_inner_frame, textvariable=self.dynamic_vars['decisao'], values=["Pendente", "Incluído", "Excluído"], state="readonly", width=15)
        cb_dec.grid(row=row_idx, column=0, sticky="w", pady=2)
        cb_dec.bind("<<ComboboxSelected>>", lambda e: self.save_current_paper_decisions())
        row_idx += 1

        btn_action_frame = ttk.Frame(self.dynamic_form_inner_frame)
        btn_action_frame.grid(row=row_idx, column=0, sticky="ew", pady=(10, 5))
        btn_action_frame.columnconfigure(0, weight=1)
        btn_action_frame.columnconfigure(1, weight=1)
        btn_action_frame.columnconfigure(2, weight=1)
        btn_action_frame.columnconfigure(3, weight=1)

        self.btn_gemini_t1 = ttk.Button(btn_action_frame, text="✨ Triar Este com IA", style="Secondary.TButton", command=self.run_gemini_triagem_partner)
        self.btn_gemini_t1.grid(row=0, column=0, sticky="ew", padx=(0, 2))

        self.btn_batch_gemini_t1_form = ttk.Button(btn_action_frame, text="⚡ Triar Todos (Loop)", style="Secondary.TButton", command=self.start_batch_gemini_triagem)
        self.btn_batch_gemini_t1_form.grid(row=0, column=1, sticky="ew", padx=2)

        self.btn_stop_batch_t1_form = ttk.Button(btn_action_frame, text="🛑 Parar Loop", style="Secondary.TButton", command=self.stop_batch_gemini_triagem, state="disabled")
        self.btn_stop_batch_t1_form.grid(row=0, column=2, sticky="ew", padx=2)

        btn_next = ttk.Button(btn_action_frame, text="Confirmar e Próximo", style="Primary.TButton", command=self.confirm_and_next_paper)
        btn_next.grid(row=0, column=3, sticky="ew", padx=(2, 0))
        row_idx += 1

    def save_current_paper_decisions(self):
        """Saves current dynamic form selection values into the active paper state."""
        if getattr(self, 'batch_t1_running', False):
            return
        if self.selected_paper_index is None:
            return
        if self.selected_paper_index >= len(self.current_session.get('trabalhos', [])):
            return

        paper = self.current_session['trabalhos'][self.selected_paper_index]
        if not hasattr(self, 'dynamic_vars') or 'criterios' not in self.dynamic_vars:
            return

        # Save criteria
        for c, var in self.dynamic_vars['criterios'].items():
            paper['Criterios'][c] = var.get()

        # Save questions
        for q, var in self.dynamic_vars['perguntas'].items():
            paper['Perguntas'][q] = var.get()

        # Save observacoes
        if hasattr(self, 'txt_observacoes') and self.txt_observacoes.winfo_exists():
            paper['Observacoes'] = self.txt_observacoes.get("1.0", tk.END).strip()

        # Save edited abstract
        if hasattr(self, 'txt_paper_abstract') and self.txt_paper_abstract.winfo_exists():
            paper['Resumo'] = self.txt_paper_abstract.get("1.0", tk.END).strip()
            
        # Save decision
        if 'decisao' in self.dynamic_vars:
            new_dec = self.dynamic_vars['decisao'].get()
            if paper.get('Decisao') != new_dec:
                paper['Decisao'] = new_dec
                try:
                    self.tree_triagem.item(str(paper['id']), values=(paper['id'], paper['Título'], paper['Autores'], paper['Ano'], paper['Fonte'], paper['Decisao']), tags=(new_dec,))
                except Exception:
                    pass

    def confirm_and_next_paper(self):
        """Saves decisions for current paper and moves selection to next paper."""
        self.save_current_paper_decisions()
        
        # Select next row in treeview
        current_selection = self.tree_triagem.selection()
        if not current_selection:
            return
            
        current_id = current_selection[0]
        children = self.tree_triagem.get_children()
        try:
            current_index = children.index(current_id)
            if current_index + 1 < len(children):
                next_id = children[current_index + 1]
                self.tree_triagem.selection_set(next_id)
                self.tree_triagem.see(next_id)
            else:
                self.status_var.set("Fim da lista alcançado.")
                messagebox.showinfo("Fim da Lista", "Você revisou o último trabalho da triagem.")
        except ValueError:
            pass


    def save_triagem_session(self):
        """Saves the entire project (unified JSON) from the Triagem/Extração tabs."""
        if not self.current_session.get('trabalhos'):
            messagebox.showwarning("Aviso", "Não há nenhuma triagem ativa para salvar.")
            return
        self._save_unified_json()

    def load_triagem_session(self):
        """Imports a project JSON (unified or legacy triagem session)."""
        file_path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if not file_path:
            return

        if self._load_unified_or_legacy(file_path):
            num_trabalhos = len(self.current_session.get('trabalhos', []))
            self.status_var.set(f"Projeto carregado com sucesso: {os.path.basename(file_path)}")
            messagebox.showinfo("Sucesso", f"Projeto carregado com sucesso!\n\nCarregados {num_trabalhos} trabalhos.")

    def get_gemini_config_path(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_dir, "config_gemini.json")

    def load_gemini_config(self):
        path = self.get_gemini_config_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Support new multi-key format
                    if "api_keys" in data and isinstance(data["api_keys"], list):
                        self.gemini_api_keys = [k for k in data["api_keys"] if k and k.strip()]
                    elif "api_key" in data and data["api_key"]:
                        # Backward compatibility: migrate single key to list
                        self.gemini_api_keys = [data["api_key"].strip()]
                    if "model" in data and data["model"]:
                        self.gemini_model.set(data["model"])
            except Exception as e:
                logging.warning(f"Erro ao carregar config_gemini.json: {e}")

    def save_gemini_config(self, show_msg=True):
        path = self.get_gemini_config_path()
        data = {
            "api_keys": self.gemini_api_keys.copy(),
            "model": self.gemini_model.get().strip() or "gemini-3.5-flash"
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if show_msg:
                messagebox.showinfo("Sucesso", f"Configurações do Gemini AI salvas com sucesso!\n{len(self.gemini_api_keys)} chave(s) de API configurada(s).")
        except Exception as e:
            if show_msg:
                messagebox.showerror("Erro", f"Erro ao salvar configurações do Gemini: {e}")

    # --- Multi API Key helpers ---

    def _has_gemini_keys(self):
        """Returns True if at least one API key is configured."""
        return bool(self.gemini_api_keys)

    def _mask_api_key(self, key):
        """Returns a masked version of the key for display (e.g., 'AIza...vm7M')."""
        if not key or len(key) < 8:
            return key or ""
        return f"{key[:4]}...{key[-4:]}"

    def _get_next_api_key(self):
        """Returns the next available API key, skipping exhausted ones.
        Raises ValueError if no keys are available."""
        if not self.gemini_api_keys:
            raise ValueError("Nenhuma chave de API do Gemini configurada. Adicione pelo menos uma na aba 'Configuração Geral'.")

        n = len(self.gemini_api_keys)
        # Try each key once, starting from current index
        for attempt in range(n):
            idx = (self.gemini_current_key_index + attempt) % n
            key = self.gemini_api_keys[idx]
            if key not in self.gemini_exhausted_keys:
                self.gemini_current_key_index = idx
                return key

        # All keys exhausted — reset and use the first one (might work after cooldown)
        logging.warning("Todas as chaves de API foram marcadas como exauridas. Resetando marcações.")
        self.gemini_exhausted_keys.clear()
        self.gemini_current_key_index = 0
        return self.gemini_api_keys[0]

    def _rotate_to_next_key(self, exhausted_key):
        """Marks a key as exhausted and rotates to the next one.
        Returns True if there are still available keys, False if all exhausted."""
        self.gemini_exhausted_keys.add(exhausted_key)
        masked = self._mask_api_key(exhausted_key)
        n = len(self.gemini_api_keys)
        available = [k for k in self.gemini_api_keys if k not in self.gemini_exhausted_keys]

        if available:
            # Advance index to the next non-exhausted key
            for attempt in range(n):
                idx = (self.gemini_current_key_index + 1 + attempt) % n
                if self.gemini_api_keys[idx] not in self.gemini_exhausted_keys:
                    self.gemini_current_key_index = idx
                    next_masked = self._mask_api_key(self.gemini_api_keys[idx])
                    logging.info(f"Chave {masked} exaurida. Rotacionando para chave {next_masked} ({idx + 1}/{n}).")
                    try:
                        self.after(0, lambda: (self._update_gemini_key_status_label(), self._refresh_gemini_keys_listbox()))
                    except Exception:
                        pass
                    return True
        logging.warning(f"Chave {masked} exaurida e nenhuma outra chave disponível ({len(self.gemini_exhausted_keys)}/{n} exauridas).")
        return False

    def _refresh_gemini_keys_listbox(self):
        """Refreshes the Gemini keys listbox display."""
        if not hasattr(self, 'lst_gemini_keys'):
            return
        self.lst_gemini_keys.delete(0, tk.END)
        for i, key in enumerate(self.gemini_api_keys):
            prefix = "▶ " if i == self.gemini_current_key_index else "   "
            exhausted = " [EXAURIDA]" if key in self.gemini_exhausted_keys else ""
            self.lst_gemini_keys.insert(tk.END, f"{prefix}{i + 1}. {self._mask_api_key(key)}{exhausted}")

    def _update_gemini_key_status_label(self):
        """Updates the status label showing active key info."""
        if not hasattr(self, 'lbl_gemini_key_status'):
            return
        n = len(self.gemini_api_keys)
        if n == 0:
            self.lbl_gemini_key_status.configure(text="Nenhuma chave configurada", foreground="#cc0000")
        else:
            exhausted = len(self.gemini_exhausted_keys)
            active_idx = self.gemini_current_key_index % n if n > 0 else 0
            text = f"Chave ativa: {active_idx + 1}/{n}"
            if exhausted > 0:
                text += f"  •  {exhausted} exaurida(s)"
            self.lbl_gemini_key_status.configure(text=text, foreground="#1f497d")

    def _add_gemini_key(self):
        """Adds a new API key from the entry field."""
        key = self.ent_new_gemini_key.get().strip()
        if not key:
            messagebox.showwarning("Aviso", "Digite uma chave de API antes de adicionar.")
            return
        if key in self.gemini_api_keys:
            messagebox.showwarning("Duplicada", f"Esta chave já está na lista: {self._mask_api_key(key)}")
            return
        self.gemini_api_keys.append(key)
        self.ent_new_gemini_key.delete(0, tk.END)
        self._refresh_gemini_keys_listbox()
        self._update_gemini_key_status_label()
        self.save_gemini_config(show_msg=False)
        self.status_var.set(f"Chave de API adicionada ({self._mask_api_key(key)}). Total: {len(self.gemini_api_keys)}")

    def _remove_gemini_key(self):
        """Removes the selected API key from the list."""
        sel = self.lst_gemini_keys.curselection()
        if not sel:
            messagebox.showwarning("Aviso", "Selecione uma chave na lista para remover.")
            return
        idx = sel[0]
        if idx < len(self.gemini_api_keys):
            removed = self.gemini_api_keys.pop(idx)
            self.gemini_exhausted_keys.discard(removed)
            # Adjust current index if needed
            if self.gemini_current_key_index >= len(self.gemini_api_keys):
                self.gemini_current_key_index = 0
            self._refresh_gemini_keys_listbox()
            self._update_gemini_key_status_label()
            self.save_gemini_config(show_msg=False)
            self.status_var.set(f"Chave de API removida ({self._mask_api_key(removed)}). Total: {len(self.gemini_api_keys)}")

    def test_gemini_connection(self):
        if not self._has_gemini_keys():
            messagebox.showwarning("Aviso", "Adicione pelo menos uma chave de API do Gemini antes de testar.")
            return

        self.status_var.set("Testando conexão com a API do Gemini...")
        def worker():
            try:
                res = self.call_gemini_api("Responda em formato JSON exclusivamente: {\"status\": \"ok\", \"mensagem\": \"Conexão bem sucedida\"}")
                def ok():
                    self.save_gemini_config(show_msg=False)
                    if res:
                        active_key = self._mask_api_key(self.gemini_api_keys[self.gemini_current_key_index % len(self.gemini_api_keys)])
                        self.status_var.set("Conexão com Gemini estabelecida com sucesso!")
                        messagebox.showinfo("Sucesso", f"Conexão com a API do Gemini ({self.gemini_model.get()}) realizada com sucesso!\nChave usada: {active_key}\n\nResposta: {str(res)[:100]}")
                    else:
                        self.status_var.set("Falha na resposta do Gemini.")
                        messagebox.showerror("Erro de Conexão", f"A API do Gemini ({self.gemini_model.get()}) não retornou uma resposta válida. Verifique se a chave de API é válida.")
                self.after(0, ok)
            except Exception as e:
                def err(msg=str(e)):
                    self.status_var.set("Falha na conexão com o Gemini.")
                    messagebox.showerror("Erro de Conexão", f"Não foi possível conectar à API do Gemini:\n\n{msg}")
                self.after(0, err)

        threading.Thread(target=worker, daemon=True).start()

    def call_gemini_api(self, prompt_text, system_instruction=None):
        """Calls Gemini API with automatic key rotation on quota exhaustion."""
        if not self._has_gemini_keys():
            raise ValueError("Nenhuma chave de API do Gemini configurada. Adicione pelo menos uma na aba 'Configuração Geral'.")

        user_model = self.gemini_model.get().strip() or "gemini-2.5-flash"

        prompt_text = sanitize_text(prompt_text)
        if system_instruction:
            system_instruction = sanitize_text(system_instruction)

        # Build candidate models list (try user's configured model first, then standard fallbacks)
        candidate_models = [user_model]
        for fallback in ["gemini-3.6-flash", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.5-pro"]:
            if fallback not in candidate_models:
                candidate_models.append(fallback)

        # Outer loop: rotate through API keys on quota exhaustion
        keys_tried = 0
        max_key_attempts = len(self.gemini_api_keys)
        last_error = None

        while keys_tried < max_key_attempts:
            api_key = self._get_next_api_key()
            keys_tried += 1
            key_succeeded = False

            for model in candidate_models:
                # 1. Direct REST API call
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                    payload = {
                        "contents": [
                            {
                                "parts": [{"text": prompt_text}]
                            }
                        ],
                        "generationConfig": {
                            "responseMimeType": "application/json"
                        }
                    }
                    if system_instruction:
                        payload["systemInstruction"] = {
                            "parts": [{"text": system_instruction}]
                        }

                    headers = {"Content-Type": "application/json"}
                    resp = requests.post(url, json=payload, headers=headers, timeout=60)
                    if resp.status_code == 200:
                        data = resp.json()
                        try:
                            text = data['candidates'][0]['content']['parts'][0]['text']
                            if text:
                                return text
                        except (KeyError, IndexError):
                            pass
                    elif resp.status_code == 429 or "RESOURCE_EXHAUSTED" in resp.text:
                        # Quota exhausted — rotate to next key
                        has_more = self._rotate_to_next_key(api_key)
                        if has_more:
                            logging.info(f"Chave {self._mask_api_key(api_key)} exaurida (429). Tentando próxima chave...")
                            break  # Break model loop to retry with next key
                        else:
                            raise RuntimeError(
                                f"Todas as {len(self.gemini_api_keys)} chaves de API atingiram o limite de cota (429 - Resource Exhausted).\n\n"
                                f"Aguarde alguns minutos para os limites resetarem ou adicione novas chaves na aba 'Configuração Geral'."
                            )
                    elif resp.status_code == 503 or "UNAVAILABLE" in resp.text:
                        raise RuntimeError("Modelo Temporariamente Indisponível (Erro 503 - High Demand).\n\nO modelo do Gemini está enfrentando alta demanda temporária nos servidores do Google.\nAguarde alguns segundos e tente novamente.")
                    else:
                        last_error = f"Erro na API Gemini ({resp.status_code}): {resp.text}"
                except RuntimeError:
                    raise
                except Exception as ex:
                    last_error = str(ex)

                # 2. Try SDK as secondary fallback
                try:
                    from google import genai
                    client = genai.Client(api_key=api_key)
                    config = {"response_mime_type": "application/json"}
                    if system_instruction:
                        config["system_instruction"] = system_instruction
                    response = client.models.generate_content(
                        model=model,
                        contents=prompt_text,
                        config=config
                    )
                    if hasattr(response, 'text') and response.text:
                        return response.text
                except Exception as sdk_err:
                    err_str = str(sdk_err)
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        has_more = self._rotate_to_next_key(api_key)
                        if has_more:
                            logging.info(f"Chave {self._mask_api_key(api_key)} exaurida via SDK (429). Tentando próxima chave...")
                            break  # Break model loop to retry with next key
                        else:
                            raise RuntimeError(
                                f"Todas as {len(self.gemini_api_keys)} chaves de API atingiram o limite de cota (429 - Resource Exhausted).\n\n"
                                f"Aguarde alguns minutos para os limites resetarem ou adicione novas chaves na aba 'Configuração Geral'."
                            )
                    if "503" in err_str or "UNAVAILABLE" in err_str:
                        raise RuntimeError("Modelo Temporariamente Indisponível (Erro 503 - High Demand).\n\nO modelo do Gemini está enfrentando alta demanda temporária nos servidores do Google.\nAguarde alguns segundos e tente novamente.")
                    logging.warning(f"google-genai SDK call failed for model '{model}': {sdk_err}")

        if last_error:
            raise RuntimeError(f"Falha em todas as tentativas da API Gemini: {last_error}")

    def stop_batch_gemini_triagem(self):
        """Requests cancellation of the ongoing batch AI screening loop."""
        if getattr(self, 'batch_t1_running', False):
            self.batch_t1_cancel_requested = True
            self.status_var.set("⏳ Solicitando parada da triagem em lote... Aguardando estudo atual.")
            if hasattr(self, 'btn_stop_batch_t1'):
                self.btn_stop_batch_t1.configure(state="disabled")
            if hasattr(self, 'btn_stop_batch_t1_form'):
                self.btn_stop_batch_t1_form.configure(state="disabled")

    def start_batch_gemini_triagem(self):
        """Executes continuous AI screening (Triagem 1) for all pending papers in a sequential background loop."""
        if getattr(self, 'batch_t1_running', False):
            messagebox.showinfo("Em Execução", "A triagem em lote já está em andamento.")
            return

        if not self._has_gemini_keys():
            messagebox.showwarning("API Key Ausente", "Nenhuma chave de API configurada. Adicione pelo menos uma na aba 'Configuração Geral'.")
            self.notebook.select(self.tab_general)
            return

        all_papers = self.current_session.get('trabalhos', [])
        if not all_papers:
            messagebox.showwarning("Sem Trabalhos", "Nenhum trabalho carregado na sessão para triar.")
            return

        pending_indices = [i for i, p in enumerate(all_papers) if p.get('Decisao') == 'Pendente']
        if not pending_indices:
            res = messagebox.askyesno("Todos os Trabalhos Triados", "Todos os trabalhos já possuem decisão (Incluído/Excluído).\nDeseja re-analisar TODOS os trabalhos da lista com o Gemini?")
            if not res:
                return
            pending_indices = list(range(len(all_papers)))

        # Update button states for batch mode
        self.batch_t1_running = True
        self.batch_t1_cancel_requested = False

        if hasattr(self, 'btn_batch_gemini_t1'):
            self.btn_batch_gemini_t1.configure(state="disabled")
        if hasattr(self, 'btn_batch_gemini_t1_form'):
            self.btn_batch_gemini_t1_form.configure(state="disabled")

        if hasattr(self, 'btn_stop_batch_t1'):
            self.btn_stop_batch_t1.configure(state="normal")
        if hasattr(self, 'btn_stop_batch_t1_form'):
            self.btn_stop_batch_t1_form.configure(state="normal")

        total_to_process = len(pending_indices)
        self.status_var.set(f"🤖 Iniciando triagem em lote com Gemini para {total_to_process} estudos...")

        # Build protocol context once
        protocol_info = {
            "nome_revisao": self.ent_project_name.get().strip() if hasattr(self, 'ent_project_name') else "",
            "criterios_inclusao": self.inclusion_criteria,
            "criterios_exclusao": self.exclusion_criteria,
            "perguntas_analiticas": self.triagem_questions
        }

        protocol_details = {}
        for name, widget in self.protocol_widgets.items():
            try:
                if isinstance(widget, (tk.Text, scrolledtext.ScrolledText)):
                    val = widget.get("1.0", tk.END).strip()
                elif hasattr(widget, 'get'):
                    try:
                        val = widget.get().strip()
                    except TypeError:
                        val = widget.get("1.0", tk.END).strip()
                else:
                    val = ""
                if val:
                    protocol_details[name] = val
            except Exception:
                pass
        if protocol_details:
            protocol_info["detalhes_protocolo"] = protocol_details

        inc_fmt = ", ".join([f"{json.dumps(c, ensure_ascii=False)}: true/false" for c in self.inclusion_criteria]) or '"Critério Inclusão": true/false'
        exc_fmt = ", ".join([f"{json.dumps(c, ensure_ascii=False)}: true/false" for c in self.exclusion_criteria]) or '"Critério Exclusão": true/false'
        q_fmt = ", ".join([f"{json.dumps(q, ensure_ascii=False)}: \"...\"" for q in self.triagem_questions]) or '"Pergunta Analítica": "..."'

        def batch_worker():
            processed_count = 0
            stopped_by_user = False

            def normalize(s):
                if not isinstance(s, str):
                    s = str(s)
                return re.sub(r'[;\s\.,]+', ' ', s).strip().lower()

            def get_json_key_val(dict_data, target_key):
                if not isinstance(dict_data, dict):
                    return None
                if target_key in dict_data:
                    return dict_data[target_key]
                target_norm = normalize(target_key)
                for k, v in dict_data.items():
                    if normalize(k) == target_norm:
                        return v
                for k, v in dict_data.items():
                    k_norm = normalize(k)
                    if len(target_norm) > 8 and len(k_norm) > 8:
                        if target_norm in k_norm or k_norm in target_norm:
                            return v
                return None

            def parse_json_from_response(raw_text):
                if not raw_text or not isinstance(raw_text, str):
                    return None
                text_clean = raw_text.strip()
                try:
                    return json.loads(text_clean, strict=False)
                except Exception:
                    pass
                if "```" in text_clean:
                    lines = []
                    in_block = False
                    for line in text_clean.splitlines():
                        ls = line.strip()
                        if ls.startswith("```"):
                            in_block = not in_block
                            continue
                        if in_block:
                            lines.append(line)
                    if lines:
                        try:
                            return json.loads("\n".join(lines).strip(), strict=False)
                        except Exception:
                            pass
                m = re.search(r'\{.*\}', text_clean, re.DOTALL)
                if m:
                    try:
                        return json.loads(m.group(0), strict=False)
                    except Exception:
                        pass
                return None

            for idx_pos, idx in enumerate(pending_indices, start=1):
                if self.batch_t1_cancel_requested:
                    stopped_by_user = True
                    break

                paper = all_papers[idx]
                paper_id = paper.get('id', idx + 1)

                # Select paper on UI
                def select_paper_ui(paper_idx=idx, pos=idx_pos, p_id=paper_id, p=paper):
                    self.selected_paper_index = paper_idx
                    self.status_var.set(f"🤖 Triagem em Lote Gemini [{pos}/{total_to_process}]: Analisando estudo #{p_id}...")
                    try:
                        self.update_dynamic_form(p)
                        tree_items = self.tree_triagem.get_children()
                        if 0 <= paper_idx < len(tree_items):
                            self.tree_triagem.selection_set(tree_items[paper_idx])
                            self.tree_triagem.see(tree_items[paper_idx])
                    except Exception:
                        pass

                self.after(0, select_paper_ui)

                study_info = {
                    "id": paper_id,
                    "titulo": sanitize_text(paper.get("Título", "")),
                    "autores": sanitize_text(paper.get("Autores", "")),
                    "ano": paper.get("Ano", ""),
                    "fonte": sanitize_text(paper.get("Fonte", "")),
                    "resumo": sanitize_text(paper.get("Resumo", ""))
                }

                # Pre-check: if abstract/metadata is missing or corrupt, leave as Pendente without calling API
                resumo_text = study_info["resumo"].strip()
                resumo_lower = resumo_text.lower()
                invalid_markers = [
                    "", "n/a", "na", "n/d", "nd", "none", "null", "undefined",
                    "sem resumo", "sem resumo disponível", "sem resumo disponivel",
                    "abstract not available", "no abstract available",
                    "não informado", "nao informado", "não disponível", "nao disponivel",
                    "resumo não disponível", "resumo nao disponivel"
                ]

                if not resumo_text or resumo_lower in invalid_markers or len(resumo_text) < 20:
                    paper['Decisao'] = 'Pendente'
                    paper['Observacoes'] = 'Mantido como Pendente: Resumo ausente, não informado ou metadados insuficientes.'
                    processed_count += 1

                    def update_insufficient_ui(paper_idx=idx, p=paper, pos=idx_pos, p_id=paper_id):
                        try:
                            item_id = str(p['id'])
                            self.tree_triagem.item(item_id, values=(
                                p.get("id"), p.get("Título"), p.get("Autores"),
                                p.get("Ano"), p.get("Fonte"), "Pendente"
                            ), tags=("Pendente",))
                        except Exception:
                            pass
                        if self.selected_paper_index == paper_idx:
                            self.update_dynamic_form(p)
                        self._save_unified_json_quietly()
                        self.status_var.set(f"⚠️ [{pos}/{total_to_process}] Estudo #{p_id}: Mantido como Pendente (Resumo ausente/insuficiente)")

                    self.after(0, update_insufficient_ui)
                    time.sleep(0.5)
                    continue

                prompt = f"""Você é um Parceiro de Triagem Especialista em Revisões Sistemáticas da Literatura.
Seu papel é analisar o estudo selecionado abaixo com base estrita no protocolo metodológico fornecido.

CONTEXTO DA REVISÃO SISTEMÁTICA (PROTOCOLO):
{json.dumps(protocol_info, ensure_ascii=False, indent=2)}

ESTUDO SELECIONADO PARA TRIAGEM (Título e Resumo):
{json.dumps(study_info, ensure_ascii=False, indent=2)}

INSTRUÇÕES RIGOROSAS DE AVALIAÇÃO E MARCAÇÃO DE CHECKBOXES:
1. VERIFICAÇÃO DE INTEGRIDADE DOS DADOS:
   Se o resumo estiver ausente, em branco, truncado, corrompido, contendo informações deslocadas/desconectadas, ou se os dados forem insuficientes para definir entre Incluído ou Excluído:
   - Marque "decisao_sugerida": "Pendente".
   - Defina todos os critérios de inclusão e exclusão como false.
   - Em "observacoes", descreva expressamente: "Informações ausentes, deslocadas ou insuficientes para definir inclusão/exclusão."
2. 'criterios_inclusao': Para CADA critério de inclusão listado no protocolo, responda true se o estudo atende, ou false se NÃO atende.
3. 'criterios_exclusao': Para CADA critério de exclusão listado no protocolo, responda true se o estudo INCORRE no motivo de exclusão ou se deve ser desconsiderado por fuga ao tema/escopo, ou false se NÃO incorre.
   REGRA OBRIGATÓRIA: Se a decisao_sugerida for "Excluído", você DEVE OBRIGATORIAMENTE marcar true para pelo menos UM critério em 'criterios_exclusao'.
4. 'perguntas': Responda a cada pergunta analítica com evidências do resumo.
5. 'decisao_sugerida':
   - "Incluído": se o trabalho atende a TODOS os critérios de inclusão e NÃO incorre em nenhum critério de exclusão.
   - "Excluído": se o trabalho falha em critérios de inclusão ou incorre em QUALQUER critério de exclusão.
   - "Pendente": se o resumo for omisso, deslocado, corrompido ou insuficiente para tomada de decisão.
6. 'observacoes': Justificativa técnica citando os critérios ou o motivo de pendência/exclusão.

Retorne EXCLUSIVAMENTE um objeto JSON válido com a seguinte estrutura:
{{
  "criterios_inclusao": {{ {inc_fmt} }},
  "criterios_exclusao": {{ {exc_fmt} }},
  "perguntas": {{ {q_fmt} }},
  "decisao_sugerida": "Incluído", "Excluído" ou "Pendente",
  "observacoes": "Justificativa detalhada..."
}}
"""
                res = None
                max_retries = 3
                last_paper_error = ""

                for attempt in range(1, max_retries + 1):
                    try:
                        raw_text = self.call_gemini_api(prompt)
                        res = parse_json_from_response(raw_text)
                        if res and isinstance(res, dict):
                            break  # JSON successfully parsed
                        else:
                            last_paper_error = "Resposta do Gemini não contém estrutura JSON válida."
                            logging.warning(f"Erro de parse JSON no estudo #{paper_id} (Tentativa {attempt}). Texto bruto: {str(raw_text)[:200]}")
                    except RuntimeError as r_err:
                        err_msg = str(r_err)
                        last_paper_error = err_msg
                        if "Todas as" in err_msg and "exauridas" in err_msg:
                            # All keys exhausted — stop batch loop immediately
                            self.after(0, lambda m=err_msg: messagebox.showerror("Cota Exaurida", m))
                            stopped_by_user = True
                            break
                        if ("429" in err_msg or "503" in err_msg or "Resource Exhausted" in err_msg or "High Demand" in err_msg) and attempt < max_retries:
                            wait_sec = 6 * attempt
                            self.after(0, lambda pos=idx_pos, p_id=paper_id, w=wait_sec, att=attempt: self.status_var.set(
                                f"⏳ Gemini ocupado/limite de cota atingido. Aguardando {w}s para re-tentar estudo #{p_id} (Tentativa {att}/{max_retries})..."
                            ))
                            time.sleep(wait_sec)
                        else:
                            logging.warning(f"Erro ao triar estudo #{paper_id} com Gemini (Tentativa {attempt}): {r_err}")
                            break
                    except Exception as paper_err:
                        last_paper_error = str(paper_err)
                        logging.warning(f"Erro ao triar estudo #{paper_id} com Gemini: {paper_err}")
                        break

                if stopped_by_user:
                    break

                if res and isinstance(res, dict):
                    inc_res = res.get('criterios_inclusao', {})
                    exc_res = res.get('criterios_exclusao', {})

                    paper['Criterios'] = paper.get('Criterios', {})
                    for c in self.inclusion_criteria:
                        val = get_json_key_val(inc_res, c)
                        if val is not None:
                            paper['Criterios'][c] = bool(val)

                    has_exclusion = False
                    for c in self.exclusion_criteria:
                        val = get_json_key_val(exc_res, c)
                        if val is not None:
                            is_chk = bool(val)
                            paper['Criterios'][c] = is_chk
                            if is_chk:
                                has_exclusion = True

                    dec = res.get('decisao_sugerida')
                    if dec in ["Incluído", "Excluído", "Pendente"]:
                        paper['Decisao'] = dec

                    if dec == "Excluído" and self.exclusion_criteria and not has_exclusion:
                        paper['Criterios'][self.exclusion_criteria[0]] = True

                    q_res = res.get('perguntas', {})
                    paper['Perguntas'] = paper.get('Perguntas', {})
                    for q in self.triagem_questions:
                        val_q = get_json_key_val(q_res, q)
                        if val_q is not None:
                            paper['Perguntas'][q] = str(val_q)

                    paper['Observacoes'] = res.get('observacoes', paper.get('Observacoes', ''))

                    processed_count += 1

                    def update_paper_ui(paper_idx=idx, p=paper, pos=idx_pos, p_id=paper_id):
                        try:
                            item_id = str(p['id'])
                            dec_val = p.get("Decisao", "Pendente")
                            self.tree_triagem.item(item_id, values=(
                                p.get("id"),
                                p.get("Título"),
                                p.get("Autores"),
                                p.get("Ano"),
                                p.get("Fonte"),
                                dec_val
                            ), tags=(dec_val,))
                        except Exception as e:
                            logging.warning(f"Erro ao atualizar linha da árvore para estudo #{p_id}: {e}")

                        self.selected_paper_index = paper_idx
                        self.update_dynamic_form(p)
                        self._save_unified_json_quietly()
                        self.status_var.set(f"✅ [{pos}/{total_to_process}] Estudo #{p_id} triado com sucesso: {p.get('Decisao')}")

                    self.after(0, update_paper_ui)
                else:
                    err_brief = last_paper_error[:60] if last_paper_error else "Falha no parse de JSON"
                    self.after(0, lambda pos=idx_pos, p_id=paper_id, err=err_brief: self.status_var.set(
                        f"⚠️ [{pos}/{total_to_process}] Estudo #{p_id} ignorado ({err})"
                    ))

                time.sleep(1.5)

            def finish_batch():
                self.batch_t1_running = False
                self.batch_t1_cancel_requested = False

                if hasattr(self, 'btn_batch_gemini_t1'):
                    self.btn_batch_gemini_t1.configure(state="normal")
                if hasattr(self, 'btn_batch_gemini_t1_form'):
                    self.btn_batch_gemini_t1_form.configure(state="normal")

                if hasattr(self, 'btn_stop_batch_t1'):
                    self.btn_stop_batch_t1.configure(state="disabled")
                if hasattr(self, 'btn_stop_batch_t1_form'):
                    self.btn_stop_batch_t1_form.configure(state="disabled")

                self._save_unified_json_quietly()

                if stopped_by_user:
                    self.status_var.set(f"⏹️ Triagem em lote interrompida. {processed_count} estudos triados.")
                    messagebox.showinfo("Triagem Interrompida", f"O loop automático de triagem foi interrompido pelo usuário.\n\nEstudos triados nesta execução: {processed_count}/{total_to_process}")
                else:
                    self.status_var.set(f"✨ Triagem em lote concluída! {processed_count} estudos triados pelo Gemini.")
                    messagebox.showinfo("Triagem em Lote Concluída", f"Todos os estudos pendentes foram triados com sucesso pelo Gemini AI!\n\nTotal de estudos triados: {processed_count}")

            self.after(0, finish_batch)

        threading.Thread(target=batch_worker, daemon=True).start()

    def run_gemini_triagem_partner(self):
        if self.selected_paper_index is None:
            messagebox.showwarning("Aviso", "Selecione um trabalho na lista acima para analisar.")
            return

        if not self._has_gemini_keys():
            messagebox.showwarning("API Key Ausente", "Nenhuma chave de API configurada. Adicione pelo menos uma na aba 'Configuração Geral'.")
            self.notebook.select(self.tab_general)
            return

        paper = self.current_session['trabalhos'][self.selected_paper_index]

        protocol_info = {
            "nome_revisao": self.ent_project_name.get().strip() if hasattr(self, 'ent_project_name') else "",
            "criterios_inclusao": self.inclusion_criteria,
            "criterios_exclusao": self.exclusion_criteria,
            "perguntas_analiticas": self.triagem_questions
        }

        protocol_details = {}
        for name, widget in self.protocol_widgets.items():
            try:
                if isinstance(widget, (tk.Text, scrolledtext.ScrolledText)):
                    val = widget.get("1.0", tk.END).strip()
                elif hasattr(widget, 'get'):
                    try:
                        val = widget.get().strip()
                    except TypeError:
                        val = widget.get("1.0", tk.END).strip()
                else:
                    val = ""
                if val:
                    protocol_details[name] = val
            except Exception:
                pass
        if protocol_details:
            protocol_info["detalhes_protocolo"] = protocol_details

        study_info = {
            "id": paper.get("id", ""),
            "titulo": paper.get("Título", ""),
            "autores": paper.get("Autores", ""),
            "ano": paper.get("Ano", ""),
            "fonte": paper.get("Fonte", ""),
            "resumo": paper.get("Resumo", "")
        }

        if hasattr(self, 'btn_gemini_t1'):
            self.btn_gemini_t1.configure(state="disabled")
        self.status_var.set(f"🤖 Gemini analisando estudo '{paper.get('id')}'...")

        inc_fmt = ", ".join([f"{json.dumps(c, ensure_ascii=False)}: true/false" for c in self.inclusion_criteria]) or '"Critério Inclusão": true/false'
        exc_fmt = ", ".join([f"{json.dumps(c, ensure_ascii=False)}: true/false" for c in self.exclusion_criteria]) or '"Critério Exclusão": true/false'
        q_fmt = ", ".join([f"{json.dumps(q, ensure_ascii=False)}: \"...\"" for q in self.triagem_questions]) or '"Pergunta Analítica": "..."'

        def worker():
            try:
                # Pre-check for empty/missing abstract in single screening
                resumo_text = study_info["resumo"].strip()
                resumo_lower = resumo_text.lower()
                invalid_markers = [
                    "", "n/a", "na", "n/d", "nd", "none", "null", "undefined",
                    "sem resumo", "sem resumo disponível", "sem resumo disponivel",
                    "abstract not available", "no abstract available",
                    "não informado", "nao informado", "não disponível", "nao disponivel",
                    "resumo não disponível", "resumo nao disponivel"
                ]

                if not resumo_text or resumo_lower in invalid_markers or len(resumo_text) < 20:
                    def update_insufficient_single():
                        paper['Decisao'] = 'Pendente'
                        paper['Observacoes'] = 'Mantido como Pendente: Resumo ausente, não informado ou metadados insuficientes.'
                        if hasattr(self, 'btn_gemini_t1'):
                            self.btn_gemini_t1.configure(state="normal")
                        self.update_dynamic_form(paper)
                        self._save_unified_json_quietly()
                        self.status_var.set("⚠️ Estudo mantido como Pendente (Resumo ausente/insuficiente).")
                        messagebox.showwarning("Informações Insuficientes", "O estudo selecionado não possui resumo suficiente nos metadados.\nFoi mantido com a decisão 'Pendente'.")

                    self.after(0, update_insufficient_single)
                    return

                prompt = f"""Você é um Parceiro de Triagem Especialista em Revisões Sistemáticas da Literatura.
Seu papel é analisar o estudo selecionado abaixo com base estrita no protocolo metodológico fornecido.

CONTEXTO DA REVISÃO SISTEMÁTICA (PROTOCOLO):
{json.dumps(protocol_info, ensure_ascii=False, indent=2)}

ESTUDO SELECIONADO PARA TRIAGEM (Título e Resumo):
{json.dumps(study_info, ensure_ascii=False, indent=2)}

INSTRUÇÕES RIGOROSAS DE AVALIAÇÃO E MARCAÇÃO DE CHECKBOXES:
1. VERIFICAÇÃO DE INTEGRIDADE DOS DADOS:
   Se o resumo estiver ausente, em branco, truncado, corrompido, contendo informações deslocadas/desconectadas, ou se os dados forem insuficientes para definir entre Incluído ou Excluído:
   - Marque "decisao_sugerida": "Pendente".
   - Defina todos os critérios de inclusão e exclusão como false.
   - Em "observacoes", descreva expressamente: "Informações ausentes, deslocadas ou insuficientes para definir inclusão/exclusão."
2. 'criterios_inclusao': Para CADA critério de inclusão listado no protocolo, responda true se o estudo atende, ou false se NÃO atende.
3. 'criterios_exclusao': Para CADA critério de exclusão listado no protocolo, responda true se o estudo INCORRE no motivo de exclusão ou se deve ser desconsiderado por fuga ao tema/escopo, ou false se NÃO incorre.
   REGRA OBRIGATÓRIA: Se a decisao_sugerida for "Excluído", você DEVE OBRIGATORIAMENTE marcar true para pelo menos UM critério em 'criterios_exclusao'.
4. 'perguntas': Responda a cada pergunta analítica com evidências do resumo.
5. 'decisao_sugerida':
   - "Incluído": se o trabalho atende a TODOS os critérios de inclusão e NÃO incorre em nenhum critério de exclusão.
   - "Excluído": se o trabalho falha em critérios de inclusão ou incorre em QUALQUER critério de exclusão.
   - "Pendente": se o resumo for omisso, deslocado, corrompido ou insuficiente para tomada de decisão.
6. 'observacoes': Justificativa técnica citando os critérios ou o motivo de pendência/exclusão.

Retorne EXCLUSIVAMENTE um objeto JSON válido com a seguinte estrutura:
{{
  "criterios_inclusao": {{ {inc_fmt} }},
  "criterios_exclusao": {{ {exc_fmt} }},
  "perguntas": {{ {q_fmt} }},
  "decisao_sugerida": "Incluído", "Excluído" ou "Pendente",
  "observacoes": "Justificativa detalhada..."
}}
"""
                raw_text = self.call_gemini_api(prompt)
                clean_text = raw_text.strip()
                if clean_text.startswith("```"):
                    lines = clean_text.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    clean_text = "\n".join(lines).strip()

                res = json.loads(clean_text)

                def normalize(s):
                    if not isinstance(s, str):
                        s = str(s)
                    return re.sub(r'[;\s\.,]+', ' ', s).strip().lower()

                def get_json_key_val(dict_data, target_key):
                    if not isinstance(dict_data, dict):
                        return None
                    if target_key in dict_data:
                        return dict_data[target_key]
                    target_norm = normalize(target_key)
                    for k, v in dict_data.items():
                        if normalize(k) == target_norm:
                            return v
                    for k, v in dict_data.items():
                        k_norm = normalize(k)
                        if len(target_norm) > 8 and len(k_norm) > 8:
                            if target_norm in k_norm or k_norm in target_norm:
                                return v
                    return None

                def update_ui():
                    if self.selected_paper_index is not None and self.current_session['trabalhos'][self.selected_paper_index]['id'] == paper['id']:
                        inc_res = res.get('criterios_inclusao', {})
                        exc_res = res.get('criterios_exclusao', {})

                        # 1. Update Inclusion Criteria Checkboxes
                        for c in self.inclusion_criteria:
                            if c in self.dynamic_vars.get('criterios', {}):
                                val = get_json_key_val(inc_res, c)
                                if val is not None:
                                    self.dynamic_vars['criterios'][c].set(bool(val))

                        # 2. Update Exclusion Criteria Checkboxes
                        has_exclusion_checked = False
                        for c in self.exclusion_criteria:
                            if c in self.dynamic_vars.get('criterios', {}):
                                val = get_json_key_val(exc_res, c)
                                if val is not None:
                                    is_chk = bool(val)
                                    self.dynamic_vars['criterios'][c].set(is_chk)
                                    if is_chk:
                                        has_exclusion_checked = True

                        # 3. Decision Dropdown
                        dec = res.get('decisao_sugerida')
                        if dec in ["Incluído", "Excluído", "Pendente"]:
                            self.dynamic_vars['decisao'].set(dec)

                        # Fallback Guarantee: If decision is Excluído but no exclusion checkbox was set to True, auto-select primary exclusion criterion
                        if dec == "Excluído" and self.exclusion_criteria and not has_exclusion_checked:
                            primary_exc = self.exclusion_criteria[0]
                            if primary_exc in self.dynamic_vars.get('criterios', {}):
                                self.dynamic_vars['criterios'][primary_exc].set(True)

                        # 4. Answer custom analytical questions
                        q_res = res.get('perguntas', {})
                        for q, var in self.dynamic_vars.get('perguntas', {}).items():
                            val_q = get_json_key_val(q_res, q)
                            if val_q is not None:
                                var.set(str(val_q))

                        # 5. Set observations
                        obs = res.get('observacoes', '')
                        if hasattr(self, 'txt_observacoes') and obs:
                            self.txt_observacoes.delete("1.0", tk.END)
                            self.txt_observacoes.insert(tk.END, obs)

                        self.save_current_paper_decisions()
                        self.status_var.set(f"✨ Parceiro de Triagem Gemini concluiu a análise do trabalho #{paper.get('id')}.")
                        messagebox.showinfo(
                            "Parceiro de Triagem Gemini",
                            f"Análise concluída com sucesso para o trabalho #{paper.get('id')}!\n\n"
                            f"Sugestão de Decisão: {dec}\n\n"
                            f"Os checkboxes de Inclusão e Exclusão, Perguntas e Observações foram preenchidos. Revise e confirme!"
                        )

                    if hasattr(self, 'btn_gemini_t1'):
                        self.btn_gemini_t1.configure(state="normal")

                self.after(0, update_ui)

            except Exception as e:
                def show_err(err_msg=str(e)):
                    if hasattr(self, 'btn_gemini_t1'):
                        self.btn_gemini_t1.configure(state="normal")
                    self.status_var.set("Erro na análise do Gemini.")
                    messagebox.showerror("Erro no Parceiro de Triagem", f"Falha ao consultar o Gemini AI:\n\n{err_msg}")
                self.after(0, show_err)

        threading.Thread(target=worker, daemon=True).start()

    def suggest_extraction_field_with_gemini(self):
        """Uses Gemini AI to suggest a relevant data extraction field based on protocol and interests."""
        if not self._has_gemini_keys():
            messagebox.showwarning("API Key Ausente", "Nenhuma chave de API configurada. Adicione pelo menos uma na aba 'Configuração Geral'.")
            self.notebook.select(self.tab_general)
            return

        protocol_info = {
            "nome_revisao": self.ent_project_name.get().strip() if hasattr(self, 'ent_project_name') else "",
            "criterios_inclusao": self.inclusion_criteria,
            "criterios_exclusao": self.exclusion_criteria,
            "perguntas_analiticas": self.triagem_questions,
            "campos_existentes": self.campos_extracao
        }

        protocol_details = {}
        if hasattr(self, 'protocol_widgets'):
            for name, widget in self.protocol_widgets.items():
                try:
                    if isinstance(widget, (tk.Text, scrolledtext.ScrolledText)):
                        val = widget.get("1.0", tk.END).strip()
                    elif hasattr(widget, 'get'):
                        try:
                            val = widget.get().strip()
                        except TypeError:
                            val = widget.get("1.0", tk.END).strip()
                    else:
                        val = ""
                    if val:
                        protocol_details[name] = val
                except Exception:
                    pass
        if protocol_details:
            protocol_info["detalhes_protocolo"] = protocol_details

        if hasattr(self, 'btn_suggest_field_gemini'):
            self.btn_suggest_field_gemini.configure(state="disabled")
        self.status_var.set("🤖 Gemini analisando protocolo para sugerir novo campo de extração...")

        def worker():
            try:
                prompt = f"""Você é um Especialista em Metodologia de Revisão Sistemática da Literatura.
Seu papel é analisar o protocolo de pesquisa abaixo e sugerir UM ÚNICO NOVO CAMPO DE EXTRAÇÃO DE DADOS que seja altamente relevante, útil e específico para sintetizar os estudos desta revisão, e que AINDA NÃO ESTEJA na lista de campos existentes.

CONTEXTO E PROTOCOLO DA REVISÃO:
{json.dumps(protocol_info, ensure_ascii=False, indent=2)}

INSTRUÇÕES:
1. Identifique um conceito, variável, método, indicador ou aspecto técnico fundamental do protocolo que ainda não é capturado pelos campos existentes.
2. O nome do campo deve ser curto, claro e direto (de 2 a 5 palavras). Exemplos: "Metodologia de Análise", "Métricas de Desempenho", "Tecnologias Utilizadas", "Escopo Geográfico / Amostra", "Principais Desafios / Obstáculos".
3. Forneça uma breve explicação (1 frase) sobre a importância deste campo para os objetivos da revisão.

Retorne EXCLUSIVAMENTE um objeto JSON válido no formato:
{{
  "novo_campo": "Nome do Campo Sugerido",
  "justificativa": "Breve justificativa técnica da importância do campo."
}}
"""
                raw_text = self.call_gemini_api(prompt)
                clean_text = raw_text.strip()
                if clean_text.startswith("```"):
                    lines = clean_text.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    clean_text = "\n".join(lines).strip()

                res = json.loads(clean_text)
                suggested_field = res.get('novo_campo', '').strip()
                justification = res.get('justificativa', '').strip()

                def update_ui():
                    if hasattr(self, 'btn_suggest_field_gemini'):
                        self.btn_suggest_field_gemini.configure(state="normal")

                    if suggested_field:
                        if suggested_field not in self.campos_extracao:
                            self.campos_extracao.append(suggested_field)
                            self.lst_ext_fields.insert(tk.END, suggested_field)
                            self.status_var.set(f"✨ Novo campo sugerido pelo Gemini adicionado: '{suggested_field}'")

                            # Refresh dynamic form if paper is selected
                            if self.selected_paper_index_t2 is not None:
                                paper = self.current_session['trabalhos'][self.selected_paper_index_t2]
                                self.update_dynamic_form_t2(paper)

                            msg = f"Campo sugerido adicionado com sucesso!\n\n📌 Campo: {suggested_field}"
                            if justification:
                                msg += f"\n💡 Justificativa: {justification}"
                            messagebox.showinfo("Sugestão de Campo (Gemini AI)", msg)
                        else:
                            messagebox.showinfo("Sugestão Existente", f"O Gemini sugeriu '{suggested_field}', mas este campo já está na sua lista.")
                    else:
                        messagebox.showwarning("Aviso", "Não foi possível extrair a sugestão de campo do Gemini.")

                self.after(0, update_ui)

            except Exception as e:
                def show_err(err_msg=str(e)):
                    if hasattr(self, 'btn_suggest_field_gemini'):
                        self.btn_suggest_field_gemini.configure(state="normal")
                    self.status_var.set("Erro ao sugerir campo com Gemini.")
                    messagebox.showerror("Erro Gemini AI", f"Não foi possível obter sugestão de campo:\n\n{err_msg}")
                self.after(0, show_err)

        threading.Thread(target=worker, daemon=True).start()

    def run_gemini_extracao_partner(self):
        if self.selected_paper_index_t2 is None:
            messagebox.showwarning("Aviso", "Selecione um trabalho na lista de extração para analisar.")
            return

        if not self._has_gemini_keys():
            messagebox.showwarning("API Key Ausente", "Nenhuma chave de API configurada. Adicione pelo menos uma na aba 'Configuração Geral'.")
            self.notebook.select(self.tab_general)
            return

        paper = self.current_session['trabalhos'][self.selected_paper_index_t2]
        ext = paper.get('Extracao', {})

        protocol_info = {
            "nome_revisao": self.ent_project_name.get().strip() if hasattr(self, 'ent_project_name') else "",
            "campos_extracao": self.campos_extracao
        }

        raw_pdf_text = ext.get("texto_extraido", "")
        clean_pdf_text = sanitize_text(raw_pdf_text)[:25000]

        study_info = {
            "id": paper.get("id", ""),
            "titulo": sanitize_text(paper.get("Título", "")),
            "autores": sanitize_text(paper.get("Autores", "")),
            "ano": paper.get("Ano", ""),
            "resumo": sanitize_text(paper.get("Resumo", "")),
            "texto_extraido_pdf": clean_pdf_text
        }

        if hasattr(self, 'btn_gemini_t2'):
            self.btn_gemini_t2.configure(state="disabled")
        if hasattr(self, 'btn_gemini_pdf_t2'):
            self.btn_gemini_pdf_t2.configure(state="disabled")
        self.status_var.set(f"🤖 Gemini extraindo dados do estudo '{paper.get('id')}'...")

        def worker():
            try:
                prompt = f"""Você é um Assistente Especialista em Extração de Dados para Revisões Sistemáticas.
Seu papel é analisar o estudo abaixo (Resumo e Texto Completo/PDF se disponível) e extrair rigorosamente os parâmetros de interesse solicitados.

CAMPOS DE EXTRAÇÃO DESEJADOS:
{json.dumps(self.campos_extracao, ensure_ascii=False, indent=2)}

INFORMAÇÕES DO ESTUDO:
{json.dumps(study_info, ensure_ascii=False, indent=2)}

INSTRUÇÕES:
1. Para cada campo de extração solicitado, sintetize a informação exata presente no texto. Se o texto não mencionar, responda 'Não informado no texto'.
2. Defina o status da extração como 'Concluída' se as informações principais foram identificadas, ou 'Pendente' caso faltem dados essenciais.
3. No campo 'observacoes', anote observações metodológicas, limitações do estudo, viés ou destaques relevantes.

Retorne EXCLUSIVAMENTE um objeto JSON válido com a seguinte estrutura:
{{
  "respostas": {{ "Nome do Campo": "Texto extraído/sintetizado" }},
  "status_extracao": "Concluída",
  "observacoes": "Observações técnicas e limitações..."
}}
"""
                raw_text = self.call_gemini_api(prompt)
                clean_text = raw_text.strip()
                if clean_text.startswith("```"):
                    lines = clean_text.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    clean_text = "\n".join(lines).strip()

                res = json.loads(clean_text)

                def get_json_key_val(dict_data, target_key):
                    if not dict_data:
                        return None
                    if isinstance(dict_data, dict):
                        if target_key in dict_data:
                            return dict_data[target_key]
                        target_norm = target_key.strip().lower()
                        for k, v in dict_data.items():
                            if str(k).strip().lower() == target_norm:
                                return v
                        for k, v in dict_data.items():
                            k_norm = str(k).strip().lower()
                            if len(target_norm) > 4 and (target_norm in k_norm or k_norm in target_norm):
                                return v
                    elif isinstance(dict_data, list):
                        target_norm = target_key.strip().lower()
                        for item in dict_data:
                            if isinstance(item, dict):
                                k_val = item.get("campo") or item.get("nome") or item.get("field") or item.get("key")
                                v_val = item.get("resposta") or item.get("valor") or item.get("value") or item.get("text")
                                if k_val and v_val and str(k_val).strip().lower() == target_norm:
                                    return v_val
                    elif isinstance(dict_data, str):
                        return dict_data
                    return None

                def update_ui():
                    if self.selected_paper_index_t2 is not None and self.current_session['trabalhos'][self.selected_paper_index_t2]['id'] == paper['id']:
                        resp_dict = res.get('respostas') if isinstance(res, dict) else res
                        if not resp_dict:
                            resp_dict = res
                        for field, txt_widget in self.dynamic_vars_t2.get('respostas', {}).items():
                            val_f = get_json_key_val(resp_dict, field)
                            if val_f is not None:
                                txt_widget.delete("1.0", tk.END)
                                txt_widget.insert(tk.END, str(val_f))

                        status_ext = res.get('status_extracao')
                        if status_ext in ["Concluída", "Pendente"]:
                            self.dynamic_vars_t2['status_extracao'].set(status_ext)

                        obs = res.get('observacoes', '')
                        if hasattr(self, 'txt_observacoes_t2') and obs:
                            self.txt_observacoes_t2.delete("1.0", tk.END)
                            self.txt_observacoes_t2.insert(tk.END, obs)

                        self.save_current_paper_extraction()
                        self.status_var.set(f"✨ Gemini concluiu a extração para o trabalho #{paper.get('id')}.")
                        messagebox.showinfo("Parceiro de Extração Gemini", f"Extração de dados concluída para o trabalho #{paper.get('id')}!\n\nOs campos de extração e observações foram preenchidos. Revise e confirme!")

                    if hasattr(self, 'btn_gemini_t2'):
                        self.btn_gemini_t2.configure(state="normal")
                    if hasattr(self, 'btn_gemini_pdf_t2'):
                        self.btn_gemini_pdf_t2.configure(state="normal")

                self.after(0, update_ui)

            except Exception as e:
                def show_err(err_msg=str(e)):
                    if hasattr(self, 'btn_gemini_t2'):
                        self.btn_gemini_t2.configure(state="normal")
                    if hasattr(self, 'btn_gemini_pdf_t2'):
                        self.btn_gemini_pdf_t2.configure(state="normal")
                    self.status_var.set("Erro na extração do Gemini.")
                    messagebox.showerror("Erro no Parceiro de Extração", f"Falha ao consultar o Gemini AI:\n\n{err_msg}")
                self.after(0, show_err)

        threading.Thread(target=worker, daemon=True).start()


    def select_output_dir(self):
        """Browse and select target output directory, then auto-update DB and export paths for all harvesters."""
        dir_path = filedialog.askdirectory()
        if dir_path:
            # Update output dir entry
            self.ent_output_dir.delete(0, tk.END)
            self.ent_output_dir.insert(0, dir_path)
            
            # Normalize to forward slashes
            dir_path = dir_path.replace("\\", "/")
            
            # Auto-update BDTD database and Excel paths
            self.ent_bdtd_db.delete(0, tk.END)
            self.ent_bdtd_db.insert(0, f"{dir_path}/2_bdtd_metadata.db")
            self.ent_bdtd_export.delete(0, tk.END)
            self.ent_bdtd_export.insert(0, f"{dir_path}/2_bdtd_resultados.xlsx")
            
            # Auto-update SciELO database and Excel paths
            self.ent_scielo_db.delete(0, tk.END)
            self.ent_scielo_db.insert(0, f"{dir_path}/2_scielo_metadata.db")
            self.ent_scielo_export.delete(0, tk.END)
            self.ent_scielo_export.insert(0, f"{dir_path}/2_scielo_resultados.xlsx")

            # Auto-update OpenAlex database and Excel paths
            self.ent_openalex_db.delete(0, tk.END)
            self.ent_openalex_db.insert(0, f"{dir_path}/2_openalex_metadata.db")
            self.ent_openalex_export.delete(0, tk.END)
            self.ent_openalex_export.insert(0, f"{dir_path}/2_openalex_resultados.xlsx")

            # Auto-update PubMed database and Excel paths
            self.ent_pubmed_db.delete(0, tk.END)
            self.ent_pubmed_db.insert(0, f"{dir_path}/2_pubmed_metadata.db")
            self.ent_pubmed_export.delete(0, tk.END)
            self.ent_pubmed_export.insert(0, f"{dir_path}/2_pubmed_resultados.xlsx")

            # Auto-update Scopus database and Excel paths
            self.ent_scopus_db.delete(0, tk.END)
            self.ent_scopus_db.insert(0, f"{dir_path}/2_scopus_metadata.db")
            self.ent_scopus_export.delete(0, tk.END)
            self.ent_scopus_export.insert(0, f"{dir_path}/2_scopus_resultados.xlsx")
            
            self.status_var.set(f"Pasta de destino configurada: {os.path.basename(dir_path)}")

    def load_configuration(self):
        """Loads a project JSON (unified or legacy config) and populates all GUI fields."""
        file_path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if not file_path:
            return

        if self._load_unified_or_legacy(file_path):
            self.status_var.set(f"Projeto carregado de: {os.path.basename(file_path)}")
            messagebox.showinfo("Sucesso", f"Projeto carregado com sucesso!\n\nArquivo: {file_path}")

    def run_search_execution(self):
        """Validates, writes config files, and launches the selected harvesters in a real-time log window."""
        config_data = self.collect_data()
        if config_data is None:
            return
            
        run_bdtd = self.var_run_bdtd.get()
        run_scielo = self.var_run_scielo.get()
        run_openalex = self.var_run_openalex.get()
        run_pubmed = self.var_run_pubmed.get()
        run_scopus = self.var_run_scopus.get()
        
        if not any([run_bdtd, run_scielo, run_openalex, run_pubmed, run_scopus]):
            messagebox.showwarning("Aviso", "Selecione pelo menos uma fonte para executar a busca.")
            return
            
        def expand_keywords(keywords):
            expanded = []
            pat_left = re.compile(r'\(([^)]+)\)\s*AND\s*(.+)', re.IGNORECASE)
            pat_right = re.compile(r'(.+)\s*AND\s*\(([^)]+)\)', re.IGNORECASE)
            
            for kw in keywords:
                kw_strip = kw.strip()
                m_left = pat_left.match(kw_strip)
                m_right = pat_right.match(kw_strip)
                
                if m_left:
                    or_part = m_left.group(1)
                    and_part = m_left.group(2)
                    terms = re.split(r'\s+OR\s+', or_part, flags=re.IGNORECASE)
                    for t in terms:
                        expanded.append(f"{t.strip()} AND {and_part.strip()}")
                elif m_right:
                    and_part = m_right.group(1)
                    or_part = m_right.group(2)
                    terms = re.split(r'\s+OR\s+', or_part, flags=re.IGNORECASE)
                    for t in terms:
                        expanded.append(f"{and_part.strip()} AND {t.strip()}")
                else:
                    expanded.append(kw_strip)
            return expanded

        bdtd_payload = None
        scielo_payload = None
        openalex_payload = None
        pubmed_payload = None
        scopus_payload = None

        # Write config JSONs to the local folders so the python scripts read them correctly
        if run_bdtd:
            bdtd_cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bdtd_harvester", "bdtd_config.json")
            os.makedirs(os.path.dirname(bdtd_cfg_path), exist_ok=True)
            sr = config_data["systematic_review"]
            bdtd_conf = config_data["sources"]["bdtd"]
            bdtd_payload = {
                "db_path": bdtd_conf["db_path"],
                "export_path": bdtd_conf["export_path"],
                "limit": sr["global_limit"],
                "delay": sr["global_delay"],
                "search_type": bdtd_conf["search_type"],
                "sort_order": bdtd_conf["sort_order"],
                "filters": bdtd_conf["filters"],
                "scrape_details": bdtd_conf.get("scrape_details", True),
                "keywords": expand_keywords(sr["keywords"])
            }
            try:
                with open(bdtd_cfg_path, 'w', encoding='utf-8') as f:
                    json.dump(bdtd_payload, f, ensure_ascii=False, indent=4)
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao salvar configuração do BDTD:\n{e}")
                return
                
        if run_scielo:
            scielo_cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scielo_harvester", "scielo_config.json")
            os.makedirs(os.path.dirname(scielo_cfg_path), exist_ok=True)
            sr = config_data["systematic_review"]
            scielo_conf = config_data["sources"]["scielo"]
            scielo_payload = {
                "db_path": scielo_conf["db_path"],
                "export_path": scielo_conf["export_path"],
                "limit": sr["global_limit"],
                "delay": sr["global_delay"],
                "search_field": scielo_conf["search_field"],
                "keywords": expand_keywords(sr["keywords"])
            }
            try:
                with open(scielo_cfg_path, 'w', encoding='utf-8') as f:
                    json.dump(scielo_payload, f, ensure_ascii=False, indent=4)
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao salvar configuração do SciELO:\n{e}")
                return

        if run_openalex:
            openalex_cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "openalex_harvester", "openalex_config.json")
            os.makedirs(os.path.dirname(openalex_cfg_path), exist_ok=True)
            sr = config_data["systematic_review"]
            openalex_conf = config_data["sources"]["openalex"]
            openalex_payload = {
                "db_path": openalex_conf["db_path"],
                "export_path": openalex_conf["export_path"],
                "limit": sr["global_limit"],
                "delay": sr["global_delay"],
                "email": openalex_conf["email"],
                "api_key": openalex_conf["api_key"],
                "filters": openalex_conf["filters"],
                "keywords": expand_keywords(sr["keywords"])
            }
            try:
                with open(openalex_cfg_path, 'w', encoding='utf-8') as f:
                    json.dump(openalex_payload, f, ensure_ascii=False, indent=4)
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao salvar configuração do OpenAlex:\n{e}")
                return

        if run_pubmed:
            pubmed_cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pubmed_harvester", "pubmed_config.json")
            os.makedirs(os.path.dirname(pubmed_cfg_path), exist_ok=True)
            sr = config_data["systematic_review"]
            pubmed_conf = config_data["sources"]["pubmed"]
            pubmed_payload = {
                "db_path": pubmed_conf["db_path"],
                "export_path": pubmed_conf["export_path"],
                "limit": sr["global_limit"],
                "delay": sr["global_delay"],
                "api_key": pubmed_conf["api_key"],
                "keywords": expand_keywords(sr["keywords"])
            }
            try:
                with open(pubmed_cfg_path, 'w', encoding='utf-8') as f:
                    json.dump(pubmed_payload, f, ensure_ascii=False, indent=4)
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao salvar configuração do PubMed:\n{e}")
                return

        if run_scopus:
            scopus_cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scopus_harvester", "scopus_config.json")
            os.makedirs(os.path.dirname(scopus_cfg_path), exist_ok=True)
            sr = config_data["systematic_review"]
            scopus_conf = config_data["sources"]["scopus"]
            scopus_payload = {
                "db_path": scopus_conf["db_path"],
                "export_path": scopus_conf["export_path"],
                "limit": sr["global_limit"],
                "delay": sr["global_delay"],
                "api_key": scopus_conf["api_key"],
                "view": scopus_conf["view"],
                "keywords": expand_keywords(sr["keywords"])
            }
            try:
                with open(scopus_cfg_path, 'w', encoding='utf-8') as f:
                    json.dump(scopus_payload, f, ensure_ascii=False, indent=4)
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao salvar configuração do Scopus:\n{e}")
                return

        # Save overall configuration inside the output directory if defined
        out_dir = self.ent_output_dir.get().strip()
        if out_dir:
            try:
                os.makedirs(out_dir, exist_ok=True)
            except Exception as e:
                messagebox.showerror(
                    "Erro de Pasta de Saída",
                    f"Não foi possível acessar ou criar a pasta de saída:\n{out_dir}\n\n"
                    f"Isso geralmente ocorre se o caminho apontar para uma unidade (como D:) que não existe no computador.\n\n"
                    f"Por favor, clique no botão 'Selecionar...' no painel de configurações para definir uma pasta válida no seu computador (como no disco C:).\n\n"
                    f"Erro original: {e}"
                )
                return
            overall_cfg_path = os.path.join(out_dir, "1_config_busca.json")
            try:
                with open(overall_cfg_path, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, ensure_ascii=False, indent=4)
            except Exception:
                pass

        # Show execution dialog modal
        self.show_execution_window(
            run_bdtd, run_scielo, run_openalex, run_pubmed, run_scopus,
            bdtd_payload=bdtd_payload, scielo_payload=scielo_payload,
            openalex_payload=openalex_payload, pubmed_payload=pubmed_payload,
            scopus_payload=scopus_payload
        )

    def show_execution_window(self, run_bdtd, run_scielo, run_openalex, run_pubmed, run_scopus,
                              bdtd_payload=None, scielo_payload=None, openalex_payload=None,
                              pubmed_payload=None, scopus_payload=None):
        """Displays execution window and launches harvesters sequentially."""
        exec_win = tk.Toplevel(self)
        exec_win.title("Executando Coletas...")
        exec_win.geometry("750x550")
        exec_win.minsize(550, 400)
        exec_win.grab_set()
        
        frame = ttk.Frame(exec_win, padding=15)
        frame.pack(fill="both", expand=True)
        
        ttk.Label(frame, text="Log de Execução em Tempo Real", font=("Segoe UI", 12, "bold"), foreground=self.primary_color).pack(anchor="w", pady=(0, 10))
        
        # Progress area
        progress_frame = ttk.Frame(frame)
        progress_frame.pack(side="top", fill="x", pady=(0, 10))
        
        lbl_status = ttk.Label(progress_frame, text="Preparando execução...", font=("Segoe UI", 10, "bold"))
        lbl_status.pack(anchor="w", pady=(0, 5))
        
        progress_bar = ttk.Progressbar(progress_frame, orient="horizontal", mode="determinate")
        progress_bar.pack(fill="x")
        
        # Text log area
        txt_log = tk.Text(frame, wrap="word", font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4", insertbackground="white")
        txt_log.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=txt_log.yview)
        scrollbar.pack(side="right", fill="y")
        txt_log.configure(yscrollcommand=scrollbar.set)
        
        btn_frame = ttk.Frame(exec_win, padding=10)
        btn_frame.pack(fill="x")
        
        self.exec_cancelled = False
        self.active_process = None
        
        def cancel_execution():
            self.exec_cancelled = True
            if self.active_process:
                try:
                    self.active_process.terminate()
                    txt_log.configure(state="normal")
                    txt_log.insert(tk.END, "\n[AVISO] Execução cancelada pelo usuário.\n")
                    txt_log.configure(state="disabled")
                except Exception:
                    pass
            btn_cancel.configure(state="disabled")
            
        def save_log_to_file():
            content = txt_log.get("1.0", tk.END)
            if not content or not content.strip():
                messagebox.showwarning("Aviso", "O log está vazio. Não há conteúdo para salvar.")
                return
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_name = f"log_busca_{timestamp}.txt"
            initial_dir = None
            for ent_name in ['ent_bdtd_export', 'ent_scielo_export', 'ent_openalex_export']:
                if hasattr(self, ent_name):
                    ent_val = getattr(self, ent_name).get().strip()
                    if ent_val:
                        exp_dir = os.path.dirname(ent_val)
                        if exp_dir and os.path.exists(exp_dir):
                            initial_dir = exp_dir
                            break
            
            filepath = filedialog.asksaveasfilename(
                parent=exec_win,
                title="Salvar Log da Busca",
                initialdir=initial_dir,
                initialfile=default_name,
                defaultextension=".txt",
                filetypes=[("Arquivo de Texto", "*.txt"), ("Todos os Arquivos", "*.*")]
            )
            if filepath:
                try:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(content)
                    messagebox.showinfo("Sucesso", f"Log salvo com sucesso em:\n{filepath}")
                except Exception as e:
                    messagebox.showerror("Erro", f"Erro ao salvar o log:\n{str(e)}")

        btn_cancel = ttk.Button(btn_frame, text="Cancelar Busca", style="Secondary.TButton", command=cancel_execution)
        btn_cancel.pack(side="right", padx=5)
        
        btn_save_log = ttk.Button(btn_frame, text="💾 Salvar Log (.txt)", style="Secondary.TButton", command=save_log_to_file)
        btn_save_log.pack(side="left", padx=5)
        
        log_queue = queue.Queue()
        
        class QueueLogHandler(logging.Handler):
            def __init__(self, q, cancel_check):
                super().__init__()
                self.q = q
                self.cancel_check = cancel_check

            def emit(self, record):
                if self.cancel_check():
                    return
                try:
                    msg = self.format(record) + "\n"
                    self.q.put(msg)
                except Exception:
                    pass

        class StreamToQueue:
            def __init__(self, q, orig_stream, cancel_check):
                self.q = q
                self.orig_stream = orig_stream
                self.cancel_check = cancel_check

            def write(self, buf):
                if self.orig_stream:
                    try:
                        self.orig_stream.write(buf)
                        self.orig_stream.flush()
                    except Exception:
                        pass
                if self.cancel_check():
                    return
                if buf:
                    for line in buf.splitlines(True):
                        if line:
                            self.q.put(line)

            def flush(self):
                if self.orig_stream:
                    try:
                        self.orig_stream.flush()
                    except Exception:
                        pass

        def run_pipelines():
            handler = QueueLogHandler(log_queue, lambda: self.exec_cancelled)
            handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            root_logger = logging.getLogger()
            root_logger.addHandler(handler)
            orig_stdout, orig_stderr = sys.stdout, sys.stderr
            sys.stdout = StreamToQueue(log_queue, orig_stdout, lambda: self.exec_cancelled)
            sys.stderr = StreamToQueue(log_queue, orig_stderr, lambda: self.exec_cancelled)

            python_exe = sys.executable
            if getattr(sys, 'frozen', False):
                python_exe = "python"

            try:
                # Run BDTD
                if run_bdtd and not self.exec_cancelled:
                    log_queue.put(">>> Iniciando BDTD Harvester...\n")
                    if bdtd_run_harvest and bdtd_payload:
                        bdtd_run_harvest(
                            keywords=bdtd_payload["keywords"],
                            db_path=bdtd_payload["db_path"],
                            export_path=bdtd_payload["export_path"],
                            limit=bdtd_payload["limit"],
                            delay=bdtd_payload["delay"],
                            search_type=bdtd_payload["search_type"],
                            sort_order=bdtd_payload["sort_order"],
                            filters=bdtd_payload["filters"],
                            scrape_details=bdtd_payload["scrape_details"]
                        )
                    else:
                        cmd = [python_exe, "bdtd_harvester.py"]
                        cwd = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bdtd_harvester")
                        execute_command(cmd, cwd)

                # Run SciELO
                if run_scielo and not self.exec_cancelled:
                    log_queue.put("\n>>> Iniciando SciELO Harvester...\n")
                    if scielo_run_harvest and scielo_payload:
                        scielo_run_harvest(
                            keywords=scielo_payload["keywords"],
                            db_path=scielo_payload["db_path"],
                            export_path=scielo_payload["export_path"],
                            limit=scielo_payload["limit"],
                            delay=scielo_payload["delay"],
                            search_field=scielo_payload["search_field"]
                        )
                    else:
                        cmd = [python_exe, "scielo_harvester.py"]
                        cwd = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scielo_harvester")
                        execute_command(cmd, cwd)

                # Run OpenAlex
                if run_openalex and not self.exec_cancelled:
                    log_queue.put("\n>>> Iniciando OpenAlex Harvester...\n")
                    if openalex_run_harvest and openalex_payload:
                        openalex_run_harvest(openalex_payload)
                    else:
                        cmd = [python_exe, "openalex_harvester.py"]
                        cwd = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "openalex_harvester")
                        execute_command(cmd, cwd)

                # Run PubMed
                if run_pubmed and not self.exec_cancelled:
                    log_queue.put("\n>>> Iniciando PubMed Harvester...\n")
                    if pubmed_run_harvest and pubmed_payload:
                        pubmed_run_harvest(pubmed_payload)
                    else:
                        cmd = [python_exe, "pubmed_harvester.py"]
                        cwd = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pubmed_harvester")
                        execute_command(cmd, cwd)

                # Run Scopus
                if run_scopus and not self.exec_cancelled:
                    log_queue.put("\n>>> Iniciando Scopus Harvester...\n")
                    if scopus_run_harvest and scopus_payload:
                        scopus_run_harvest(scopus_payload)
                    else:
                        cmd = [python_exe, "scopus_harvester.py"]
                        cwd = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scopus_harvester")
                        execute_command(cmd, cwd)
            except Exception as e_pipe:
                log_queue.put(f"\n[ERRO] Falha durante a execução: {str(e_pipe)}\n")
            finally:
                sys.stdout = orig_stdout
                sys.stderr = orig_stderr
                root_logger.removeHandler(handler)

            if self.exec_cancelled:
                log_queue.put("\n>>> Execução cancelada.\n")
            else:
                log_queue.put("\n>>> Todas as buscas concluídas com sucesso!\n")
            log_queue.put(None)

        def execute_command(cmd, cwd):
            try:
                self.active_process = subprocess.Popen(
                    cmd, 
                    cwd=cwd, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.STDOUT, 
                    text=True, 
                    bufsize=1,
                    encoding='utf-8',
                    errors='replace'
                )
                
                for line in self.active_process.stdout:
                    if self.exec_cancelled:
                        break
                    log_queue.put(line)
                    
                self.active_process.wait()
            except Exception as e:
                log_queue.put(f"[ERRO] Falha ao iniciar harvester: {str(e)}\n")

        threading.Thread(target=run_pipelines, daemon=True).start()
        
        # Parse state variables
        total_records = [1]
        current_count = [0]
        current_harvester = ["BDTD"]
        
        re_bdtd_total = re.compile(r"Total matching on BDTD:\s*(\d+)")
        re_bdtd_saved = re.compile(r"\[SAVED\]")
        re_bdtd_new_keyword = re.compile(r"Processing keyword:")
        re_scielo_rec = re.compile(r"Processing record:\s*(\d+)\s*/\s*(\d+)")
        re_openalex_total = re.compile(r"Total matching records in OpenAlex catalog:\s*(\d+)")
        re_pubmed_total = re.compile(r"Found\s*(\d+)\s*matching PMIDs in PubMed")
        re_scopus_total = re.compile(r"Total matching records in Scopus catalog:\s*(\d+)")
        
        # Tracks the accumulated total across all BDTD keywords
        bdtd_accumulated_total = [0]
        bdtd_last_keyword_total = [0]
        
        def poll_queue():
            try:
                while True:
                    line = log_queue.get_nowait()
                    if line is None:
                        progress_bar['value'] = progress_bar['maximum']
                        if self.exec_cancelled:
                            lbl_status.configure(text="Execução Interrompida pelo Usuário.")
                        else:
                            lbl_status.configure(text="Execução Concluída com Sucesso!")

                        try:
                            auto_log_dir = None
                            for ent_name in ['ent_bdtd_export', 'ent_scielo_export', 'ent_openalex_export']:
                                if hasattr(self, ent_name):
                                    ent_val = getattr(self, ent_name).get().strip()
                                    if ent_val:
                                        d = os.path.dirname(ent_val)
                                        if d and os.path.exists(d):
                                            auto_log_dir = d
                                            break
                            if not auto_log_dir:
                                auto_log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            auto_log_path = os.path.join(auto_log_dir, f"log_execucao_{timestamp}.txt")
                            open_path = auto_log_path
                            if sys.platform.startswith('win') and len(os.path.abspath(open_path)) >= 250 and not os.path.abspath(open_path).startswith('\\\\?\\'):
                                open_path = '\\\\?\\' + os.path.abspath(open_path)
                            with open(open_path, 'w', encoding='utf-8') as f:
                                f.write(txt_log.get("1.0", tk.END))
                            txt_log.configure(state="normal")
                            txt_log.insert(tk.END, f"\n[AUTO-SALVAMENTO] Log da busca salvo automaticamente em:\n{auto_log_path}\n")
                            txt_log.see(tk.END)
                            txt_log.configure(state="disabled")
                        except Exception as e:
                            txt_log.configure(state="normal")
                            txt_log.insert(tk.END, f"\n[AVISO] Não foi possível salvar automaticamente o log ({e}).\n")
                            txt_log.see(tk.END)
                            txt_log.configure(state="disabled")

                        btn_cancel.configure(text="Fechar", command=exec_win.destroy)
                        btn_cancel.configure(style="Primary.TButton")
                        btn_cancel.configure(state="normal")
                        return
                    
                    txt_log.configure(state="normal")
                    txt_log.insert(tk.END, line)
                    txt_log.see(tk.END)
                    txt_log.configure(state="disabled")
                    
                    # Parse progress metrics from log stream
                    if "Iniciando BDTD Harvester" in line:
                        current_harvester[0] = "BDTD"
                        total_records[0] = 100
                        current_count[0] = 0
                        bdtd_accumulated_total[0] = 0
                        bdtd_last_keyword_total[0] = 0
                        progress_bar['maximum'] = 100
                        progress_bar['value'] = 0
                        lbl_status.configure(text="BDTD Harvester: Buscando registros...")
                        
                    elif "Iniciando SciELO Harvester" in line:
                        current_harvester[0] = "SciELO"
                        total_records[0] = 100
                        current_count[0] = 0
                        progress_bar['maximum'] = 100
                        progress_bar['value'] = 0
                        lbl_status.configure(text="SciELO Harvester: Buscando registros...")

                    elif "Iniciando OpenAlex Harvester" in line:
                        current_harvester[0] = "OpenAlex"
                        total_records[0] = 100
                        current_count[0] = 0
                        progress_bar['maximum'] = 100
                        progress_bar['value'] = 0
                        lbl_status.configure(text="OpenAlex Harvester: Buscando registros...")

                    elif "Iniciando PubMed Harvester" in line:
                        current_harvester[0] = "PubMed"
                        total_records[0] = 100
                        current_count[0] = 0
                        progress_bar['maximum'] = 100
                        progress_bar['value'] = 0
                        lbl_status.configure(text="PubMed Harvester: Buscando registros...")

                    elif "Iniciando Scopus Harvester" in line:
                        current_harvester[0] = "Scopus"
                        total_records[0] = 100
                        current_count[0] = 0
                        progress_bar['maximum'] = 100
                        progress_bar['value'] = 0
                        lbl_status.configure(text="Scopus Harvester: Buscando registros...")
                        
                    if current_harvester[0] == "BDTD":
                        # When a new keyword starts, accumulate the previous keyword's total
                        if re_bdtd_new_keyword.search(line):
                            bdtd_accumulated_total[0] += bdtd_last_keyword_total[0]
                            bdtd_last_keyword_total[0] = 0
                        
                        bdtd_tot_match = re_bdtd_total.search(line)
                        if bdtd_tot_match:
                            keyword_total = int(bdtd_tot_match.group(1))
                            bdtd_last_keyword_total[0] = keyword_total
                            total_records[0] = bdtd_accumulated_total[0] + keyword_total
                            progress_bar['maximum'] = total_records[0]
                            lbl_status.configure(text=f"BDTD Harvester: Encontrados {total_records[0]} trabalhos. Iniciando raspagem detalhada...")
                        
                        if re_bdtd_saved.search(line):
                            current_count[0] += 1
                            progress_bar['value'] = current_count[0]
                            percent = int((current_count[0] / total_records[0]) * 100) if total_records[0] > 0 else 0
                            lbl_status.configure(text=f"BDTD Harvester: Raspando detalhe {current_count[0]} de {total_records[0]} ({percent}%)")
                            
                    elif current_harvester[0] == "SciELO":
                        scielo_rec_match = re_scielo_rec.search(line)
                        if scielo_rec_match:
                            current_count[0] = int(scielo_rec_match.group(1))
                            total_records[0] = int(scielo_rec_match.group(2))
                            progress_bar['maximum'] = total_records[0]
                            progress_bar['value'] = current_count[0]
                            percent = int((current_count[0] / total_records[0]) * 100) if total_records[0] > 0 else 0
                            lbl_status.configure(text=f"SciELO Harvester: Coletando artigo {current_count[0]} de {total_records[0]} ({percent}%)")

                    elif current_harvester[0] == "OpenAlex":
                        openalex_tot_match = re_openalex_total.search(line)
                        if openalex_tot_match:
                            total_records[0] = int(openalex_tot_match.group(1))
                            progress_bar['maximum'] = total_records[0]
                            lbl_status.configure(text=f"OpenAlex Harvester: Encontrados {total_records[0]} trabalhos. Iniciando coleta...")
                        if re_bdtd_saved.search(line):
                            current_count[0] += 1
                            progress_bar['value'] = current_count[0]
                            percent = int((current_count[0] / total_records[0]) * 100) if total_records[0] > 0 else 0
                            lbl_status.configure(text=f"OpenAlex Harvester: Coletados {current_count[0]} de {total_records[0]} ({percent}%)")

                    elif current_harvester[0] == "PubMed":
                        pubmed_tot_match = re_pubmed_total.search(line)
                        if pubmed_tot_match:
                            total_records[0] = int(pubmed_tot_match.group(1))
                            progress_bar['maximum'] = total_records[0]
                            lbl_status.configure(text=f"PubMed Harvester: Encontrados {total_records[0]} trabalhos. Iniciando coleta...")
                        if re_bdtd_saved.search(line):
                            current_count[0] += 1
                            progress_bar['value'] = current_count[0]
                            percent = int((current_count[0] / total_records[0]) * 100) if total_records[0] > 0 else 0
                            lbl_status.configure(text=f"PubMed Harvester: Coletados {current_count[0]} de {total_records[0]} ({percent}%)")

                    elif current_harvester[0] == "Scopus":
                        scopus_tot_match = re_scopus_total.search(line)
                        if scopus_tot_match:
                            total_records[0] = int(scopus_tot_match.group(1))
                            progress_bar['maximum'] = total_records[0]
                            lbl_status.configure(text=f"Scopus Harvester: Encontrados {total_records[0]} trabalhos. Iniciando coleta...")
                        if re_bdtd_saved.search(line):
                            current_count[0] += 1
                            progress_bar['value'] = current_count[0]
                            percent = int((current_count[0] / total_records[0]) * 100) if total_records[0] > 0 else 0
                            lbl_status.configure(text=f"Scopus Harvester: Coletados {current_count[0]} de {total_records[0]} ({percent}%)")
            except queue.Empty:
                pass
            exec_win.after(100, poll_queue)
            
        exec_win.after(100, poll_queue)

    def show_export_parts_window(self):
        """Opens a modal window allowing the user to export parts of the project separately."""
        export_win = tk.Toplevel(self)
        export_win.title("Exportar Componentes do Projeto")
        export_win.geometry("550x450")
        export_win.resizable(False, False)
        export_win.transient(self)
        export_win.grab_set()

        # Center the window
        export_win.update_idletasks()
        width = export_win.winfo_width()
        height = export_win.winfo_height()
        x = (export_win.winfo_screenwidth() // 2) - (width // 2)
        y = (export_win.winfo_screenheight() // 2) - (height // 2)
        export_win.geometry(f'{width}x{height}+{x}+{y}')

        main_frame = ttk.Frame(export_win, padding=20)
        main_frame.pack(fill="both", expand=True)

        ttk.Label(
            main_frame,
            text="Exportar Componentes Individuais",
            style="Title.TLabel"
        ).pack(anchor="w", pady=(0, 5))

        ttk.Label(
            main_frame,
            text="Selecione abaixo qual parte do projeto deseja extrair do arquivo unificado:",
            style="Subtitle.TLabel"
        ).pack(anchor="w", pady=(0, 20))

        # Helper function to create a component card
        def create_component_row(parent, title, desc, btn_text, command):
            card = ttk.LabelFrame(parent, text=title, padding=10)
            card.pack(fill="x", pady=6)
            
            lbl_desc = ttk.Label(card, text=desc, font=("Segoe UI", 9), foreground="#555555")
            lbl_desc.pack(side="left", fill="both", expand=True, padx=(0, 10))
            
            btn = ttk.Button(card, text=btn_text, style="Secondary.TButton", command=command)
            btn.pack(side="right")

        # Row 1: Protocol
        create_component_row(
            main_frame,
            "1. Protocolo de Pesquisa (.json)",
            "Salva apenas o protocolo metodológico preenchido na primeira aba.",
            "Exportar Protocolo...",
            lambda: [export_win.destroy(), self.export_protocol_only()]
        )

        # Row 2: Search Config
        create_component_row(
            main_frame,
            "2. Configuração de Busca (.json)",
            "Salva as palavras-chave, limites, delay e fontes de busca habilitadas.",
            "Exportar Busca...",
            lambda: [export_win.destroy(), self.export_config_busca_only()]
        )

        # Row 3: Triage Phase 1
        create_component_row(
            main_frame,
            "3. Planilha de Triagem - Fase 1 (.xlsx/.csv)",
            "Exporta a lista completa de trabalhos com as decisões e critérios aplicados.",
            "Exportar Triagem 1...",
            lambda: [export_win.destroy(), self.export_triagem_fase1_only()]
        )

        # Row 4: Extraction Phase 2
        create_component_row(
            main_frame,
            "4. Matriz de Extração - Fase 2 (.xlsx)",
            "Exporta as respostas do formulário de extração dos trabalhos incluídos.",
            "Exportar Extração...",
            lambda: [export_win.destroy(), self.export_extraction_excel()]
        )

        # Close Button at the bottom
        btn_close = ttk.Button(main_frame, text="Fechar", style="Primary.TButton", command=export_win.destroy)
        btn_close.pack(anchor="e", pady=(20, 0))

    def export_protocol_only(self):
        """Exports the protocol metadata block as a standalone JSON file."""
        proto_data = self.collect_protocol_data()
        if not proto_data or not proto_data.get("protocol_type"):
            messagebox.showwarning("Aviso", "Não há dados de protocolo preenchidos para exportar.")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialfile="protocolo_pesquisa.json"
        )
        if not file_path:
            return

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(proto_data, f, ensure_ascii=False, indent=4)
            messagebox.showinfo("Sucesso", f"Protocolo exportado com sucesso!\n\nArquivo: {file_path}")
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível salvar o protocolo:\n{str(e)}")

    def export_config_busca_only(self):
        """Exports the search configuration block as a standalone JSON file."""
        config_data = self.collect_data()
        if not config_data:
            messagebox.showwarning("Aviso", "Não há dados de configuração de busca para exportar.")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialfile="config_busca.json"
        )
        if not file_path:
            return

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)
            messagebox.showinfo("Sucesso", f"Configuração de busca exportada com sucesso!\n\nArquivo: {file_path}")
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível salvar a configuração de busca:\n{str(e)}")

    def export_triagem_fase1_only(self):
        """Exports Phase 1 screening papers to Excel (.xlsx) or CSV (.csv)."""
        if not self.current_session.get('trabalhos'):
            messagebox.showwarning("Aviso", "Não há dados de triagem ativos para exportar.")
            return

        self.save_current_paper_decisions()

        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx"), ("CSV files", "*.csv")],
            initialfile="3_triagem_fase1_decisoes.xlsx"
        )
        if not file_path:
            return

        rows = []
        for paper in self.current_session['trabalhos']:
            row = {
                "ID": paper.get('id', ''),
                "Título": paper.get('Título', ''),
                "Autores": paper.get('Autores', ''),
                "Ano": paper.get('Ano', ''),
                "Fonte": paper.get('Fonte', ''),
                "Tipo de Pesquisa": paper.get('Tipo de Pesquisa', ''),
                "Nome do Orientador": paper.get('Nome do Orientador', ''),
                "Universidade / Editora / Revista": paper.get('Universidade / Editora / Revista', ''),
                "Resumo": paper.get('Resumo', ''),
                "Link para Download": paper.get('Link para Download', ''),
                "Decisão": paper.get('Decisao', 'Pendente'),
                "Observações": paper.get('Observacoes', '')
            }
            # Append all criteria
            for c, val in paper.get('Criterios', {}).items():
                row[f"Critério: {c}"] = "Sim" if val else "Não"
            # Append all custom questions
            for q, val in paper.get('Perguntas', {}).items():
                row[f"Pergunta: {q}"] = val
            rows.append(row)

        df = pd.DataFrame(rows)

        try:
            if file_path.lower().endswith('.csv'):
                df.to_csv(file_path, index=False, encoding='utf-8-sig')
            else:
                df.to_excel(file_path, index=False)
            messagebox.showinfo("Sucesso", f"Planilha de triagem (Fase 1) exportada com sucesso!\n\nArquivo: {file_path}")
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível salvar a planilha:\n{str(e)}")

def main():
    app = SystematicReviewApp()
    app.mainloop()

if __name__ == "__main__":
    main()
