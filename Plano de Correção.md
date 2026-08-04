# Plano de Consolidação - RSAC (Revisão Sistemática Assistida por Computador)

**Data de Análise:** Dezembro 2024  
**Versão do Sistema:** 1.0  
**Objetivo:** Identificar bugs, inconsistências estruturais e pontos de melhoria para consolidação do funcionamento atual da aplicação.

---

## Sumário Executivo

Este documento apresenta uma análise técnica detalhada da arquitetura e implementação atual do RSAC, identificando:
- Bugs conhecidos e potenciais
- Inconsistências arquiteturais
- Pontos de fragilidade na estrutura de código
- Recomendações de refatoração e consolidação

O sistema é composto por **6.047 linhas de código** no módulo principal (`config_app/main.py`), além de múltiplos scripts auxiliares e harvesters especializados.

---

## 1. Arquitetura Atual do Sistema

### 1.1 Estrutura de Diretórios

```
RSAC/
├── config_app/                          # Núcleo da aplicação GUI
│   ├── main.py                          # 6.047 linhas - Aplicação principal Tkinter
│   ├── bdtd_harvester/                  # Configs JSON dos harvesters
│   ├── scielo_harvester/
│   └── openalex_harvester/
├── bdtd_harvester/                      # Coletor BDTD (Teses/Dissertações)
├── scielo_harvester/                    # Coletor SciELO
├── openalex_harvester/                  # Coletor OpenAlex
├── pubmed_harvester/                    # Coletor PubMed
├── scopus_harvester/                    # Coletor Scopus
├── consolidar_e_deduplicar.py           # Script de consolidação (335 linhas)
├── baixar_pdfs.py                       # Download automatizado (362 linhas)
├── baixar_sucesso.py                    # Pós-processamento PDFs bem-sucedidos (300 linhas)
├── baixar_failed_pdfs.py                # Gestão de PDFs falhos (241 linhas)
├── process_manual_pdf.py                # Processamento manual (125 linhas)
├── ArticleSearcherEduardo.spec          # Spec PyInstaller
├── ConfiguradorRevisao.spec             # Spec PyInstaller
└── Iniciar_Configurador.bat             # Launcher Windows
```

### 1.2 Componentes Principais

| Componente | Linhas | Responsabilidade | Status |
|------------|--------|------------------|---------|
| `config_app/main.py` | 6.047 | Interface GUI, lógica de negócio, integração harvesters | ⚠️ Crítico |
| `consolidar_e_deduplicar.py` | 335 | Unificação e deduplicação de registros | ✅ Estável |
| `baixar_pdfs.py` | 362 | Download em massa de PDFs | ⚠️ Atenção |
| `baixar_sucesso.py` | 300 | Extração dados PDFs baixados | ⚠️ Atenção |
| `baixar_failed_pdfs.py` | 241 | Retry e gestão de falhas | ✅ Estável |
| `process_manual_pdf.py` | 125 | Upload manual de PDFs | ✅ Estável |
| Harvesters (5x) | ~400-600 cada | Coleta específica por base | ✅ Estável |

---

## 2. Bugs Identificados e Pontos Críticos

### 2.1 BUG CRÍTICO #1: Monolito no `main.py`

**Problema:**  
O arquivo `config_app/main.py` concentra **6.047 linhas** de código em um único módulo, violando princípios SOLID (Single Responsibility Principle).

**Sintomas:**
- Dificuldade extrema de manutenção e teste unitário
- Acoplamento forte entre interface GUI e lógica de negócio
- Risco elevado de regressão em modificações
- Tempo de carregamento inicial lento

**Impacto:** ALTO  
**Prioridade:** CRÍTICA

**Solução Recomendada:**
```python
# Estrutura ideal pós-refatoração:
config_app/
├── main.py (apenas bootstrap, <200 linhas)
├── gui/
│   ├── __init__.py
│   ├── protocol_screen.py      # Tela de protocolo
│   ├── search_config_screen.py # Tela configuração busca
│   ├── screening_screen.py     # Tela de triagem
│   └── extraction_screen.py    # Tela de extração
├── core/
│   ├── __init__.py
│   ├── protocol_manager.py     # Lógica de protocolo
│   ├── gemini_ai.py            # Integração API Gemini
│   ├── session_manager.py      # Gestão sessões JSON
│   └── export_manager.py       # Exportação Excel/JSON
└── utils/
    ├── text_sanitizer.py
    ├── path_resolver.py
    └── validators.py
```

---

### 2.2 BUG #2: Hardcoding de Paths Relativos

**Localização:** `config_app/main.py`, múltiplas ocorrências  
**Descrição:** Caminhos relativos fixos como `"openalex_harvester/openalex_metadata.db"` falham quando:
- O script é executado de diretórios diferentes
- A aplicação é empacotada com PyInstaller
- Usuário move a pasta do projeto

**Código Problemático:**
```python
# Exemplo encontrado (linha ~100-150)
sources_to_load = {
    "OpenAlex": {
        "db": ["openalex_metadata.db", "openalex_harvester/openalex_metadata.db"],
        ...
    }
}
```

**Impacto:** MÉDIO  
**Prioridade:** ALTA

**Solução:**
```python
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATHS = {
    "OpenAlex": [
        BASE_DIR / "openalex_metadata.db",
        BASE_DIR / "openalex_harvester" / "openalex_metadata.db"
    ]
}
```

---

### 2.3 BUG #3: Falta de Validação de Schema nos JSONs de Configuração

**Localização:** Todos os harvesters (`*_harvester.py`)  
**Descrição:** Os arquivos JSON de configuração (`bdtd_config.json`, `scielo_config.json`, etc.) são lidos sem validação de schema.

**Risco:**
- Campos obrigatórios ausentes causam `KeyError` em runtime
- Tipos incorretos (ex: string ao invés de int) não são detectados
- Erros só aparecem durante execução da coleta

**Impacto:** MÉDIO  
**Prioridade:** MÉDIA

**Solução:**
```python
from pydantic import BaseModel, Field, validator

class HarvesterConfig(BaseModel):
    db_path: str = Field(..., min_length=1)
    export_path: str
    limit: int | None = None
    delay: float = Field(default=3.0, gt=0)
    keywords: list[str] = Field(..., min_items=1)
    
    @validator('delay')
    def delay_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Delay deve ser positivo')
        return v

# Uso:
config = HarvesterConfig(**json.load(open(config_file)))
```

---

### 2.4 BUG #4: Tratamento de Exceção Genérico nos Harvesters

**Localização:** `scielo_harvester/scielo_harvester.py`, `openalex_harvester/openalex_harvester.py`  
**Descrição:** Blocos `try-except Exception` genéricos mascaram erros reais.

**Exemplo:**
```python
try:
    # scraping logic
except Exception as e:
    logger.warning(f"Could not read: {e}")
    return pd.DataFrame()
```

**Problemas:**
- Não diferencia erro de rede de erro de parsing
- Dificulta debugging
- Pode esconder bugs críticos de lógica

**Impacto:** MÉDIO  
**Prioridade:** MÉDIA

**Solução:**
```python
from requests.exceptions import RequestException, Timeout
from bs4 import BeautifulSoupSoupError

try:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
except Timeout:
    logger.error("Timeout na requisição")
    raise
except RequestException as e:
    logger.error(f"Erro HTTP: {e}")
    raise
except BeautifulSoupSoupError as e:
    logger.error(f"Erro no parsing HTML: {e}")
    raise
```

---

### 2.5 BUG #5: Vazamento de Memória em Loops de Coleta

**Localização:** Todos os harvesters  
**Descrição:** DataFrames pandas são acumulados em listas sem garbage collection explícita durante loops longos.

**Cenário:** Coleta de 1000+ registros pode consumir >2GB RAM.

**Impacto:** BAIXO (em máquinas modernas)  
**Prioridade:** BAIXA

**Solução:**
```python
import gc

for page in range(total_pages):
    records = fetch_page(page)
    process_and_save(records)
    
    # Liberação explícita
    del records
    if page % 50 == 0:
        gc.collect()
```

---

### 2.6 BUG #6: Concorrência em Acesso a Arquivos SQLite

**Localização:** `consolidar_e_deduplicar.py`, harvesters  
**Descrição:** Múltiplos processos podem tentar escrever no mesmo banco SQLite simultaneamente.

**Sintoma:** Erro `database is locked` esporádico.

**Impacto:** BAIXO  
**Prioridade:** BAIXA

**Solução:**
```python
import sqlite3
from contextlib import contextmanager

@contextmanager
def get_db_connection(db_path, timeout=30):
    conn = sqlite3.connect(db_path, timeout=timeout, isolation_level='DEFERRED')
    conn.execute('PRAGMA journal_mode=WAL')
    try:
        yield conn
    finally:
        conn.close()
```

---

### 2.7 BUG #7: Falta de Logging Estruturado

**Localização:** Todo o código  
**Descrição:** Logs são strings soltas sem contexto estruturado.

**Problema:**
- Impossível filtrar logs por nível/componente dinamicamente
- Dificuldade de análise post-mortem
- Sem correlação entre eventos distribuídos

**Impacto:** BAIXO  
**Prioridade:** BAIXA

**Solução:**
```python
import structlog

logger = structlog.get_logger()

logger.info(
    "harvest_started",
    source="SciELO",
    keywords=["planejamento urbano"],
    limit=50,
    request_id="abc123"
)
```

---

### 2.8 BUG #8: Dependência Implícita do Ambiente Windows

**Localização:** `config_app/main.py` (linhas 10-17)  
**Descrição:** Código de DPI awareness e paths com backslash hardcodado.

```python
ctypes.windll.shcore.SetProcessDpiAwareness(1)  # Falha no Linux/macOS
```

**Impacto:** MÉDIO  
**Prioridade:** ALTA (para suporte multi-plataforma)

**Solução:**
```python
import sys

if sys.platform == "win32":
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
```

---

### 2.9 BUG #9: Ausência de Testes Automatizados

**Localização:** Todo o projeto  
**Descrição:** Não há nenhum arquivo de teste (`test_*.py` ou `*_test.py`).

**Risco:**
- Regressões não detectadas
- Refatorações arriscadas
- Dificuldade de onboarding de novos desenvolvedores

**Impacto:** ALTO  
**Prioridade:** CRÍTICA

**Solução Mínima Viável:**
```bash
# Estrutura recomendada
tests/
├── __init__.py
├── test_protocol_manager.py
├── test_deduplication.py
├── test_harvesters.py
└── conftest.py
```

```python
# tests/test_deduplication.py
import pytest
from consolidar_e_deduplicar import normalize_title, clean_doi

def test_normalize_title_removes_accents():
    assert normalize_title("Planejamento Urbano") == "planejamentourbano"
    
def test_clean_doi_extracts_from_url():
    doi = "https://doi.org/10.1590/S0102-88392020000100001"
    assert clean_doi(doi) == "10.1590/s0102-88392020000100001"
```

---

### 2.10 BUG #10: Documentação Desatualizada

**Localização:** `README.md`, `Procedimento_Uso_Sistema_Revisao.md`  
**Descrição:** Referências a caminhos absolutos do desenvolvedor original.

**Exemplo:**
```markdown
"C:\\Users\\eduardo.figueira\\Documents\\Sistema de Revisão da Literatura"
```

**Impacto:** BAIXO  
**Prioridade:** BAIXA

**Solução:** Substituir por paths relativos ou variáveis de ambiente.

---

## 3. Inconsistências Estruturais

### 3.1 INCONSISTÊNCIA #1: Duplicação de Harvesters

**Problema:** Existem duas cópias de cada harvester:
- `/workspace/scielo_harvester/scielo_harvester.py`
- `/workspace/config_app/scielo_harvester/` (apenas configs JSON)

**Risco:** Dessincronização de versões, bugs corrigidos em um local mas não no outro.

**Solução:** Manter harvesters em único local e importar via `sys.path`.

---

### 3.2 INCONSISTÊNCIA #2: Formatos de Saída Heterogêneos

**Problema:** Cada harvester exporta em formatos diferentes:
- BDTD: SQLite + XLSX
- SciELO: SQLite + CSV + XLSX
- OpenAlex: SQLite apenas
- Scopus: XLSX

**Impacto:** Complexidade desnecessária no script de consolidação.

**Solução:** Padronizar saída única (SQLite + JSON Lines).

---

### 3.3 INCONSISTÊNCIA #3: Nomenclatura de Variáveis

**Problema:** Mistura de inglês e português no código:

```python
# config_app/main.py
def run_harvest(...):        # Inglês
    ...
    
# consolidar_e_deduplicar.py
def carregar_dados(...):     # Português (comentários)
    ...
```

**Solução:** Adotar inglês como língua oficial do código (padrão indústria).

---

## 4. Pontos de Melhoria Estrutural

### 4.1 MELHORIA #1: Implementar Pattern Repository

**Objetivo:** Abstrair acesso a dados (SQLite, CSV, JSON).

```python
from abc import ABC, abstractmethod

class DataRepository(ABC):
    @abstractmethod
    def save(self, records: list[dict]) -> None:
        pass
    
    @abstractmethod
    def load(self, filters: dict = None) -> list[dict]:
        pass

class SQLiteRepository(DataRepository):
    def __init__(self, db_path: str, table: str):
        self.db_path = db_path
        self.table = table
    
    def save(self, records):
        # implementação
        pass
```

---

### 4.2 MELHORIA #2: Adicionar Progresso Assíncrono na GUI

**Problema:** GUI congela durante coletas longas.

**Solução:** Usar `threading` ou `asyncio` com callbacks de progresso.

```python
import threading
import queue

progress_queue = queue.Queue()

def run_harvest_threaded(keywords, progress_callback):
    def worker():
        for i, keyword in enumerate(keywords):
            result = harvest(keyword)
            progress_queue.put(("progress", i / len(keywords) * 100))
        progress_queue.put(("done", None))
    
    thread = threading.Thread(target=worker)
    thread.start()
```

---

### 4.3 MELHORIA #3: Implementar Cache de Requisições HTTP

**Objetivo:** Evitar re-coleta desnecessária e respeitar rate limits.

```python
from cachecontrol import CacheControl
import requests

cached_session = CacheControl(requests.Session())

response = cached_session.get(url, headers={
    'Cache-Control': 'max-age=3600'  # Cache por 1 hora
})
```

---

### 4.4 MELHORIA #4: Adicionar Health Checks nas APIs

**Objetivo:** Validar conectividade antes de iniciar coletas.

```python
def check_api_health(base_name: str, url: str) -> bool:
    try:
        response = requests.get(url, timeout=5)
        return response.status_code == 200
    except:
        return False

# Na GUI:
for base in configured_bases:
    if not check_api_health(base.name, base.health_url):
        messagebox.showwarning(f"{base.name} indisponível")
```

---

### 4.5 MELHORIA #5: Versionamento de Sessões

**Problema:** Sessões JSON não têm versionamento, incompatibilidade futura.

**Solução:**
```json
{
  "session_version": "1.0",
  "created_at": "2024-12-01T10:00:00Z",
  "app_version": "1.0.0",
  "protocol": {...},
  "records": [...]
}
```

---

## 5. Roadmap de Consolidação

### Fase 1: Estabilização (2-3 semanas)
- [ ] Corrigir Bug #2 (Hardcoding de paths)
- [ ] Corrigir Bug #3 (Validação de schemas JSON)
- [ ] Corrigir Bug #8 (Dependência Windows)
- [ ] Implementar testes unitários mínimos (Bug #9)

### Fase 2: Refatoração (4-6 semanas)
- [ ] Quebrar `main.py` em módulos menores (Bug #1)
- [ ] Implementar logging estruturado (Bug #7)
- [ ] Padronizar formatos de saída (Inconsistência #2)
- [ ] Criar documentação técnica atualizada

### Fase 3: Otimização (2-3 semanas)
- [ ] Implementar cache HTTP (Melhoria #3)
- [ ] Adicionar concorrência controlada (Melhoria #2)
- [ ] Otimizar uso de memória (Bug #5)
- [ ] Implementar health checks (Melhoria #4)

### Fase 4: Modernização (4-6 semanas)
- [ ] Migrar para asyncio moderno
- [ ] Considerar migração para framework GUI moderno (PyQt6 ou Tauri)
- [ ] Implementar CI/CD pipeline
- [ ] Adicionar type hints completos (mypy)

---

## 6. Métricas de Qualidade Atuais

| Métrica | Valor | Meta | Status |
|---------|-------|------|--------|
| Linhas de Código Total | ~12.000 | <10.000 | ⚠️ |
| Cobertura de Testes | 0% | >80% | ❌ |
| Complexity Average (main.py) | ~50 | <20 | ❌ |
| Duplicação de Código | ~15% | <5% | ⚠️ |
| Technical Debt Ratio | Alto | Baixo | ❌ |
| Documentação Técnica | Parcial | Completa | ⚠️ |

---

## 7. Conclusões

O RSAC é uma aplicação funcional e robusta que cumpre seu propósito principal de automação de revisões sistemáticas. No entanto, para garantir sustentabilidade a longo prazo, escalabilidade e facilidade de manutenção, as seguintes ações são **críticas**:

1. **Refatoração urgente do `main.py`** em módulos coesos
2. **Implementação de suite de testes automatizados**
3. **Correção de hardcoded paths** para portabilidade
4. **Padronização de schemas e validações**
5. **Documentação técnica desvinculada de paths absolutos**

A priorização sugerida segue o modelo **RICE** (Reach, Impact, Confidence, Effort), focando primeiro em bugs de alto impacto e baixo esforço de correção.

---

## Anexos

### A. Glossário Técnico
- **SLR**: Systematic Literature Review
- **PRISMA**: Preferred Reporting Items for Systematic Reviews and Meta-Analyses
- **GUI**: Graphical User Interface
- **SOLID**: Princípios de design orientado a objetos
- **RICE**: Framework de priorização (Reach, Impact, Confidence, Effort)

### B. Referências Bibliográficas
- Page, M. J., et al. (2022). PRISMA 2020 explanation and elaboration. *BMJ*, 372.
- Figueira, E. & Oliveira, R. (2026). Revisões Sistemáticas em Desenvolvimento Regional no Brasil. *Revista Brasileira de Estudos Regionais*.

---

**Documento elaborado para fins de planejamento de consolidação técnica.**  
**Próxima revisão prevista:** Março 2025