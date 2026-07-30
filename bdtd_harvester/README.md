# Pipeline de Extração de Metadados da BDTD (bdtd-scraper)

Este projeto implementa um pipeline de dados automatizado em Python para extrair, filtrar e armazenar metadados acadêmicos (teses e dissertações) da **Biblioteca Digital Brasileira de Teses e Dissertações (BDTD)**.

Devido à desativação temporária do servidor OAI-PMH central da BDTD (IBICT), este script utiliza a biblioteca `bdtd-scraper` para interagir diretamente com a interface de busca e coletar os registros via API REST de forma robusta e ética.

---

## 🛠️ Requisitos e Instalação

O projeto requer **Python 3.6+** (testado com Python 3.12.9) e as bibliotecas listadas no `requirements.txt`.

Devido a uma restrição de compilação da versão legada do Pandas (`pandas==2.0.3`) especificada pelo pacote `bdtd-scraper` no Python 3.12+, a instalação deve ser feita com a flag `--no-deps`, seguida da instalação manual das versões modernas e compatíveis das dependências:

```bash
# 1. Instalar o bdtd-scraper ignorando as dependências rígidas legadas
pip install git+https://github.com/AcademicAI/bdtd-scraper.git --no-deps

# 2. Instalar dependências modernas e compatíveis (incluindo as listadas no requirements.txt)
pip install pandas Levenshtein requests beautifulsoup4
```

---

## 🚀 Como Executar

O script oferece controle via CLI (Command Line Interface) para customizar a execução:

### 1. Execução Padrão (Sem limite de registros)
Coleta todos os trabalhos relacionados aos termos `"desenvolvimento regional"`, `"políticas públicas"` e `"planejamento urbano"`, salvando-os no banco `bdtd_metadata.db`:
```bash
python bdtd_harvester.py
```

### 2. Execução com Limite (Recomendado para Testes)
Limita a coleta a, por exemplo, 10 registros salvos por palavra-chave (totalizando até 30 registros):
```bash
python bdtd_harvester.py --limit 10
```

### 3. Configurando Parâmetros Adicionais
Você pode configurar o caminho do banco de dados, o atraso educado entre requisições de página e o tamanho do lote de paginação:
```bash
python bdtd_harvester.py --db-path meu_banco.db --delay 3.0 --page-size 50
```

### 4. Executando via Formulário Excel (Recomendado)
Para uma experiência amigável sem usar a linha de comando, basta abrir, editar e salvar o arquivo `bdtd_config.xlsx` gerado na pasta do projeto e executar o script:
```bash
python bdtd_harvester.py
```

---

## 📋 Formulário de Configuração Excel (`bdtd_config.xlsx`)

O script detecta automaticamente o arquivo de configuração `bdtd_config.xlsx`. Se ele não existir, o script o cria como um modelo pronto com as seguintes opções configuráveis:

*   **Configurações Gerais**:
    *   `Banco de Dados (SQLite)`: Caminho do arquivo de banco de dados SQLite.
    *   `Excel de Saída`: Caminho do arquivo da planilha final com os resultados.
    *   `Limite por Termo`: Limite de registros por termo (deixe em branco para todos).
    *   `Atraso entre requisições (segundos)`: Intervalo educado entre chamadas de paginação.
*   **Parâmetros de Busca da API BDTD**:
    *   `Tipo de Busca`: Campo em que a busca será feita (`AllFields`, `Title`, `Author`, `Subject`, `Advisor`).
    *   `Ordenação`: Critério de ordenação (`year`, `year asc`, `relevance`, `title`, `author`).
*   **Filtros de Pesquisa BDTD (Solr)**:
    *   `Filtro: Tipo de Documento`: Filtra o tipo (`doctoralThesis` para teses, `masterThesis` para dissertações, `article` para artigos).
    *   `Filtro: Instituição`: Filtra pela sigla da instituição (ex: `USP`, `UNICAMP`).
    *   `Filtro: Ano de Publicação`: Filtra por ano ou intervalo de anos (ex: `2025` ou `[2020 TO 2026]`).
    *   `Filtro: Idioma`: Filtra por sigla de idioma (ex: `por`, `eng`, `spa`).
*   **Termos de Busca**: Lista de termos/expressões booleanas a pesquisar (Coluna D).

---

## 🗄️ Estrutura do Banco de Dados (SQLite)

Os dados são salvos no banco de dados SQLite na tabela `academic_metadata` com a seguinte estrutura relacional:

| Campo | Tipo SQL | Descrição |
| :--- | :--- | :--- |
| `id` | `INTEGER PRIMARY KEY` | Chave primária autoincrementada. |
| `record_id` | `TEXT UNIQUE` | Identificador único do trabalho na BDTD (garante a desduplicação). |
| `title` | `TEXT` | Título completo da tese/dissertação. |
| `creator` | `TEXT` | Autor principal higienizado (anos de nascimento removidos). |
| `date` | `TEXT` | Ano de publicação/defesa do trabalho. |
| `description` | `TEXT` | Resumo / Abstract do trabalho acadêmico (higienizado contra advisors duplicados). |
| `subject` | `TEXT` | Palavras-chave / Assuntos do trabalho separados por ponto e vírgula. |
| `type_of_research` | `TEXT` | Tipo do trabalho traduzido (Tese, Dissertação, Artigo, etc.). |
| `advisor` | `TEXT` | Nome do orientador e banca examinadora higienizados (sem currículos Lattes/ORCID). |
| `source_institution` | `TEXT` | Nome da universidade ou periódico de publicação. |
| `download_url` | `TEXT` | Link ou URI de acesso/download do texto completo. |
| `harvested_at` | `TIMESTAMP` | Registro de data/hora da extração (padrão: `CURRENT_TIMESTAMP`). |

### Índices Criados para Otimização
*   `idx_record_id` (sobre `record_id`): Acelera a validação e desduplicação de registros.
*   `idx_date` (sobre `date`): Permite filtros temporais rápidos nas análises.

---

## 🛡️ Resiliência e Ética no Acesso
*   **Retry Automático com Backoff Exponencial:** Em caso de oscilações na rede ou erros do servidor BDTD, o script realiza até 5 tentativas com tempo de espera crescente.
*   **Atraso Educado (`--delay`):** Uma pausa padrão de 2 segundos é inserida entre as requisições de páginas subsequentes para evitar sobrecarga no servidor da BDTD.
*   **Desduplicação Inteligente:** Utiliza a instrução SQL `INSERT OR IGNORE` baseada na restrição `UNIQUE` da coluna `record_id`, assegurando que mesmo se o script for executado múltiplas vezes, o banco não conterá registros duplicados.

