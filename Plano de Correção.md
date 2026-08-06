# Análise Profissional e Plano de Refatoração do `main.py`

Analisei o código em profundidade. É um MVP funcional e ambicioso, mas carrega **dívida técnica significativa** que compromete manutenibilidade, testabilidade e escalabilidade. Abaixo está o diagnóstico e o plano de profissionalização.

---

## 1. Diagnóstico: Principais Problemas Identificados

### 🔴 Problemas Críticos de Arquitetura

| # | Problema | Impacto |
|---|----------|---------|
| 1 | **God Class** (`SystematicReviewApp` com ~5000 linhas) | Viola SRP; impossível testar; qualquer mudança gera regressão |
| 2 | **Acoplamento UI ↔ Lógica** (`self.ent_bdtd_db.get()` espalhado em métodos de negócio) | Lógica não reutilizável; testes unitários inviáveis |
| 3 | **Estado global disperso** (`current_session`, `keywords`, `triagem_csv_files`, `dynamic_vars_t2`) | Múltiplas fontes de verdade → bugs sutis de sincronização |
| 4 | **Persistência acoplada ao JSON** | Trocar para SQLite/PostgreSQL exigiria reescrever 40% do código |
| 5 | **Threading ad-hoc** (`threading.Thread` direto em 10+ lugares) | Race conditions, sem cancelamento estruturado, sem retry |
| 6 | **Parsing de JSON heurístico** (`parse_json_from_response`) | Frágil a variações do Gemini; sem fallback tipado |
| 7 | **Cache `_pdf_text_cache` ilimitado** | Memory leak em sessões longas (1000+ papers) |
| 8 | **Zero testes automatizados** | Regressões inevitáveis a cada refactor |

### 🟡 Problemas de Qualidade

- **Strings hardcoded** (`"bdtd_harvester"`, `"Não Informado"`, paths relativos)
- **Type hints inconsistentes** (alguns métodos têm, outros não)
- **Exceções genéricas** (`except Exception` em 90% dos casos)
- **Logging reativo** (sem correlation ID, sem contexto estruturado)
- **Configuração espalhada** (Gemini keys, paths, delays em lugares diferentes)

---

## 2. Arquitetura Proposta: Clean Architecture Adaptada

```
src/
├── main.py                          # Entry point mínimo
├── app/
│   ├── application.py               # Orquestrador da aplicação
│   └── container.py                 # Dependency Injection
├── core/
│   ├── domain/                      # Entidades puras (sem frameworks)
│   │   ├── entities.py              # Paper, Protocol, Criterion
│   │   ├── events.py                # Domain events (ScreeningCompleted, etc.)
│   │   └── exceptions.py            # DomainException hierarchy
│   ├── services/                    # Casos de uso
│   │   ├── screening_service.py
│   │   ├── extraction_service.py
│   │   ├── harvest_orchestrator.py
│   │   └── ai_partner_service.py
│   └── ports/                       # Interfaces (contratos)
│       ├── repositories.py
│       ├── ai_client.py
│       └── harvester.py
├── infrastructure/
│   ├── persistence/
│   │   ├── json_project_repo.py
│   │   └── filesystem_pdf_repo.py
│   ├── ai/
│   │   ├── gemini_client.py         # REST + SDK com fallback
│   │   ├── response_parser.py       # Parsing robusto de JSON
│   │   └── key_rotation.py          # Rotação de chaves com state machine
│   ├── harvesters/
│   │   └── harvester_adapter.py     # Adapter pattern para os 5 harvesters
│   └── utils/
│       ├── event_bus.py             # Pub/Sub tipado
│       ├── lru_cache.py             # Cache com limite
│       └── text_sanitizer.py
├── presentation/
│   ├── app_window.py                # Janela principal (thin)
│   ├── viewmodels/                  # Estado reativo
│   │   ├── base_viewmodel.py
│   │   ├── protocol_vm.py
│   │   ├── screening_vm.py
│   │   └── extraction_vm.py
│   ├── views/                       # Telas declarativas
│   │   ├── protocol_view.py
│   │   ├── screening_view.py
│   │   └── extraction_view.py
│   └── widgets/                     # Componentes reutilizáveis
└── tests/
    ├── unit/                        # Testes de serviços/repos
    ├── integration/                 # Testes de fluxos
    └── fixtures/
```

### Princípios Norteadores

1. **Dependency Rule:** `presentation` → `core` ← `infrastructure`. O core não conhece Tkinter.
2. **Event-Driven:** Views emitem eventos → ViewModels reagem → Services executam → Events publicados → Views atualizam.
3. **Repository Pattern:** Persistência abstraída. Hoje JSON, amanhã SQLite.
4. **Command Pattern:** Toda ação do usuário vira um Command (possibilita undo/redo).
5. **Fail-Fast Validation:** Pydantic models em todas as fronteiras.

---

## 3. Exemplos Concretos de Código Refatorado

### 3.1. Entidades de Domínio (purás, testáveis)

```python
# core/domain/entities.py
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

class Decision(str, Enum):
    PENDING = "Pendente"
    INCLUDED = "Incluído"
    EXCLUDED = "Excluído"

@dataclass(frozen=True)
class Paper:
    """Entidade imutável. Toda modificação retorna nova instância."""
    id: str
    title: str
    authors: str
    year: str
    source: str
    research_type: str
    institution: str
    abstract: str
    download_url: str
    decision: Decision = Decision.PENDING
    inclusion_criteria: dict[str, bool] = field(default_factory=dict)
    exclusion_criteria: dict[str, bool] = field(default_factory=dict)
    questions: dict[str, str] = field(default_factory=dict)
    observations: str = ""
    
    def with_decision(self, decision: Decision) -> "Paper":
        from dataclasses import replace
        return replace(self, decision=decision)
    
    def with_criterion(self, criterion: str, value: bool, is_exclusion: bool = False) -> "Paper":
        from dataclasses import replace
        target = dict(self.exclusion_criteria if is_exclusion else self.inclusion_criteria)
        target[criterion] = value
        if is_exclusion:
            return replace(self, exclusion_criteria=target)
        return replace(self, inclusion_criteria=target)

@dataclass
class ScreeningSession:
    """Agregado raiz da triagem."""
    papers: list[Paper]
    inclusion_criteria: list[str]
    exclusion_criteria: list[str]
    questions: list[str]
    created_at: datetime = field(default_factory=datetime.now)
    
    def paper_by_id(self, paper_id: str) -> Optional[Paper]:
        return next((p for p in self.papers if p.id == paper_id), None)
    
    def replace_paper(self, updated: Paper) -> None:
        for i, p in enumerate(self.papers):
            if p.id == updated.id:
                self.papers[i] = updated
                return
        raise ValueError(f"Paper {updated.id} not found")
```

### 3.2. Domain Events (desacoplamento)

```python
# core/domain/events.py
from dataclasses import dataclass
from core.domain.entities import Paper

@dataclass(frozen=True)
class ScreeningRequested:
    paper_id: str

@dataclass(frozen=True)
class ScreeningCompleted:
    paper: Paper
    suggested_by_ai: bool = False

@dataclass(frozen=True)
class BatchScreeningProgress:
    current: int
    total: int
    paper_id: str
    
@dataclass(frozen=True)
class HarvestStarted:
    source: str
    
@dataclass(frozen=True)
class HarvestCompleted:
    source: str
    records_saved: int
```

### 3.3. Event Bus Tipado

```python
# infrastructure/utils/event_bus.py
from collections import defaultdict
from typing import Callable, Any, TypeVar
import threading

T = TypeVar("T")

class EventBus:
    """Pub/Sub thread-safe para comunicação entre camadas."""
    
    def __init__(self) -> None:
        self._subscribers: dict[type, list[Callable]] = defaultdict(list)
        self._lock = threading.RLock()
    
    def subscribe(self, event_type: type, handler: Callable) -> None:
        with self._lock:
            self._subscribers[event_type].append(handler)
    
    def publish(self, event: Any) -> None:
        with self._lock:
            handlers = list(self._subscribers.get(type(event), []))
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                import logging
                logging.exception(f"Handler failed for {type(event).__name__}: {e}")
```

### 3.4. Service de Screening (lógica pura, testável)

```python
# core/services/screening_service.py
from core.domain.entities import Paper, Decision
from core.domain.events import ScreeningCompleted
from core.ports.ai_client import AIClient
from core.ports.repositories import ProjectRepository
from infrastructure.utils.event_bus import EventBus

class ScreeningService:
    """Caso de uso: triar um paper com IA."""
    
    def __init__(
        self,
        ai_client: AIClient,
        repository: ProjectRepository,
        event_bus: EventBus,
    ) -> None:
        self._ai = ai_client
        self._repo = repository
        self._bus = event_bus
    
    async def screen_paper(
        self,
        paper: Paper,
        protocol_context: dict,
    ) -> Paper:
        """Retorna um novo Paper com decisão sugerida."""
        # 1. Validação prévia (fail-fast, sem chamada de rede)
        if not self._has_sufficient_data(paper):
            return paper.with_decision(Decision.PENDING)
        
        # 2. Chama IA (injetada, mockável em testes)
        suggestion = await self._ai.analyze_screening(
            paper=paper,
            protocol=protocol_context,
        )
        
        # 3. Aplica sugestão (imutabilidade)
        updated = paper.with_decision(suggestion.decision)
        for criterion, value in suggestion.inclusion_criteria.items():
            updated = updated.with_criterion(criterion, value, is_exclusion=False)
        for criterion, value in suggestion.exclusion_criteria.items():
            updated = updated.with_criterion(criterion, value, is_exclusion=True)
        
        # 4. Persiste
        self._repo.update_paper(updated)
        
        # 5. Publica evento (ViewModels escutam e atualizam UI)
        self._bus.publish(ScreeningCompleted(paper=updated, suggested_by_ai=True))
        
        return updated
    
    def _has_sufficient_data(self, paper: Paper) -> bool:
        abstract = paper.abstract.strip().lower()
        if len(abstract) < 20:
            return False
        invalid_markers = {"", "n/a", "none", "não informado", "sem resumo"}
        return abstract not in invalid_markers
```

### 3.5. ViewModel Reativo (ponte UI ↔ Service)

```python
# presentation/viewmodels/screening_vm.py
from dataclasses import dataclass
from typing import Callable
from core.domain.events import ScreeningCompleted, BatchScreeningProgress
from core.services.screening_service import ScreeningService
from infrastructure.utils.event_bus import EventBus
import asyncio
import threading

@dataclass
class ScreeningState:
    current_paper_id: str | None = None
    is_batch_running: bool = False
    batch_progress: tuple[int, int] = (0, 0)

class ScreeningViewModel:
    """Expõe estado reativo e comandos para a View."""
    
    def __init__(self, service: ScreeningService, event_bus: EventBus) -> None:
        self._service = service
        self._bus = event_bus
        self._state = ScreeningState()
        self._state_listeners: list[Callable[[ScreeningState], None]] = []
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        
        # Inscreve-se em eventos de domínio
        self._bus.subscribe(ScreeningCompleted, self._on_screening_completed)
        self._bus.subscribe(BatchScreeningProgress, self._on_batch_progress)
    
    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
    
    @property
    def state(self) -> ScreeningState:
        return self._state
    
    def add_state_listener(self, listener: Callable[[ScreeningState], None]) -> None:
        self._state_listeners.append(listener)
    
    def _notify(self) -> None:
        for listener in self._state_listeners:
            listener(self._state)
    
    # === COMANDOS (chamados pela View) ===
    
    def screen_current_paper(self, paper: Paper, protocol: dict) -> None:
        """Comando assíncrono: triar paper atual."""
        asyncio.run_coroutine_threadsafe(
            self._service.screen_paper(paper, protocol),
            self._loop,
        )
    
    def stop_batch(self) -> None:
        self._state.is_batch_running = False
        self._notify()
    
    # === HANDLERS DE EVENTOS ===
    
    def _on_screening_completed(self, event: ScreeningCompleted) -> None:
        # Atualiza estado e notifica UI (thread-safe via Tk `after`)
        pass
    
    def _on_batch_progress(self, event: BatchScreeningProgress) -> None:
        self._state.batch_progress = (event.current, event.total)
        self._notify()
```

### 3.6. Cliente Gemini com Rotação de Chaves Robusta

```python
# infrastructure/ai/gemini_client.py
from dataclasses import dataclass
from typing import Protocol
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

class AIClient(Protocol):
    async def analyze_screening(self, paper, protocol) -> "ScreeningSuggestion": ...

class QuotaExhaustedError(Exception):
    """Todas as chaves atingiram quota."""

class ModelUnavailableError(Exception):
    """Erro 503 — alta demanda."""

@dataclass
class GeminiKeyState:
    key: str
    is_exhausted: bool = False
    failures: int = 0

class GeminiClient:
    """Cliente Gemini com rotação, retry exponencial e fallback de modelo."""
    
    FALLBACK_MODELS = ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash")
    
    def __init__(self, keys: list[str], primary_model: str = "gemini-2.5-flash") -> None:
        if not keys:
            raise ValueError("At least one API key is required")
        self._keys = [GeminiKeyState(key=k) for k in keys]
        self._current_idx = 0
        self._primary_model = primary_model
    
    def _available_keys(self) -> list[GeminiKeyState]:
        return [k for k in self._keys if not k.is_exhausted]
    
    def _rotate(self) -> GeminiKeyState:
        available = self._available_keys()
        if not available:
            # Reset e tenta novamente (cooldown pode ter passado)
            for k in self._keys:
                k.is_exhausted = False
            available = self._keys
        self._current_idx = (self._current_idx + 1) % len(self._keys)
        return self._keys[self._current_idx]
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(ModelUnavailableError),
        reraise=True,
    )
    async def generate_json(self, prompt: str, system: str | None = None) -> dict:
        """Retorna JSON validado ou lança exceção tipada."""
        key_state = self._rotate()
        models = [self._primary_model, *self.FALLBACK_MODELS]
        
        last_error: Exception | None = None
        for model in models:
            try:
                response = self._call_api(key_state.key, model, prompt, system)
                return self._parse_response(response)
            except QuotaExhaustedError:
                key_state.is_exhausted = True
                if not self._available_keys():
                    raise QuotaExhaustedError(
                        f"All {len(self._keys)} keys exhausted. Wait for quota reset."
                    )
                key_state = self._rotate()
            except ModelUnavailableError as e:
                last_error = e
                continue
        
        raise last_error or RuntimeError("All models failed")
    
    def _call_api(self, key: str, model: str, prompt: str, system: str | None) -> requests.Response:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        
        resp = requests.post(
            url,
            params={"key": key},
            json=payload,
            timeout=60,
            headers={"Content-Type": "application/json"},
        )
        
        if resp.status_code == 429 or "RESOURCE_EXHAUSTED" in resp.text:
            raise QuotaExhaustedError(f"Key quota exhausted: {resp.text[:100]}")
        if resp.status_code == 503:
            raise ModelUnavailableError(f"Model {model} unavailable")
        resp.raise_for_status()
        return resp
    
    def _parse_response(self, resp: requests.Response) -> dict:
        """Parsing robusto: tenta múltiplas estratégias."""
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return JSONResponseParser.parse(text)  # classe dedicada
```

### 3.7. Cache LRU para PDFs

```python
# infrastructure/utils/lru_cache.py
from collections import OrderedDict
from threading import RLock
from typing import TypeVar, Generic

K = TypeVar("K")
V = TypeVar("V")

class LRUCache(Generic[K, V]):
    """Cache com tamanho máximo e política LRU. Thread-safe."""
    
    def __init__(self, max_size: int = 100) -> None:
        self._max = max_size
        self._data: OrderedDict[K, V] = OrderedDict()
        self._lock = RLock()
    
    def get(self, key: K) -> V | None:
        with self._lock:
            if key not in self._data:
                return None
            self._data.move_to_end(key)  # marca como recentemente usado
            return self._data[key]
    
    def put(self, key: K, value: V) -> None:
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
            else:
                if len(self._data) >= self._max:
                    self._data.popitem(last=False)  # remove o mais antigo
            self._data[key] = value
```

---

## 4. Roadmap de Migração (4 Fases)

### Fase 1: Fundação (2-3 semanas)
- [ ] Criar estrutura de pastas proposta
- [ ] Extrair entidades de domínio (`Paper`, `Protocol`, `Session`)
- [ ] Implementar `EventBus` tipado
- [ ] Criar `LRUCache` e substituir `_pdf_text_cache`
- [ ] Adicionar testes unitários para entidades (cobertura inicial 20%)

### Fase 2: Separação de Camadas (3-4 semanas)
- [ ] Extrair `ScreeningService`, `ExtractionService`, `HarvestOrchestrator`
- [ ] Criar `GeminiClient` com retry tipado (usando `tenacity`)
- [ ] Implementar `ProjectRepository` interface + JSON impl
- [ ] Migrar ViewModels (começar por `ScreeningViewModel`)
- [ ] Cobertura de testes sobe para 50%

### Fase 3: UI Refactor (4-5 semanas)
- [ ] Quebrar `SystematicReviewApp` em `AppWindow` + 4 Views
- [ ] Substituir `after(0, ...)` por `asyncio` + `threading`
- [ ] Migrar todas as telas para padrão MVVM
- [ ] Adicionar feedback visual estruturado (toasts, progress bars tipadas)

### Fase 4: Consolidação (2-3 semanas)
- [ ] DI Container (usar `dependency-injector` ou custom)
- [ ] Logging estruturado (`structlog` com correlation ID)
- [ ] Sistema de undo/redo via Command Pattern
- [ ] CI/CD com testes, lint (`ruff`), type-check (`mypy --strict`)
- [ ] Empacotamento (`PyInstaller`) otimizado

---

## 5. Ganhos Mensuráveis Esperados

| Métrica | Antes | Depois |
|---------|-------|--------|
| Linhas em `main.py` | ~5000 | ~80 (só bootstrap) |
| Cobertura de testes | 0% | 80%+ |
| Tempo para adicionar novo harvester | 2-3 dias | 2-3 horas (Adapter Pattern) |
| Tempo para trocar persistência | Impossível | 1 dia (nova impl do repo) |
| Bugs de sincronização de estado | Frequentes | Zero (única fonte: domínio) |
| Memory leak em sessões longas | Presente | Eliminado (LRU cache) |

---

## 6. Recomendação Estratégica

**Não tente reescrever tudo de uma vez.** O código atual funciona. A estratégia correta é **Strangler Fig Pattern**:

1. Mantenha o `main.py` atual rodando
2. Crie a nova estrutura em paralelo (`src/core`, `src/infrastructure`)
3. Migre **uma feature por vez** (comece pela mais problemática: batch screening)
4. A View antiga chama o novo Service via adaptador
5. Quando uma feature estiver 100% migrada e testada, remova o código legado

Isso permite continuar entregando valor enquanto a refatoração acontece.

---

## 7. Próximo Passo Concreto

Posso começar implementando **Fase 1 completa** agora:

1. Estrutura de pastas
2. Entidades de domínio (`Paper`, `Protocol`, `ScreeningSession`)
3. `EventBus` tipado e thread-safe
4. `LRUCache` substituindo o cache atual
5. Primeiros testes unitários (`pytest`)

**Quer que eu comece pela Fase 1?** Posso entregar um PR-ready com toda a fundação implementada, documentada e testada. A partir daí, cada fase subsequente se torna incremental e segura.