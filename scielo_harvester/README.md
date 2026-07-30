# SciELO Harvester

Pipeline automatizada em Python para extração de metadados de artigos científicos da base **SciELO** (Scientific Electronic Library Online).

A planilha de saída é **compatível** com a gerada pelo BDTD Harvester, permitindo consolidar resultados de ambas as fontes.

## Instalação

```bash
pip install -r requirements.txt
```

## Uso Rápido

### Via Linha de Comando

```bash
# Busca simples
python scielo_harvester.py --keywords "planejamento urbano" --limit 50

# Busca com exportação em CSV
python scielo_harvester.py --keywords "causalidade" "inferência causal" --export resultados.csv

# Usar arquivo de configuração
python scielo_harvester.py --config scielo_config.json
```

### Via API Python (uso programático/agêntico)

```python
from scielo_harvester import run_harvest

run_harvest(
    keywords=["planejamento urbano", "causalidade"],
    db_path="minha_pesquisa.db",
    export_path="resultados.xlsx",
    limit=100,
    delay=3.0,
)
```

## Configuração via JSON

O arquivo `scielo_config.json` é gerado automaticamente na primeira execução:

```json
{
    "db_path": "scielo_metadata.db",
    "export_path": "scielo_resultados.xlsx",
    "limit": null,
    "delay": 3.0,
    "search_field": "",
    "keywords": [
        "planejamento urbano",
        "causalidade"
    ]
}
```

## Colunas da Planilha de Saída

| Coluna | Descrição | Compatível BDTD? |
|--------|-----------|:-:|
| **Autores** | Nomes dos autores do artigo | ✅ |
| **Título** | Título do artigo | ✅ |
| **Ano** | Ano de publicação | ✅ |
| **Tipo de Pesquisa** | "Artigo" ou "Preprint" | ✅ |
| **Nome do Orientador** | N/A (artigo) | ✅ |
| **Universidade / Editora / Revista** | Nome do periódico | ✅ |
| **Resumo** | Resumo em português (quando disponível) | ✅ |
| **Link para Download** | URL do artigo na SciELO | ✅ |

## Formatos de Exportação

O formato é detectado automaticamente pela extensão do arquivo:

- `.xlsx` → Excel
- `.csv` → CSV (UTF-8)
- `.json` → JSON (array de objetos)

## Parâmetros CLI

| Parâmetro | Padrão | Descrição |
|-----------|--------|-----------|
| `--keywords` | `"planejamento urbano"` | Termos de busca |
| `--db-path` | `scielo_metadata.db` | Caminho do banco SQLite |
| `--export` | `scielo_resultados.xlsx` | Arquivo de saída |
| `--limit` | `None` (todos) | Limite de registros por termo |
| `--delay` | `3.0` | Atraso entre requisições (segundos) |
| `--config` | `None` | Caminho para arquivo de configuração JSON |
| `--search-field` | `""` (todos) | Campo de busca SciELO |

## Estrutura do Banco de Dados SQLite

```sql
CREATE TABLE article_metadata (
    id TEXT PRIMARY KEY,
    title TEXT,
    authors TEXT,
    year TEXT,
    type_of_research TEXT DEFAULT 'Artigo',
    journal TEXT,
    abstract TEXT,
    doi TEXT,
    article_url TEXT,
    keyword_query TEXT,
    harvested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```
