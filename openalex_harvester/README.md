# OpenAlex Harvester

Pipeline automatizada em Python para extração de metadados de artigos científicos, livros, teses e capítulos da base **OpenAlex** (api.openalex.org).

A planilha de saída é **totalmente compatível** com a gerada pelo BDTD Harvester e SciELO Harvester, permitindo consolidar os resultados de todas as fontes sem retrabalho.

## Recursos do Harvester
- **Busca Avançada**: Suporta queries booleanas completas com operadores `AND`, `OR`, `NOT`, parênteses para agrupamento e aspas para termos exatos.
- **Páginas Infinitas (Cursor)**: Utiliza paginação baseada em cursor para evitar a limitação de 10.000 registros da API do OpenAlex.
- **Reconstrução de Resumos**: Reconstrói automaticamente o texto completo do resumo a partir do formato *Abstract Inverted Index* fornecido pelo OpenAlex.
- **Detecção de Download**: Extrai links diretos de PDF em acesso aberto priorizando as melhores fontes de acesso aberto.
- **Compatibilidade Dupla de Configurações**: Detecta automaticamente se o arquivo JSON fornecido segue a estrutura plana padrão ou o formato estruturado gerado pelo notebook de controle da revisão sistemática (`Interface_Revisao.ipynb`).
- **Resiliência**: Mecanismo de tentativas (*retries*) com atraso exponencial em caso de limites de taxa de requisição (HTTP 429) ou falhas temporárias de conexão.

## Instalação

Instale as dependências necessárias listadas em `requirements.txt`:

```bash
pip install -r requirements.txt
```

## Uso Rápido

### Via Linha de Comando (CLI)

```bash
# Busca simples
python openalex_harvester.py --keywords "planejamento urbano" --limit 50

# Busca booleana com exportação customizada e e-mail para fila de cortesia (Polite Pool)
python openalex_harvester.py --keywords "(\"inferência causal\" OR \"causal inference\") AND \"descoberta causal\"" --email seu-email@exemplo.com --limit 100 --export resultados.xlsx

# Usar arquivo de configuração JSON (flat ou estruturado do notebook)
python openalex_harvester.py --config openalex_config.json
```

### Via API Python (uso programático)

```python
from openalex_harvester import run_harvest

config = {
    "keywords": ["\"inferência causal\" AND \"planejamento urbano\""],
    "db_path": "openalex_metadata.db",
    "export_path": "openalex_resultados.xlsx",
    "limit": 100,
    "delay": 1.0,
    "email": "seu-email@exemplo.com",
    "api_key": "",
    "filters": {
        "publication_year": "2020-2026"
    },
    "user_agent": None
}

run_harvest(config)
```

## Configuração via JSON

### Formato Plano (`openalex_config.json`)
Gerado automaticamente na primeira execução se nenhum arquivo de configuração for especificado:

```json
{
    "db_path": "openalex_metadata.db",
    "export_path": "openalex_resultados.xlsx",
    "limit": null,
    "delay": 1.0,
    "email": "seu-email@exemplo.com",
    "api_key": "",
    "filters": {
        "type": "article",
        "publication_year": "2020-2026",
        "language": "pt"
    },
    "keywords": [
        "\"inferência causal\" OR \"descoberta causal\""
    ]
}
```

### Formato Estruturado do Notebook (`config_openalex.json`)
Escrito e lido automaticamente pela interface `Interface_Revisao.ipynb`:

```json
{
    "search": {
        "query": "\"Planejamento Urbano\" AND \"Causalidade\"",
        "start_year": 2020,
        "end_year": 2026,
        "filters": {
            "repository_ids": [],
            "publisher_ids": [],
            "only_open_access": false,
            "source_types": []
        }
    },
    "api": {
        "base_url": "https://api.openalex.org/works",
        "limit": 50,
        "max_retries": 5,
        "backoff_factor": 1.5,
        "politeness_delay_seconds": 1.0,
        "user_agent": "OpenAlexHarvester/1.0 (contact: seu-email@exemplo.com)"
    },
    "paths": {
        "output_dir": "openalex_outputs",
        "csv_name": "openalex_clean_data.csv",
        "json_name": "openalex_raw_backup.json",
        "excel_name": "OpenAlex_Data_Export.xlsx",
        "report_name": "openalex_summary_report.md",
        "log_name": "openalex_harvester.log"
    }
}
```

## Colunas da Planilha de Saída

| Coluna | Descrição | Origem OpenAlex |
|--------|-----------|-----------------|
| **Autores** | Nomes dos autores separados por ponto e vírgula | `authorships.author.display_name` |
| **Título** | Título do trabalho | `title` ou `display_name` |
| **Ano** | Ano de publicação | `publication_year` |
| **Tipo de Pesquisa** | Categoria do trabalho traduzida (ex: Artigo, Livro, Capítulo de Livro, Tese/Dissertação) | Mapeado de `type` |
| **Nome do Orientador** | Identificação do orientador (sempre "Não Informado") | Não disponível no OpenAlex |
| **Universidade / Editora / Revista** | Veículo de publicação ou editora | `primary_location.source.display_name` |
| **Resumo** | Resumo em texto simples reconstruído | `abstract_inverted_index` |
| **Link para Download** | Link direto de PDF ou URL de acesso do artigo | PDF em acesso aberto ou DOI |

## Estrutura do Banco de Dados SQLite (`openalex_metadata`)

```sql
CREATE TABLE openalex_metadata (
    id TEXT PRIMARY KEY,
    title TEXT,
    authors TEXT,
    year TEXT,
    type_of_research TEXT,
    advisor TEXT DEFAULT 'Não Informado',
    journal TEXT,
    abstract TEXT,
    doi TEXT,
    article_url TEXT,
    keyword_query TEXT,
    harvested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_openalex_year ON openalex_metadata (year);
```
