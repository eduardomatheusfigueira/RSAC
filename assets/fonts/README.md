# Fontes do Design System ScholarReview

Este diretório contém as fontes TTF embarcadas usadas pela interface gráfica.

## Fontes Incluídas

| Arquivo | Fonte | Uso |
|---------|-------|-----|
| `EBGaramond-Variable.ttf` | EB Garamond (variable) | Títulos, headings, display |
| `Inter-Variable.ttf` | Inter (variable) | Corpo, labels, botões |
| `MaterialSymbolsOutlined.ttf` | Material Symbols Outlined | Ícones |

## Como Funciona

No boot da aplicação, `src/presentation/typography.py` chama `register_fonts()` que:

1. No Windows: registra as fontes via `ctypes.windll.gdi32.AddFontResourceExW()` como fontes privadas do processo (não instala globalmente)
2. Em outros SOs: as fontes precisam estar instaladas no sistema, ou o fallback será usado

## Fallbacks

Se as fontes customizadas não estiverem disponíveis:

- **EB Garamond** → Georgia → Times New Roman
- **Inter** → Segoe UI → Helvetica Neue → Arial
- **Material Symbols** → Fallback para texto plano (sem ícones gráficos)
