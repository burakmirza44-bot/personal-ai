# Personal-AI — Claude Geliştirme Brifing Dokümanı

**Versiyon:** 2026-03-10 (Phase 2 Complete)
**Amaç:** Claude'a bu projeyi geliştirmek için tam bağlam sağlamak

---

## Proje Nedir?

`D:\personal-ai` — Houdini ve TouchDesigner için kişisel, lokal-öncelikli AI asistanı.

**Hedef:**
- Houdini/TD'de node/operator oluşturma, parametre ayarlama, graph building görevlerini otonom yapabilmek
- Yaptığı işlerden öğrenmek (memory, distillation, fine-tune)
- Goal-driven: hatalardan, doc'lardan, başarısızlıklardan kendi kendine öğrenme hedefleri üretmek

**Değil:**
- Genel amaçlı chatbot
- Kısıtlanmamış otonom agent
- Bulut bağımlı sistem — tüm inference Ollama üzerinden (qwen3 modelleri)

---

## Mimari Katmanlar (Üstten Alta)

```
┌─────────────────────────────────────────────────────────┐
│  GOAL LAYER — GoalGeneratorService                      │
│  Sinyal tespiti → Goal üretimi → GoalStore (JSONL)       │
├─────────────────────────────────────────────────────────┤
│  AUTONOMOUS LOOP — AutonomousLoopService                │
│  OBSERVE→RETRIEVE→CHOOSE→EXECUTE→VERIFY→PROMOTE         │
│  Sleep/poll, killswitch, health monitoring               │
├─────────────────────────────────────────────────────────┤
│  ORCHESTRATION — IntegratedRuntimeLoop / TDExecutionLoop│
│  Checkpoint/resume, memory inject, bridge health gate    │
├─────────────────────────────────────────────────────────┤
│  DOMAIN LAYER                                           │
│  TouchDesigner (port 9988) │ Houdini (port 9989)        │
│  TDLiveClient │ Graph planner │ Verifier │ UI controller │
├─────────────────────────────────────────────────────────┤
│  CORE INFRASTRUCTURE                                    │
│  InferenceOrchestrator (Ollama-first) │ Memory Runtime  │
│  CheckpointLifecycle │ BridgeHealthTracker │ RAG Index   │
├─────────────────────────────────────────────────────────┤
│  LEARNING LAYER                                         │
│  FeedbackLoop │ ErrorMemory │ SuccessPatterns            │
│  TranscriptDistiller │ VideoToRecipe │ FinetunePipeline  │
└─────────────────────────────────────────────────────────┘
```

---

## Kritik Dosyalar

### Execution Merkezi

| Dosya | Satır | Ne Yapıyor |
|-------|-------|-----------|
| `app/agent_core/runtime_loop.py` | ~730 | `IntegratedRuntimeLoop` — checkpoint, memory, bridge health, step execution |
| `app/learning/recipe_executor.py` | ~1100 | `RecipeExecutor`, `TDBridgeExecutor`, `HoudiniBridgeExecutor` |
| `app/domains/touchdesigner/td_execution_loop.py` | ~700 | TD-spesifik execution, routing, checkpoint |
| `app/domains/houdini/houdini_execution_loop.py` | ~? | Houdini-spesifik execution |

### Bridge Communication

| Dosya | Ne Yapıyor |
|-------|-----------|
| `app/domains/touchdesigner/td_live_client.py` | HTTP client — TD bridge'e ping/inspect/command gönderir |
| `app/domains/touchdesigner/td_live_commands.py` | Command builder — `create_node`, `set_par`, `run_script` |
| `app/domains/touchdesigner/td_live_protocol.py` | Request/Response modelleri |
| `scripts/td/td_bridge_server_module.py` | TD içine yüklenen WebServer DAT |
| `scripts/td/td_webserver_handler.py` | HTTP routing: `/ping`, `/network`, `/command` |
| `scripts/houdini/houdini_bridge_server.py` | Houdini stdlib HTTP server — port 9989 |

### Memory & Learning

| Dosya | Ne Yapıyor |
|-------|-----------|
| `app/core/memory_runtime.py` | Pre-execution retrieval, post-execution writeback |
| `app/core/rag_index.py` | JSONL-tabanlı RAG indeksi |
| `app/learning/transcript_distiller.py` | Video/transcript → DistilledKnowledge |
| `app/learning/feedback_loop.py` | Error → retry → learn döngüsü |
| `app/learning/error_memory.py` | Başarısızlık pattern'larını saklar |
| `app/learning/success_patterns.py` | Başarılı yaklaşımları saklar |

### Goal Sistemi

| Dosya | Ne Yapıyor |
|-------|-----------|
| `app/goal_generator/service.py` | `GoalGeneratorService` — sinyal → goal |
| `app/goal_generator/detectors.py` | Error/docs/memory/runtime sinyal detektörleri |
| `app/goal_generator/store.py` | `GoalStore` — JSONL persistence |
| `app/goal_scheduler_bridge/bridge_service.py` | `GoalSchedulerBridge` — goal → task dönüşümü |
| `app/agent_core/autonomous_loop_goals.py` | `GoalConsumer` — döngüde goal tüketimi |

### Inference

| Dosya | Ne Yapıyor |
|-------|-----------|
| `app/core/inference_orchestrator.py` | Birleşik inference entry point (Ollama-first) |
| `app/core/provider_router.py` | Local/remote provider routing |
| `app/core/prompt_cache.py` | Tekrar eden query short-circuit |
| `app/integrations/ollama_client.py` | Ollama HTTP client |

---

## Mevcut Stub'lar ve Eksiklikler

### ✅ Tamamlanan (Eski Stub'lar)

| Özellik | Durum | Not |
|---------|-------|-----|
| TDBridgeExecutor.execute() | ✅ TAMAMLANDI | TDLiveClient entegrasyonu yapıldı |
| HoudiniBridgeExecutor.execute() | ✅ TAMAMLANDI | HoudiniLiveClient entegrasyonu yapıldı |
| IntegratedRuntimeLoop.execute_step_with_retry() | ✅ TAMAMLANDI | TDBridgeExecutor'a route ediliyor |
| Autonomous Loop Phase 2 | ✅ TAMAMLANDI | Sleep/poll, health, goal consumption |
| Checkpoint/Resume | ✅ TAMAMLANDI | Full lifecycle |
| Goal Generator | ✅ TAMAMLANDI | Signal detection, prioritization |

### ⚠️ Halen Eksik/Kısmi

| Özellik | Öncelik | Açıklama |
|---------|---------|----------|
| UI Automation (_execute_via_ui) | Düşük | Bridge öncelikli, UI fallback henüz yok |
| Fine-tune Training | Orta | 47K+82K örnek hazır, GPU gerekiyor |
| Visual Verification | Orta | Kısmi implementasyon, güçlendirilmeli |
| Cold vs Warm Benchmark | Yüksek | Memory reuse etkinliği ölçülmedi |
| End-to-End Validation | Yüksek | Gerçek TD/Houdini task tamamlama oranı bilinmiyor |

---

## Veri Dosyaları

```
data/
├── memory/
│   ├── success_patterns.json      # Başarılı execution pattern'ları
│   ├── failure_patterns.json      # Başarısız pattern'lar
│   └── distilled_knowledge.json   # Distill edilmiş bilgi
├── rag_index.json                 # RAG indeksi
├── checkpoints/                   # Checkpoint dosyaları
├── goals/                         # GoalStore JSONL
└── transcripts/{domain}/          # Ham transcript'ler
```

---

## Test Durumu

**Toplam:** 3803 passed, 5 failed, 12 skipped (%99.87 pass rate)

**Başarısız testler:**
- `test_ollama_default_provider.py` (1) — Failure normalization
- `test_ollama_runtime_integration.py` (1) — Remote fallback
- `test_bridge_command_memory.py` (3) — Cache metadata integration

**Kategori bazlı:**
- Agent Core: 150+ test
- Backend Selection: 50+ test
- Bridge Executors: 40+ test
- Memory Runtime: 30+ test
- Goal Generator: 25+ test
- OCR: 29 test
- Recording: 35+ test

**Not:** Tüm testler mock/dry_run üzerinde. Gerçek bridge'e bağlanan integration test'ler için TD/Houdini çalışır olmalı.

---

## Model Konfigürasyonu

```python
# app/core/inference_orchestrator.py
_DEFAULT_REASONING_MODEL = "qwen3:14b"
_DEFAULT_VISION_MODEL = "qwen3-vl:30b"
_DEFAULT_FAST_MODEL = "qwen3:4b"

LOCAL_PROVIDERS = {"ollama", "rule_based"}
REMOTE_PROVIDERS = {"gemini", "openai"}   # sadece fallback
```

Provider önceliği: **Ollama → Rule-based → Gemini → OpenAI**

---

## Kod Standartları (Bu Projede Zorunlu)

```python
# 1. Type hints — her fonksiyonda
def execute_step(self, step: dict[str, Any]) -> dict[str, Any]: ...

# 2. Dataclass pattern
@dataclass(slots=True)
class ExecutionResult:
    success: bool = False
    domain: str = ""

# 3. Güvenli default'lar
def run(self, dry_run: bool = True, bounded_mode: bool = True): ...

# 4. logging, print değil
logger = logging.getLogger(__name__)
logger.info("[td_exec] step %s completed in %.1fms", step_id, elapsed)

# 5. Spesifik exception
try:
    ...
except urllib.error.URLError as exc:
    raise RuntimeError(f"Bridge connection failed: {exc}") from exc

# 6. Her public fonksiyona docstring
# 7. Yeni fonksiyon = yeni test
```

---

## Bridge Protokolü (TouchDesigner)

**Endpoint:** `http://127.0.0.1:9988`

```
GET  /ping                    → {"status": "ok", "version": "..."}
GET  /network?path=/project1  → {"ops": [...], "connections": [...]}
POST /command                 → TDLiveCommandRequest → TDLiveCommandResponse
```

**Command format:**
```json
{
  "command": "create_node",
  "params": {
    "node_type": "noiseTOP",
    "name": "noise1",
    "parent_path": "/project1"
  }
}
```

**Python model:** `app/domains/touchdesigner/td_live_protocol.py`
**Command builder:** `app/domains/touchdesigner/td_live_commands.py`

---

## Bridge Protokolü (Houdini)

**Endpoint:** `http://127.0.0.1:9989`

```
GET  /ping
GET  /context
POST /command
```

**Desteklenen komutlar:** `inspect_context`, `basic_sop_chain`, `run_python`

---

## Öncelikli Geliştirme Hedefleri

### P0 — Validation (Şu an)
- Cold vs warm task benchmark çalıştır
- Memory reuse etkinliğini ölç
- End-to-end TD/Houdini task doğrulama

### P1 — Training Execution
- Fine-tune training pilot (GPU gerekiyor)
- Training data kalitesini doğrula
- Local model performans iyileştirmesi test et

### P2 — Integration Hardening
- Tüm inference path'lerinin orchestrator'dan geçtiğinden emin ol
- Error memory → runtime injection'ı güçlendir
- Goal → autonomous loop pipeline'ı tamamla

### P3 — Visual Verification
- Screenshot-based verification'ı güçlendir
- Runtime loop ile entegrasyonu iyileştir
- Confidence calibration ekle

### P4 — Domain Expansion
- Unity/Unreal domain stub'ları
- Cross-domain pattern transfer

---

## Sık Kullanılan Komutlar

```bash
# Test çalıştır
cd D:/personal-ai
python -m pytest tests/ -q

# Spesifik modül testi
python -m pytest tests/agent_core/ -v
python -m pytest tests/domains/ -v

# Bridge ping (TD açıkken)
curl http://127.0.0.1:9988/ping

# Demo script
python scripts/demo_goal_scheduler_bridge.py

# GUI başlat
python -m gui.main

# RAG index oluştur
python -c "from app.core.rag_index import build_index, save_index; save_index(build_index())"
```

---

## Claude'a Prompt Yazarken

### Bağlam her zaman şunu içersin:
```
D:\personal-ai projesinde, [modül] altında çalışıyorum.
Mevcut pattern: [ilgili sınıf/fonksiyon adı]
Yapmak istediğim: [net görev]
```

### Örnek — doğru prompt:
```
D:\personal-ai, app/learning/recipe_executor.py içinde
TDBridgeExecutor.execute() metodunu implement etmek istiyorum.
TDLiveClient (app/domains/touchdesigner/td_live_client.py) ve
TDLiveCommandRequest (td_live_protocol.py) mevcut.
execute() şu an "Bridge communication not implemented" döndürüyor.
Bunu TDLiveClient.send_command() kullanarak implement et.
dry_run=True olduğunda simüle etsin.
```

### Kaçınılacak:
- "Yeni bir bridge sistemi tasarla" — varolan sistemi kullan
- "Mimarı iyileştir" — sadece implementasyona odaklan
- "GUI ekle" — önce execution çalışsın

---

*Hazırlandı: 2026-03-10*
