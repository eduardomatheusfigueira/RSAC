# Pipeline de Extração e Processamento de Metadados SciELO

Este projeto implementa um pipeline de dados automatizado em Python para extração, higienização e persistência de metadados de artigos científicos da Scientific Electronic Library Online (SciELO).

O sistema foi projetado para operar em ambientes de produção, lidando com paginação automatizada, higienização de dados estruturados e garantindo integridade transacional durante a persistência em SQLite. A saída do pipeline é estruturalmente compatível com o BDTD Harvester, permitindo a consolidação de metadados de ambas as fontes em um único repositório analítico.

## Contexto Técnico

O pipeline interage diretamente com a interface de busca pública do SciELO (`search.scielo.org`), contornando a necessidade de APIs REST restritas. A abordagem utiliza raspagem HTML estruturada com BeautifulSoup, sessões HTTP persistentes com estratégias de retry automáticas e transações em lote para otimização de I/O de disco.

## Requisitos e Instalação

O projeto requer **Python 3.8+** (testado com Python 3.12.x) e as dependências listadas no `requirements.txt`.

```bash
pip install -r requirements.txt
```

Dependências principais:
- `requests` — Requisições HTTP com suporte a sessões persistentes
- `beautifulsoup4` — Parsing e extração de elementos HTML
- `pandas` — Estruturação de dados e exportação
- `openpyxl` — Geração de arquivos Excel
- `Levenshtein` — Similaridade de strings (opcional, para deduplicação avançada)

## Execução e Interface de Linha de Comando (CLI)

O script suporta execução via terminal com sobrescrita de parâmetros ou através de arquivos de configuração externos (JSON).

### Execução Padrão
Coleta registros para as palavras-chave padrão e persiste no banco SQLite local.
```bash
python scielo_harvester.py
```

### Execução com Parâmetros Customizados
```bash
python scielo_harvester.py --keywords "planejamento urbano" "causalidade" --limit 100 --delay 3.0
```

### Execução via Arquivo de Configuração
```bash
python scielo_harvester.py --config scielo_config.json
```

### Argumentos da CLI
* `--db-path`: Caminho do arquivo SQLite de destino.
* `--limit`: Limite máximo de registros a serem salvos por palavra-chave.
* `--delay`: Tempo de espera (em segundos) entre requisições de paginação.
* `--keywords`: Lista de termos de busca.
* `--export`: Caminho do arquivo de saída (suporta `.xlsx`, `.csv`, `.json`).
* `--config`: Caminho para arquivo de configuração JSON.
* `--search-field`: Campo de busca específico do SciELO (vazio = todos os campos).

## Configuração via Arquivo Externo

O pipeline suporta configuração declarativa via arquivo JSON. Se o argumento `--config` não for fornecido, o script buscará automaticamente por `scielo_config.json` no diretório atual. Caso não exista, o template será gerado automaticamente.

### Configuração JSON (`scielo_config.json`)

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

## Arquitetura e Otimizações de Performance

O pipeline foi projetado para suportar alto volume de dados com eficiência computacional e de rede:

* **Gerenciamento de Sessão com Retries Automáticos:** Utiliza `urllib3.util.retry.Retry` acoplado ao `HTTPAdapter` para lidar automaticamente com falhas de conexão, timeouts e erros HTTP 429/5xx, aplicando backoff exponencial nativo.
* **Conexões Persistentes (Keep-Alive):** A sessão HTTP é inicializada com uma visita à página inicial do SciELO para aquisição de cookies, reutilizando conexões TCP e reduzindo significativamente a latência de rede.
* **Transações em Lote (Batch UPSERT):** A persistência no SQLite utiliza `executemany` com a cláusula nativa `ON CONFLICT DO UPDATE`. Isso evita o *fsync* de disco a cada registro e atualiza metadados incompletos em execuções subsequentes, sem gerar duplicatas.
* **Exportação em Blocos (Chunking):** A exportação para CSV é realizada através de iteração por blocos (`chunksize=50000`) via Pandas, prevenindo estouro de memória (OOM) ao processar bancos de dados com centenas de milhares de registros.
* **Expressões Regulares Pré-compiladas:** Padrões complexos de extração (ano, DOI, total de hits) são compilados no escopo do módulo, otimizando o uso de CPU durante o parsing de HTML.
* **Modo WAL (Write-Ahead Logging):** O SQLite é configurado com `PRAGMA journal_mode=WAL` para permitir leituras concorrentes durante a escrita, melhorando a performance em ambientes de produção.

## Higienização e Tratamento de Dados

Os dados brutos retornados pelo SciELO frequentemente contêm inconsistências estruturais. O pipeline aplica as seguintes regras de saneamento:

1. **Extração de Identificadores:** O ID do artigo é extraído do atributo `id` do elemento HTML, garantindo unicidade para desduplicação.
2. **Limpeza de Títulos:** Remove prefixos como `[SciELO Preprints] - ` para normalização.
3. **Consolidação de Autores:** Unifica múltiplos autores em uma única string separada por ponto e vírgula.
4. **Extração de Ano:** Utiliza heurísticas de fallback, extraindo o ano do ID do artigo (padrão SciELO) ou buscando padrões de 4 dígitos no texto da fonte.
5. **Classificação de Tipo:** Identifica automaticamente se o registro é um artigo publicado ou um preprint com base no ID.
6. **Higienização de Resumo:** Prioriza o resumo em português quando disponível, removendo o prefixo "Resumo" para entregar apenas o texto limpo.
7. **Extração de DOI:** Utiliza regex para extrair apenas o identificador DOI puro (ex: `10.1590/1413-81232023282.10222022`), ignorando textos auxiliares.

## Estrutura do Banco de Dados (SQLite)

Os dados são persistidos na tabela `article_metadata`.

| Campo | Tipo SQL | Descrição |
| :--- | :--- | :--- |
| `id` | `TEXT PRIMARY KEY` | Identificador único do artigo no SciELO. |
| `title` | `TEXT` | Título completo do artigo. |
| `authors` | `TEXT` | Autores separados por ponto e vírgula. |
| `year` | `TEXT` | Ano de publicação. |
| `type_of_research` | `TEXT` | Tipologia do trabalho (Artigo, Preprint). |
| `journal` | `TEXT` | Nome do periódico de publicação. |
| `abstract` | `TEXT` | Resumo em português (quando disponível). |
| `doi` | `TEXT` | Identificador DOI do artigo. |
| `article_url` | `TEXT` | URL de acesso ao artigo no SciELO. |
| `keyword_query` | `TEXT` | Palavra-chave que originou a coleta. |
| `harvested_at` | `TIMESTAMP` | Data/hora da extração (padrão: `CURRENT_TIMESTAMP`). |

## Compatibilidade de Saída

A exportação para Excel/CSV/JSON gera colunas estruturalmente compatíveis com o BDTD Harvester, permitindo consolidação direta:

| Coluna BDTD | Coluna SciELO | Descrição |
| :--- | :--- | :--- |
| Autores | Autores | Nomes dos autores |
| Título | Título | Título do trabalho |
| Ano | Ano | Ano de publicação |
| Tipo de Pesquisa | Tipo de Pesquisa | Tipologia (Artigo, Preprint, Tese, etc.) |
| Nome do Orientador | N/A (artigo) | Campo vazio para artigos |
| Universidade / Editora / Revista | Universidade / Editora / Revista | Periódico ou instituição |
| Resumo | Resumo | Texto do resumo |
| Link para Download | Link para Download | URL de acesso ao texto completo |

## Uso Programático (API Python)

O pipeline expõe uma função de alto nível para integração com outros sistemas:

```python
from scielo_harvester import run_harvest

success = run_harvest(
    keywords=["planejamento urbano", "causalidade"],
    db_path="minha_pesquisa.db",
    export_path="resultados.xlsx",
    limit=100,
    delay=3.0,
    search_field=""
)
```

**Parâmetros:**
* `keywords` (List[str]): Lista de termos de busca.
* `db_path` (str): Caminho do arquivo SQLite.
* `export_path` (str): Caminho do arquivo de saída.
* `limit` (Optional[int]): Limite de registros por palavra-chave.
* `delay` (float): Atraso entre requisições em segundos.
* `search_field` (str): Campo de busca específico do SciELO.

**Retorna:** `True` se a execução foi bem-sucedida, `False` caso contrário.

## Resiliência e Ética no Acesso

* **Retry Automático com Backoff Exponencial:** Em caso de oscilações na rede ou erros do servidor SciELO, o sistema realiza até 5 tentativas com tempo de espera crescente.
* **Atraso Educado (`--delay`):** Uma pausa padrão de 3 segundos é inserida entre as requisições de páginas subsequentes para evitar sobrecarga no servidor do SciELO.
* **Desduplicação Inteligente:** Utiliza a instrução SQL `INSERT ... ON CONFLICT DO UPDATE` baseada na restrição `PRIMARY KEY` da coluna `id`, assegurando que mesmo se o script for executado múltiplas vezes, o banco não conterá registros duplicados e metadados incompletos serão atualizados.
* **User-Agent Identificado:** O pipeline utiliza um User-Agent padrão de navegador moderno para evitar bloqueios automáticos, mantendo comportamento ético de raspagem.

## Limitações Conhecidas

* **Paginação Fixa:** O SciELO retorna 15 itens por página por padrão. Este valor é hardcoded no pipeline.
* **Resumos Multilíngues:** O pipeline prioriza o resumo em português. Se não disponível, utiliza o primeiro resumo encontrado (geralmente em inglês ou espanhol).
* **Artigos sem DOI:** Alguns registros podem não conter DOI. O campo será preenchido com string vazia.
* **Rate Limiting:** O SciELO pode impor limites de requisição em caso de uso excessivo. O parâmetro `--delay` deve ser ajustado conforme necessário.