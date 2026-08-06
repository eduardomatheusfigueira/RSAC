# Pipeline de Extração e Processamento de Metadados da BDTD

Este projeto implementa um pipeline de dados automatizado em Python para extração, higienização e persistência de metadados acadêmicos da Biblioteca Digital Brasileira de Teses e Dissertações (BDTD). 

O sistema foi projetado para operar em ambientes de produção, lidando com as inconsistências estruturais dos dados de origem, restrições de rede (WAF) e garantindo integridade transacional durante a persistência em SQLite.

## Contexto Técnico

Devido à instabilidade e desativação periódica do endpoint OAI-PMH central da BDTD (IBICT), este pipeline utiliza a biblioteca `bdtd-scraper` para interagir diretamente com a API REST do motor de busca VuFind. A abordagem contorna as limitações do protocolo OAI-PMH e permite a aplicação de filtros complexos e raspagem de metadados estendidos.

## Requisitos e Instalação

O projeto requer **Python 3.8+** (testado com Python 3.12.x). 

Devido a conflitos de dependências legadas no pacote `bdtd-scraper` (especificamente a exigência de `pandas==2.0.3` que é incompatível com Python 3.12+), a instalação deve ser realizada ignorando as dependências do pacote, seguida pela instalação manual das versões modernas:

```bash
# 1. Instalar o bdtd-scraper ignorando as dependências rígidas legadas
pip install git+https://github.com/AcademicAI/bdtd-scraper.git --no-deps

# 2. Instalar as dependências modernas e compatíveis
pip install pandas openpyxl requests beautifulsoup4 Levenshtein
```

## Execução e Interface de Linha de Comando (CLI)

O script suporta execução via terminal com sobrescrita de parâmetros ou através de arquivos de configuração externos (Excel ou JSON).

### Execução Padrão
Coleta registros para as palavras-chave padrão e persiste no banco SQLite local.
```bash
python bdtd_harvester.py
```

### Execução com Parâmetros Customizados
```bash
python bdtd_harvester.py --db-path producao.db --limit 500 --delay 2.5 --page-size 100
```

### Modo Rápido (Fast-Mode)
Desabilita a raspagem individual das páginas web de detalhes (scraping), extraindo apenas os dados retornados pela API REST. Útil para coletas massivas iniciais onde a velocidade é prioritária em detrimento de campos específicos (como orientadores detalhados).
```bash
python bdtd_harvester.py --fast-mode
```

### Argumentos da CLI
* `--db-path`: Caminho do arquivo SQLite de destino.
* `--limit`: Limite máximo de registros a serem salvos por palavra-chave.
* `--delay`: Tempo de espera (em segundos) entre requisições de paginação.
* `--page-size`: Quantidade de registros por página (máximo 100).
* `--keywords`: Lista de termos de busca.
* `--type`: Campo de busca (`AllFields`, `Title`, `Author`, `Subject`, `Advisor`).
* `--sort`: Critério de ordenação (`year`, `relevance`, `title`, etc.).
* `--filter`: Filtros Solr (ex: `format:masterThesis institution:USP`).
* `--fast-mode`: Ativa o modo de coleta rápida sem scraping web.
* `--config`: Caminho para arquivo de configuração externo (`.json` ou `.xlsx`).

## Configuração via Arquivo Externo

O pipeline suporta configuração declarativa via arquivos Excel (`.xlsx`) ou JSON (`.json`). Se o argumento `--config` não for fornecido, o script buscará automaticamente por `bdtd_config.json` ou `bdtd_config.xlsx` no diretório atual. Caso nenhum exista, os templates serão gerados automaticamente.

### Configuração JSON (`bdtd_config.json`)
Estrutura recomendada para integração com sistemas automatizados e validação via Pydantic (se disponível no ambiente).

```json
{
    "db_path": "bdtd_metadata.db",
    "export_path": "resultados.xlsx",
    "limit": null,
    "delay": 2.0,
    "search_type": "AllFields",
    "sort_order": "year",
    "filters": {
        "format": "masterThesis",
        "institution": "USP",
        "publishDate": "[2020 TO 2026]",
        "language": "por, eng"
    },
    "keywords": [
        "desenvolvimento regional",
        "planejamento urbano"
    ]
}
```

### Configuração Excel (`bdtd_config.xlsx`)
Interface visual contendo duas seções principais:
1. **Configurações Gerais e Filtros (Colunas A e B):** Parâmetros de conexão, limites, atrasos e filtros Solr.
2. **Termos de Busca (Coluna D):** Lista de palavras-chave ou expressões booleanas a serem processadas.

## Arquitetura e Otimizações de Performance

O pipeline foi refatorado para suportar alto volume de dados com eficiência computacional e de rede:

* **Gerenciamento de WAF e Rate-Limiting:** O servidor VuFind da BDTD impõe restrições severas (HTTP 429) para requisições com múltiplos filtros. O pipeline sanitiza os filtros, limitando o envio via API e aplicando filtros de idioma localmente (pós-processamento). Inclui lógica de *retry* com *backoff* exponencial.
* **Conexões Persistentes (Keep-Alive):** A raspagem de páginas de detalhes utiliza `requests.Session`, reutilizando conexões TCP e reduzindo significativamente a latência de rede e a sobrecarga no servidor alvo.
* **Transações em Lote (Batch UPSERT):** A persistência no SQLite utiliza `executemany` com a cláusula nativa `ON CONFLICT DO UPDATE`. Isso evita o *fsync* de disco a cada registro e atualiza metadados incompletos em execuções subsequentes, sem gerar duplicatas.
* **Exportação em Blocos (Chunking):** A exportação para CSV/Excel é realizada através de iteração por blocos (`chunksize`) via Pandas, prevenindo estouro de memória (OOM) ao processar bancos de dados com milhões de registros.
* **Expressões Regulares Pré-compiladas:** Padrões complexos de higienização (remoção de datas, links Lattes/ORCID, instituições) são compilados no escopo do módulo, otimizando o uso de CPU durante o processamento de listas massivas.

## Higienização e Tratamento de Dados

Os dados brutos retornados pela BDTD frequentemente contêm inconsistências estruturais. O pipeline aplica as seguintes regras de saneamento:

1. **Consolidação de Autores:** Unifica autores primários, secundários e corporativos, removendo sufixos de datas de nascimento/falecimento.
2. **Limpeza de Orientadores:** Remove URLs (Lattes, ORCID), departamentos institucionais e corrige metadados trocados (ex: quando o nome do orientador é inserido erroneamente no campo de resumo/descrição).
3. **Tradução de Formatos:** Normaliza as chaves de formato do VuFind para descrições padronizadas em português (Tese, Dissertação, Artigo, etc.).
4. **Resolução de Fonte:** Determina a instituição de defesa, editora ou periódico com base em heurísticas de prioridade dependendo do tipo de documento.

## Estrutura do Banco de Dados (SQLite)

Os dados são persistidos na tabela `academic_metadata`.

| Campo | Tipo SQL | Descrição |
| :--- | :--- | :--- |
| `id` | `INTEGER PRIMARY KEY` | Chave primária autoincrementada. |
| `record_id` | `TEXT UNIQUE` | Identificador único do trabalho na BDTD (índice de desduplicação). |
| `title` | `TEXT` | Título completo do trabalho. |
| `creator` | `TEXT` | Autor principal higienizado. |
| `date` | `TEXT` | Ano de publicação/defesa. |
| `description` | `TEXT` | Resumo / Abstract. |
| `subject` | `TEXT` | Palavras-chave separadas por ponto e vírgula. |
| `type_of_research` | `TEXT` | Tipologia do trabalho (Tese, Dissertação, etc.). |
| `advisor` | `TEXT` | Nome do orientador higienizado. |
| `source_institution` | `TEXT` | Instituição de defesa, editora ou periódico. |
| `download_url` | `TEXT` | URI de acesso ao texto completo. |
| `harvested_at` | `TIMESTAMP` | Data/hora da extração (padrão: `CURRENT_TIMESTAMP`). |

**Índices:**
* `idx_record_id`: Acelera a validação de unicidade e operações de UPSERT.
* `idx_date`: Otimiza consultas e filtragens temporais.