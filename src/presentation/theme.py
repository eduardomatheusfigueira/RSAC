#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
ScholarReview Design System — Design Tokens e Tema Tkinter.

Implementa o estilo editorial monocromático "ScholarReview" baseado na
estética acadêmica contemporânea. Zero cores saturadas: apenas preto,
branco e tons de cinza.

Referência visual: plano de estilo.md §2-§5
"""

from dataclasses import dataclass, field
from tkinter import ttk
import tkinter as tk
from typing import Dict, Tuple


# ─── Design Tokens (imutáveis) ────────────────────────────────────────

@dataclass(frozen=True)
class DesignTokens:
    """Todos os tokens visuais imutáveis do Design System ScholarReview."""

    # ── Paleta monocromática ──────────────────────────────────────────
    paper:              str = "#FFFFFF"   # fundo de cards
    surface:            str = "#F9F9F9"   # fundo geral da janela
    surface_low:        str = "#F3F3F3"   # fundo de containers sutis
    surface_dim:        str = "#DADADA"   # divisores fortes
    border:             str = "#E5E5E5"   # bordas padrão (1px)
    outline:            str = "#7E7576"   # texto terciário, ícones inativos
    on_surface_variant: str = "#4C4546"   # texto secundário (subtítulos)
    on_surface:         str = "#1A1C1C"   # texto primário (corpo)
    primary:            str = "#000000"   # preto puro — ações primárias
    on_primary:         str = "#FFFFFF"   # texto sobre preto

    # ── Estados semânticos (EXTREMA PARCIMÔNIA) ──────────────────────
    success_subtle:     str = "#F0F5F0"   # fundo de sucesso
    error_subtle:       str = "#FFF4F3"   # fundo de erro
    warning_subtle:     str = "#FDF8EE"   # fundo de aviso

    # ── Interação ────────────────────────────────────────────────────
    selection:          str = "#EFEFEF"   # hover/selected em listas
    focus_ring:         str = "#000000"   # anel de foco (1px offset)

    # ── Espaçamentos (múltiplos de 4) ────────────────────────────────
    space_xs:  int = 4
    space_sm:  int = 8
    space_md:  int = 16
    space_lg:  int = 24
    space_xl:  int = 32
    space_2xl: int = 48

    # ── Bordas ───────────────────────────────────────────────────────
    radius:       int = 2    # quase reto (0.125rem)
    border_width: int = 1


# ─── Paleta como dicionário (acesso por string) ──────────────────────

PALETTE: Dict[str, str] = {
    "paper_white":    "#FFFFFF",
    "surface":        "#F9F9F9",
    "surface_low":    "#F3F3F3",
    "surface_dim":    "#DADADA",
    "border":         "#E5E5E5",
    "outline":        "#7E7576",
    "on_surface_v":   "#4C4546",
    "on_surface":     "#1A1C1C",
    "primary":        "#000000",
    "on_primary":     "#FFFFFF",
    "success_subtle": "#F0F5F0",
    "error_subtle":   "#FFF4F3",
    "warning_subtle": "#FDF8EE",
    "selection":      "#EFEFEF",
    "focus_ring":     "#000000",
}


# ─── Font Stacks Cross-Platform ──────────────────────────────────────

FONT_STACKS = {
    "display": ("EB Garamond", "Cormorant Garamond", "Libre Caslon Text",
                "Georgia", "Times New Roman"),
    "body":    ("Inter", "Segoe UI", "Helvetica Neue", "SF Pro Text",
                "Roboto", "Ubuntu"),
    "mono":    ("JetBrains Mono", "Cascadia Code", "Consolas",
                "SF Mono", "Courier New"),
}


# ─── Escala Tipográfica ──────────────────────────────────────────────

# Mapeado para tuplas Tkinter (family, size, weight)
# `family` será resolvido em runtime por `typography.py`
TYPOGRAPHY = {
    "display_lg":  {"stack": "display", "size": 42, "weight": "normal"},
    "headline_lg": {"stack": "display", "size": 28, "weight": "normal"},
    "headline_md": {"stack": "display", "size": 22, "weight": "normal"},
    "body_lg":     {"stack": "body",    "size": 16, "weight": "normal"},
    "body_md":     {"stack": "body",    "size": 14, "weight": "normal"},
    "body_sm":     {"stack": "body",    "size": 12, "weight": "normal"},
    "label_md":    {"stack": "body",    "size": 12, "weight": "normal"},
    "label_sm":    {"stack": "body",    "size": 11, "weight": "normal"},
    "caption":     {"stack": "body",    "size": 11, "weight": "normal"},
}


# ─── Grid System ─────────────────────────────────────────────────────

GRID = {
    "columns":       12,
    "gutter":        24,
    "max_width":     1280,
    "sidebar_width": 256,
    "margins":       {"x": 48, "y": 32},
}


# ─── Material Symbols Icon Registry ─────────────────────────────────

ICONS = {
    "dashboard":       "\ue871",
    "search":          "\ue8b6",
    "database":        "\ue94c",
    "article":         "\ue94e",
    "add":             "\ue145",
    "settings":        "\ue8b8",
    "tune":            "\ue429",
    "arrow_forward":   "\ue5c8",
    "notifications":   "\ue7f4",
    "account_circle":  "\ue853",
    "auto_awesome":    "\ue65f",
    "bolt":            "\uea0b",
    "stop_circle":     "\uef71",
    "psychology":      "\uea4a",
    "save":            "\ue161",
    "open_in_new":     "\ue89e",
    "chevron_left":    "\ue5cb",
    "chevron_right":   "\ue5cc",
    "push_pin":        "\ue6c9",
    "check_circle":    "\ue86c",
    "error_outline":   "\ue001",
    "close":           "\ue5cd",
    "download":        "\uf090",
    "upload":          "\uf09b",
    "folder":          "\ue2c7",
    "description":     "\ue873",
    "edit":            "\ue3c9",
    "delete":          "\ue872",
    "refresh":         "\ue5d5",
    "help_outline":    "\ue8fd",
}


def _resolve_font_family(stack_name: str) -> str:
    """Resolve a primeira família de fonte disponível no sistema."""
    try:
        from src.presentation.typography import resolve_font_family
        return resolve_font_family(stack_name)
    except ImportError:
        # Fallback se typography.py não estiver disponível
        fallbacks = {
            "display": "Georgia",
            "body": "Segoe UI",
            "mono": "Consolas",
        }
        return fallbacks.get(stack_name, "TkDefaultFont")


def get_font(token_name: str) -> Tuple[str, int, str]:
    """Retorna tupla (family, size, weight) para um token tipográfico."""
    spec = TYPOGRAPHY.get(token_name)
    if not spec:
        return ("Segoe UI", 11, "normal")
    family = _resolve_font_family(spec["stack"])
    return (family, spec["size"], spec["weight"])


# ─── Aplicação do Tema ───────────────────────────────────────────────

def apply_theme(root: tk.Tk) -> DesignTokens:
    """
    Aplica o tema ScholarReview em toda a aplicação Tkinter.

    Configura todos os estilos ttk globalmente. Deve ser chamado
    uma vez no __init__ da janela principal.

    Returns:
        DesignTokens: instância imutável com todos os tokens.
    """
    tokens = DesignTokens()
    style = ttk.Style(root)
    style.theme_use("clam")  # base mais customizável

    # Resolve fontes disponíveis
    display_font = _resolve_font_family("display")
    body_font = _resolve_font_family("body")

    # ═══ Reset global ═══════════════════════════════════════════════
    root.configure(bg=tokens.surface)
    root.option_add("*TCombobox*Listbox.background", tokens.paper)
    root.option_add("*TCombobox*Listbox.foreground", tokens.on_surface)
    root.option_add("*TCombobox*Listbox.selectBackground", tokens.selection)
    root.option_add("*TCombobox*Listbox.selectForeground", tokens.primary)

    style.configure(".",
        background=tokens.surface,
        foreground=tokens.on_surface,
        font=(body_font, 11),
        borderwidth=0,
        focusthickness=1,
        focuscolor=tokens.primary,
    )

    # ═══ Frames ═════════════════════════════════════════════════════
    style.configure("TFrame",
        background=tokens.surface,
    )
    style.configure("Card.TFrame",
        background=tokens.paper,
        relief="solid",
        borderwidth=1,
    )

    # ═══ Labels — Display (EB Garamond) ═════════════════════════════
    style.configure("Display.TLabel",
        font=(display_font, 42),
        foreground=tokens.primary,
        background=tokens.surface,
    )
    style.configure("Headline.TLabel",
        font=(display_font, 28),
        foreground=tokens.primary,
        background=tokens.surface,
    )
    style.configure("Subhead.TLabel",
        font=(display_font, 22),
        foreground=tokens.primary,
        background=tokens.surface,
    )

    # ═══ Labels — Body (Inter) ══════════════════════════════════════
    style.configure("TLabel",
        font=(body_font, 11),
        foreground=tokens.on_surface,
        background=tokens.surface,
    )
    style.configure("Title.TLabel",
        font=(display_font, 20),
        foreground=tokens.primary,
        background=tokens.surface,
    )
    style.configure("Subtitle.TLabel",
        font=(body_font, 10),
        foreground=tokens.on_surface_variant,
        background=tokens.surface,
    )
    style.configure("Bold.TLabel",
        font=(body_font, 11, "bold"),
        foreground=tokens.on_surface,
        background=tokens.surface,
    )
    style.configure("Caption.TLabel",
        font=(body_font, 9),
        foreground=tokens.outline,
        background=tokens.surface,
    )
    style.configure("Header.TLabel",
        font=(body_font, 12, "bold"),
        foreground=tokens.primary,
        background=tokens.paper,
    )

    # Labels em contexto de Card (fundo branco)
    style.configure("Card.TLabel",
        background=tokens.paper,
        foreground=tokens.on_surface,
        font=(body_font, 11),
    )
    style.configure("CardTitle.TLabel",
        background=tokens.paper,
        foreground=tokens.primary,
        font=(display_font, 16),
    )
    style.configure("CardSubtitle.TLabel",
        background=tokens.paper,
        foreground=tokens.on_surface_variant,
        font=(body_font, 10),
    )

    # ═══ Botão Primário (preto sólido) ══════════════════════════════
    style.configure("Primary.TButton",
        font=(body_font, 11, "bold"),
        background=tokens.primary,
        foreground=tokens.on_primary,
        padding=(tokens.space_md, tokens.space_sm),
        borderwidth=0,
    )
    style.map("Primary.TButton",
        background=[("active", tokens.on_surface),
                    ("disabled", tokens.border)],
        foreground=[("disabled", tokens.outline)],
    )

    # ═══ Botão Secundário (borda fina) ══════════════════════════════
    style.configure("Secondary.TButton",
        font=(body_font, 11),
        background=tokens.surface,
        foreground=tokens.on_surface,
        padding=(tokens.space_md, tokens.space_sm),
        borderwidth=1,
    )
    style.map("Secondary.TButton",
        background=[("active", tokens.selection)],
    )

    # ═══ Botão Fantasma (ghost) ═════════════════════════════════════
    style.configure("Ghost.TButton",
        font=(body_font, 11),
        background=tokens.surface,
        foreground=tokens.on_surface,
        borderwidth=0,
        padding=(tokens.space_sm, tokens.space_xs),
    )
    style.map("Ghost.TButton",
        background=[("active", tokens.selection)],
    )

    # ═══ Entry / Combobox ═══════════════════════════════════════════
    style.configure("TEntry",
        fieldbackground=tokens.paper,
        foreground=tokens.on_surface,
        borderwidth=1,
        padding=(tokens.space_sm, tokens.space_xs),
        font=(body_font, 11),
    )
    style.map("TEntry",
        bordercolor=[("focus", tokens.primary)],
        lightcolor=[("focus", tokens.primary)],
    )

    style.configure("TCombobox",
        fieldbackground=tokens.paper,
        foreground=tokens.on_surface,
        borderwidth=1,
        padding=(tokens.space_sm, tokens.space_xs),
        font=(body_font, 11),
    )
    style.map("TCombobox",
        bordercolor=[("focus", tokens.primary)],
        fieldbackground=[("readonly", tokens.paper)],
    )

    # ═══ LabelFrame ═════════════════════════════════════════════════
    style.configure("TLabelframe",
        background=tokens.paper,
        foreground=tokens.on_surface,
        borderwidth=1,
        relief="solid",
    )
    style.configure("TLabelframe.Label",
        background=tokens.paper,
        foreground=tokens.primary,
        font=(body_font, 11, "bold"),
    )

    # ═══ Treeview (editorial) ═══════════════════════════════════════
    style.configure("Treeview",
        background=tokens.paper,
        foreground=tokens.on_surface,
        fieldbackground=tokens.paper,
        rowheight=36,
        borderwidth=0,
        font=(body_font, 11),
    )
    style.configure("Treeview.Heading",
        font=(body_font, 11, "bold"),
        background=tokens.surface,
        foreground=tokens.on_surface,
        borderwidth=0,
        relief="flat",
    )
    style.map("Treeview",
        background=[("selected", tokens.selection)],
        foreground=[("selected", tokens.primary)],
    )

    # Alias "Editorial.Treeview" para uso explícito
    style.configure("Editorial.Treeview",
        background=tokens.paper,
        foreground=tokens.on_surface,
        fieldbackground=tokens.paper,
        rowheight=36,
        borderwidth=0,
        font=(body_font, 11),
    )
    style.configure("Editorial.Treeview.Heading",
        font=(body_font, 11, "bold"),
        background=tokens.surface,
        foreground=tokens.on_surface,
        borderwidth=0,
        relief="flat",
    )
    style.map("Editorial.Treeview",
        background=[("selected", tokens.selection)],
        foreground=[("selected", tokens.primary)],
    )

    # ═══ Notebook (tabs minimalistas) ═══════════════════════════════
    style.configure("TNotebook",
        background=tokens.surface,
        borderwidth=0,
        tabmargins=[0, 0, 0, 0],
    )
    style.configure("TNotebook.Tab",
        font=(body_font, 11),
        padding=(tokens.space_md, tokens.space_sm),
        background=tokens.surface,
        foreground=tokens.on_surface_variant,
        borderwidth=0,
    )
    style.map("TNotebook.Tab",
        background=[("selected", tokens.paper)],
        foreground=[("selected", tokens.primary)],
        expand=[("selected", [0, 0, 0, 2])],
    )

    # Alias editorial
    style.configure("Editorial.TNotebook",
        background=tokens.surface,
        borderwidth=0,
    )
    style.configure("Editorial.TNotebook.Tab",
        font=(body_font, 12),
        padding=(tokens.space_md, tokens.space_sm),
        background=tokens.surface,
        foreground=tokens.on_surface_variant,
        borderwidth=0,
    )
    style.map("Editorial.TNotebook.Tab",
        background=[("selected", tokens.paper)],
        foreground=[("selected", tokens.primary)],
    )

    # ═══ Scrollbar ══════════════════════════════════════════════════
    style.configure("TScrollbar",
        background=tokens.surface,
        troughcolor=tokens.surface,
        borderwidth=0,
        arrowsize=12,
    )
    style.map("TScrollbar",
        background=[("active", tokens.surface_dim)],
    )

    # ═══ Separator ══════════════════════════════════════════════════
    style.configure("TSeparator",
        background=tokens.border,
    )

    # ═══ Progressbar ════════════════════════════════════════════════
    style.configure("TProgressbar",
        background=tokens.primary,
        troughcolor=tokens.border,
        borderwidth=0,
        thickness=4,
    )

    # ═══ Checkbutton / Radiobutton ══════════════════════════════════
    style.configure("TCheckbutton",
        background=tokens.surface,
        foreground=tokens.on_surface,
        font=(body_font, 11),
        focuscolor=tokens.primary,
    )
    style.map("TCheckbutton",
        background=[("active", tokens.selection)],
        indicatorcolor=[("selected", tokens.primary)],
    )

    style.configure("TRadiobutton",
        background=tokens.surface,
        foreground=tokens.on_surface,
        font=(body_font, 11),
        focuscolor=tokens.primary,
    )
    style.map("TRadiobutton",
        background=[("active", tokens.selection)],
        indicatorcolor=[("selected", tokens.primary)],
    )

    # ═══ PanedWindow ════════════════════════════════════════════════
    style.configure("TPanedwindow",
        background=tokens.border,
    )
    style.configure("Sash",
        sashthickness=4,
        gripcount=0,
    )

    return tokens
