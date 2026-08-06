# Plano de Adoção do Estilo Editorial Minimalista
## Migrando a Interface do `SystematicReviewApp` para a Linguagem Visual *ScholarReview*

---

## 1. Diagnóstico Visual: O Que Estamos Adotando

O HTML de referência segue uma estética **editorial acadêmica contemporânea**, inspirada em publicações como *The New York Review of Books*, *Aeon* e sistemas de design como o do *Linear* e *Vercel*. Seus pilares são:

| Pilar | Característica |
|-------|---------------|
| **Cromática** | Monocromática estrita: preto (`#000`), branco (`#FFF`) e 7 tons de cinza. Zero cores saturadas. |
| **Tipografia** | Pareamento serif + sans-serif: **EB Garamond** (títulos/display) + **Inter** (corpo/labels). |
| **Iconografia** | Material Symbols Outlined, peso 400, tamanho consistente (18–24px). |
| **Espaçamento** | Generoso, baseado em múltiplos de 4px. Escala tipográfica clara (12/14/16/18/24/32/48px). |
| **Bordas** | Finas (1px), raio quase zero (`0.125rem` = 2px). Sem sombras (`box-shadow: none`). |
| **Hierarquia** | Peso da fonte (400 vs 600) e tamanho criam hierarquia — não cor. |
| **Interação** | Hover = sublinhado (`underline-offset-4`) ou mudança sutil de borda. Sem transformações. |

### Contrastes com o Tkinter Atual

| Elemento | Atual (Tkinter) | Alvo (ScholarReview) |
|----------|-----------------|----------------------|
| Cor primária | Azul `#1f497d` | Preto `#000000` |
| Fonte títulos | Segoe UI bold | EB Garamond 600 |
| Fonte corpo | Segoe UI 10 | Inter 400/16px |
| Cantos | Arredondados médios | Quase retos (2px) |
| Sombras | Presentes em cards | Ausentes |
| Ícones | Emojis (`✨`, `⚡`, `⚙`) | Material Symbols |
| Botões primários | Fundo azul, texto branco | Fundo preto, texto branco |

---

## 2. Princípios de Design (Guia de Estilo)

Antes de tocar no código, estabelecemos **5 princípios imutáveis** que toda decisão visual deve respeitar:

1. **Silêncio Cromático**: Cor nunca é usada para decorar. Preto comunica ação primária; cinza comunica contexto; branco é respiro.
2. **Tipografia como Arquitetura**: A hierarquia é construída 100% com tamanho + peso + família tipográfica. Nunca com cor.
3. **Ortogonalidade Suave**: Cantos em `2px` (não 0, não 8). Linhas finas de `1px` em `#E5E5E5`.
4. **Densidade Editorial**: Muito espaço em branco (padding generoso de 24–48px). Texto com `line-height` confortável (1.5).
5. **Feedback Sutil**: Hover = sublinhado com `underline-offset: 4px`. Nunca mudança brusca de cor ou tamanho.

---

## 3. Mapeamento de Paleta (Tkinter ↔ ScholarReview)

O Tkinter aceita cores hex. Abaixo, o mapeamento oficial a ser usado em **todas** as configurações de `ttk.Style`:

```python
PALETTE = {
    # Núcleo monocromático
    "paper_white":   "#FFFFFF",   # fundo de cards
    "surface":       "#F9F9F9",   # fundo geral da janela
    "surface_low":   "#F3F3F3",   # fundo de containers sutis
    "surface_dim":   "#DADADA",   # divisores fortes
    "border":        "#E5E5E5",   # bordas padrão (1px)
    "outline":       "#7E7576",   # texto terciário, ícones inativos
    "on_surface_v":  "#4C4546",   # texto secundário (subtítulos)
    "on_surface":    "#1A1C1C",   # texto primário (corpo)
    "primary":       "#000000",   # preto puro — ações primárias
    "on_primary":    "#FFFFFF",   # texto sobre preto
    
    # Estados semânticos (usados COM EXTREMA PARCIMÔNIA)
    "success_subtle": "#F0F5F0",  # fundo de sucesso (cinza-esverdeado MUITO sutil)
    "error_subtle":   "#FFF4F3",  # fundo de erro (cinza-rosado MUITO sutil)
    "warning_subtle": "#FDF8EE",  # fundo de aviso (cinza-âmbar MUITO sutil)
    
    # Interação
    "selection":     "#EFEFEF",   # hover/selected em listas
    "focus_ring":    "#000000",   # anel de foco (1px offset)
}
```

**Regra de ouro**: nenhuma cor fora desta paleta é permitida. O azul `#1f497d` atual é **proibido**.

---

## 4. Estratégia Tipográfica

### 4.1. Cross-Platform Font Stack

EB Garamond e Inter não estão instaladas por padrão em todos os SOs. Precisamos de um **stack de fallback** que preserve a estética:

```python
FONT_STACKS = {
    "display": (
        "'EB Garamond', 'Cormorant Garamond', 'Libre Caslon Text', "
        "'Georgia', 'Times New Roman', serif"
    ),
    "body": (
        "'Inter', 'Helvetica Neue', 'Segoe UI', 'SF Pro Text', "
        "'Roboto', 'Ubuntu', sans-serif"
    ),
    "mono": (
        "'JetBrains Mono', 'SF Mono', 'Cascadia Code', 'Consolas', monospace"
    ),
}
```

### 4.2. Bundling Opcional (Recomendado para distribuição)

Para garantir fidelidade 100% em produção, **embutir as fontes TTF** via `tkfont.Font(file=...)`:

```
assets/fonts/
├── EBGaramond-Regular.ttf
├── EBGaramond-SemiBold.ttf
├── Inter-Regular.ttf
└── Inter-SemiBold.ttf
```

Carregamento lazy no boot:

```python
from tkinter import font as tkfont
import os

def register_fonts():
    fonts_dir = os.path.join(BASE_DIR, "assets", "fonts")
    for ttf in os.listdir(fonts_dir):
        if ttf.endswith(".ttf"):
            tkfont.Font(family=tkfont.Font(file=os.path.join(fonts_dir, ttf)).actual("family"))
```

### 4.3. Escala Tipográfica (Mapeamento Tkinter)

| Token | Uso | Tkinter Config |
|-------|-----|----------------|
| `display-lg` | Título principal de tela | `("EB Garamond", 42, "normal")` |
| `headline-lg` | Títulos de seção/card | `("EB Garamond", 28, "normal")` |
| `headline-md` | Subtítulos de card | `("EB Garamond", 22, "normal")` |
| `body-lg` | Corpo destacado | `("Inter", 16, "normal")` |
| `body-md` | Corpo padrão | `("Inter", 14, "normal")` |
| `label-md` | Labels, botões, badges | `("Inter", 12, "normal")` com `tracking` |
| `caption` | Metadados, timestamps | `("Inter", 11, "normal")` |

**Observação crítica**: Tkinter não suporta `letter-spacing` (tracking) nem `line-height` nativamente. Mitigaremos com:
- Ajuste manual de altura de widgets multi-linha (`ScrolledText` com `spacing1`, `spacing3`)
- Para labels, usar `ttk.Label` com padding vertical calculado

---

## 5. Plano de Implementação Técnica

### 5.1. Fase 1 — Fundação do Sistema de Design (1 semana)

Criar um módulo `presentation/theme.py` centralizado:

```python
# presentation/theme.py
"""
ScholarReview Design System — implementação Tkinter.
Baseado em: https://scholarreview.design (referência HTML)
"""
from dataclasses import dataclass
from tkinter import ttk
import tkinter as tk

@dataclass(frozen=True)
class DesignTokens:
    """Todos os tokens de design imutáveis."""
    # Cores
    paper: str = "#FFFFFF"
    surface: str = "#F9F9F9"
    border: str = "#E5E5E5"
    primary: str = "#000000"
    on_primary: str = "#FFFFFF"
    on_surface: str = "#1A1C1C"
    on_surface_variant: str = "#4C4546"
    outline: str = "#7E7576"
    selection: str = "#EFEFEF"
    
    # Espaçamentos (múltiplos de 4)
    space_xs: int = 4
    space_sm: int = 8
    space_md: int = 16
    space_lg: int = 24
    space_xl: int = 32
    space_2xl: int = 48
    
    # Bordas
    radius: int = 2  # quase reto
    border_width: int = 1


def apply_theme(root: tk.Tk) -> DesignTokens:
    """Aplica o tema ScholarReview em toda a aplicação."""
    tokens = DesignTokens()
    style = ttk.Style(root)
    style.theme_use("clam")  # base mais customizável
    
    # === Reset global ===
    root.configure(bg=tokens.surface)
    style.configure(".",
        background=tokens.surface,
        foreground=tokens.on_surface,
        font=("Inter", 11),
        borderwidth=0,
        focusthickness=1,
        focuscolor=tokens.primary,
    )
    
    # === Títulos (EB Garamond) ===
    style.configure("Display.TLabel",
        font=("EB Garamond", 42),
        foreground=tokens.primary,
        background=tokens.surface,
    )
    style.configure("Headline.TLabel",
        font=("EB Garamond", 28),
        foreground=tokens.primary,
    )
    style.configure("Subhead.TLabel",
        font=("EB Garamond", 22),
        foreground=tokens.primary,
    )
    
    # === Botão primário (preto sólido, cantos quase retos) ===
    style.configure("Primary.TButton",
        font=("Inter", 12, "bold"),
        background=tokens.primary,
        foreground=tokens.on_primary,
        padding=(tokens.space_md, tokens.space_sm),
        borderwidth=0,
    )
    style.map("Primary.TButton",
        background=[("active", tokens.on_surface),
                    ("disabled", tokens.border)],
    )
    
    # === Botão fantasma (ghost) ===
    style.configure("Ghost.TButton",
        font=("Inter", 12),
        background=tokens.surface,
        foreground=tokens.on_surface,
        borderwidth=0,
    )
    style.map("Ghost.TButton",
        background=[("active", tokens.selection)],
    )
    
    # === Card (frame com borda sutil) ===
    style.configure("Card.TFrame",
        background=tokens.paper,
        relief="solid",
        borderwidth=1,
        bordercolor=tokens.border,  # requer patch custom — ver §5.2
    )
    
    # === Treeview (a peça mais importante da UI) ===
    style.configure("Editorial.Treeview",
        background=tokens.paper,
        foreground=tokens.on_surface,
        fieldbackground=tokens.paper,
        rowheight=36,
        borderwidth=0,
        font=("Inter", 11),
    )
    style.configure("Editorial.Treeview.Heading",
        font=("Inter", 11, "bold"),
        background=tokens.surface,
        foreground=tokens.on_surface,
        borderwidth=0,
        relief="flat",
    )
    style.map("Editorial.Treeview",
        background=[("selected", tokens.selection)],
        foreground=[("selected", tokens.primary)],
    )
    
    # === Notebook (tabs minimalistas) ===
    style.configure("Editorial.TNotebook",
        background=tokens.surface,
        borderwidth=0,
    )
    style.configure("Editorial.TNotebook.Tab",
        font=("Inter", 12),
        padding=(tokens.space_md, tokens.space_sm),
        background=tokens.surface,
        foreground=tokens.on_surface_variant,
        borderwidth=0,
    )
    style.map("Editorial.TNotebook.Tab",
        background=[("selected", tokens.paper)],
        foreground=[("selected", tokens.primary)],
    )
    
    return tokens
```

### 5.2. Fase 2 — Widgets Customizados (2 semanas)

Tkinter puro não renderiza bordas `bordercolor` em `ttk.Frame`. Precisamos de **widgets customizados** via `tk.Canvas` ou `tk.Frame` com pintura manual.

#### 5.2.1. Card Component (equivalente ao `<article>` do HTML)

```python
class EditorialCard(tk.Canvas):
    """Card minimalista estilo ScholarReview."""
    
    def __init__(self, parent, *, padding=24, hover=True, **kwargs):
        self.bg = kwargs.pop("bg", PALETTE["paper_white"])
        self.border_color = PALETTE["border"]
        super().__init__(parent,
            bg=self.bg, highlightthickness=1,
            highlightbackground=self.border_color,
            highlightcolor=PALETTE["primary"] if hover else self.border_color,
            **kwargs)
        self.padding = padding
        self._hover = hover
        self._inner = tk.Frame(self, bg=self.bg)
        self.create_window(padding, padding, anchor="nw", window=self._inner)
        
        if hover:
            self.bind("<Enter>", self._on_enter)
            self.bind("<Leave>", self._on_leave)
    
    @property
    def inner(self) -> tk.Frame:
        return self._inner
    
    def _on_enter(self, _):
        self.configure(highlightbackground=PALETTE["primary"])
    
    def _on_leave(self, _):
        self.configure(highlightbackground=self.border_color)
```

#### 5.2.2. Button com Ícone (Material Symbols via Unicode PUA)

Tkinter não renderiza SVG nativamente. Solução: **usar fonte Material Symbols como fonte customizada** e referir ícones por codepoint Unicode (Private Use Area).

```python
from tkinter import font as tkfont

# Após registrar MaterialSymbols-Regular.ttf
ICONS = {
    "dashboard": "\ue871",
    "search": "\ue8b6",
    "database": "\ue94c",
    "article": "\ue94e",
    "add": "\ue145",
    "settings": "\ue8b8",
    "arrow_forward": "\ue5c8",
    "notifications": "\ue7f4",
    "account_circle": "\ue853",
}

class IconButton(ttk.Button):
    def __init__(self, parent, *, icon: str, text: str, **kwargs):
        super().__init__(parent,
            text=f"{ICONS.get(icon, '')}  {text}",
            style="Ghost.TButton",
            **kwargs)
        # Configurar fonte do ícone via tkfont
```

#### 5.2.3. Badge / Chip

Equivalente ao `<span class="bg-surface-container-low ...">`:

```python
class Badge(tk.Label):
    def __init__(self, parent, text: str):
        super().__init__(parent,
            text=text,
            bg=PALETTE["surface_low"],
            fg=PALETTE["on_surface"],
            font=("Inter", 10),
            padx=8, pady=2,
            highlightthickness=1,
            highlightbackground=PALETTE["border"],
        )
```

### 5.3. Fase 3 — Migração Tela por Tela (4 semanas)

Adotamos o padrão **Strangler Fig**: uma tela por vez, mantendo o app funcional.

#### Ordem de Migração (por impacto visual)

1. **Tela 0: Splash / Boot** — primeira impressão (1 dia)
2. **Tela 1: Side Navigation** — substitui as tabs do Notebook por sidebar fixa (3 dias)
3. **Tela 2: Dashboard/Overview** — nova tela introdutória com Bento Grid (3 dias)
4. **Tela 3: Protocolo de Pesquisa** — formulário principal (5 dias)
5. **Tela 4: Configuração Geral** — substitui cards azuis por `EditorialCard` (2 dias)
6. **Tela 5: Triagem (Treeview)** — a peça mais importante; reescrever `ttk.Treeview` (5 dias)
7. **Tela 6: Extração (PDF viewer)** — redesenho do painel bipartido (4 dias)
8. **Tela 7: Modais e Diálogos** — unificar `messagebox` por diálogos customizados (3 dias)

#### Exemplo: Refatoração do Protocol Tab

**Antes** (~200 linhas de `ttk.LabelFrame` aninhados):
```python
choice_frame = ttk.LabelFrame(left_panel, text="Escolha do Protocolo", padding=10)
```

**Depois** (~40 linhas com componentes semânticos):
```python
from presentation.widgets import EditorialCard, Headline, Body, Select

with EditorialCard(left_panel, padding=24) as card:
    Headline(card.inner, "Escolha do Protocolo")
    Body(card.inner, "Selecione a metodologia que rege sua revisão sistemática.",
         variant="caption", color=PALETTE["on_surface_variant"])
    Select(card.inner,
        label="Protocolo Metodológico",
        options=PROTOCOL_OPTIONS,
        value=self.cb_protocol_type_var,
        on_change=self.on_protocol_type_changed,
    )
```

---

## 6. Iconografia: Substituição de Emojis

Os emojis atuais (`✨`, `⚡`, `🛑`, `⚙`, `🤖`, `💾`) serão **todos removidos** e substituídos por Material Symbols.

### Tabela de Substituição

| Emoji Atual | Texto | Material Symbol |
|-------------|-------|-----------------|
| `✨` (Sugerir IA) | "Sugerir com IA" | `auto_awesome` |
| `⚡` (Triar todos) | "Triar em lote" | `bolt` |
| `🛑` (Parar loop) | "Interromper" | `stop_circle` |
| `⚙` (Configurações) | "Fontes de busca" | `tune` |
| `🤖` (Parceiro IA) | "Assistente IA" | `psychology` |
| `💾` (Salvar) | "Salvar" | `save` |
| `↗` (Link externo) | "Abrir externo" | `open_in_new` |
| `←` / `→` (Navegar) | "Anterior" / "Próximo" | `chevron_left` / `chevron_right` |
| `📌` (Fixado) | "Observação" | `push_pin` |
| `✅` (Sucesso) | "Confirmado" | `check_circle` |
| `⚠️` (Aviso) | "Atenção" | `error_outline` |

**Regra**: Ícones sempre **à esquerda** do texto, com gap de `8px`, tamanho `18px`. Nunca sozinhos (sempre com label textual para acessibilidade).

---

## 7. Layout e Espaçamento

### 7.1. Grid System

Adotamos um grid de **12 colunas** com gutter fixo de `24px` (desktop) e `16px` (mobile/tablet):

```python
GRID = {
    "columns": 12,
    "gutter": 24,
    "max_width": 1280,  # container-max do HTML
    "sidebar_width": 256,  # w-64
    "margins": {"x": 48, "y": 32},
}
```

### 7.2. Substituição do `ttk.Notebook` por Sidebar Fixa

A navegação atual em abas (`Protocolo | Configuração | Triagem | Extração`) será **substituída por uma sidebar vertical permanente** à esquerda, como no HTML:

```
┌────────────────────────────────────────────────────┐
│ Sidebar (256px)  │  Main Canvas (flex-1)          │
│                  │                                 │
│ ScholarReview    │  Active Projects               │
│ ● Project Alpha  │  ┌─────────────────────────┐   │
│                  │  │ Featured Project Card   │   │
│ ● Overview       │  └─────────────────────────┘   │
│ ● Protocol       │  ┌─────────┐ ┌─────────┐       │
│ ● Search         │  │ Card 1  │ │ Card 2  │       │
│ ● Screening      │  └─────────┘ └─────────┘       │
│ ● Extraction     │                                 │
│                  │                                 │
│ ──────────────── │                                 │
│ ⚙ Settings       │                                 │
│ ? Help           │                                 │
└────────────────────────────────────────────────────┘
```

### 7.3. Bento Grid para Triagem

Substituir a `ttk.Treeview` pura por uma grade mista:
- **Cards grandes** para artigos pendentes prioritários (com abstract preview)
- **Cards compactos** para itens já triados
- **Sidebar de contexto** com critérios e perguntas do protocolo

---

## 8. Estrutura de Arquivos Proposta

```
config_app/
├── presentation/
│   ├── __init__.py
│   ├── theme.py              # DesignTokens + apply_theme()
│   ├── typography.py         # Font stacks e registro
│   ├── icons.py              # Material Symbols registry
│   ├── app_window.py         # Shell principal (sidebar + canvas)
│   ├── widgets/              # Componentes atômicos
│   │   ├── __init__.py
│   │   ├── card.py           # EditorialCard
│   │   ├── button.py         # PrimaryButton, GhostButton, IconButton
│   │   ├── badge.py          # Badge, Chip
│   │   ├── input.py          # TextField, TextArea, Select
│   │   ├── treeview.py       # EditorialTreeview (custom)
│   │   ├── sidebar.py        # NavigationRail
│   │   ├── progress.py       # ProgressBar minimalista (1px height)
│   │   ├── dialog.py         # Modal custom (substitui messagebox)
│   │   └── pdf_viewer.py     # Visualizador de PDF redesenhado
│   ├── views/                # Telas compostas
│   │   ├── __init__.py
│   │   ├── protocol_view.py
│   │   ├── search_config_view.py
│   │   ├── screening_view.py
│   │   ├── extraction_view.py
│   │   └── dashboard_view.py # Nova
│   └── viewmodels/           # Estado reativo (MVVM)
│       └── ...
├── assets/
│   └── fonts/
│       ├── EBGaramond-Regular.ttf
│       ├── EBGaramond-SemiBold.ttf
│       ├── Inter-Regular.ttf
│       ├── Inter-SemiBold.ttf
│       └── MaterialSymbolsOutlined.ttf
└── ...
```

---

## 9. Cronograma e Entregáveis

| Semana | Fase | Entregável | Critério de Aceite |
|--------|------|-----------|-------------------|
| **1** | Fundação | `theme.py` + registro de fontes + 5 widgets base | `apply_theme()` aplicável sem quebrar app atual |
| **2** | Shell | `app_window.py` com sidebar + canvas + navegação | Usuário navega entre views sem regressão |
| **3-4** | Tela Principal | `dashboard_view.py` (nova) + `protocol_view.py` | Protocolo 100% funcional com novo estilo |
| **5-6** | Core | `screening_view.py` com Treeview custom | Triagem funcional, batch IA preservado |
| **7** | Extração | `extraction_view.py` + PDF viewer redesenhado | Extração com IA Gemini preservada |
| **8** | Polimento | Modais, diálogos, animações sutis, acessibilidade | Contraste WCAG AA, navegação por teclado |

---

## 10. Riscos e Mitigações

| Risco | Probabilidade | Mitigação |
|-------|---------------|-----------|
| **Tkinter não renderiza EB Garamond em alguns Linux** | Média | Fallback para `Liberation Serif` + bundle TTF |
| **Material Symbols TUA não renderiza em macOS antigo** | Baixa | Fallback para ícones SVG rasterizados via Pillow |
| **Perda de funcionalidades durante migração** | Alta | Testes E2E com `pytest-qt` equivalentes (pyautogui + screenshots comparativos) |
| **Performance do Treeview custom (1000+ papers)** | Média | Virtualização: renderizar apenas linhas visíveis |
| **Resistência de usuários acostumados ao azul** | Baixa | Manter opção "Classic Theme" por 6 meses como toggle |

---

## 11. Critérios de Sucesso

A migração será considerada **completa** quando:

1. ✅ **Zero código hardcoded de cor** em views — tudo via `DesignTokens`.
2. ✅ **Todas as 7 telas** usam widgets de `presentation/widgets/`.
3. ✅ **Contraste WCAG AA** em todos os elementos textuais (verificado via ferramenta automatizada).
4. ✅ **Navegação por teclado** (Tab, Enter, Esc) funcional em 100% da UI.
5. ✅ **Zero emojis** no código — apenas Material Symbols.
6. ✅ **Snapshot visual** de referência aprovado por pelo menos 2 pesquisadores externos (teste de "parece acadêmico?").
7. ✅ **Bundle final** (`PyInstaller`) com < 15MB de overhead de assets.

---

## 12. Próximo Passo Imediato

**Recomendo iniciar pela Fase 1 (Fundação)**. Posso entregar, na próxima iteração:

1. `presentation/theme.py` completo com todos os tokens
2. `presentation/widgets/card.py` e `button.py` funcionais
3. Um **protótipo visual estático** da nova tela de Overview/Dashboard renderizado em Tkinter, usando o estilo ScholarReview, com dados fictícios

Este protótipo servirá como **referência visual congelada** (north star) para todas as migrações subsequentes, evitando desvios estilísticos ao longo das 8 semanas.

**Devo prosseguir com a Fase 1?**