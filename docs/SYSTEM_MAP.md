# Personal-AI Sistem Haritası

**Son Güncelleme:** 2026-03-10
**Durum:** Tam entegre runtime platform - Autonomous Loop Phase 2 tamamlandı

---

## Sistem Mimarisi

```
┌─────────────────────────────────────────────────────────────────┐
│                     GOAL GENERATOR LAYER                        │
│  Signal Detection → Goal Prioritization → Goal Store           │
├─────────────────────────────────────────────────────────────────┤
│                    AUTONOMOUS LOOP LAYER                        │
│  Observe → Retrieve → Choose → Execute → Verify → Promote       │
│  + Health Monitoring + Sleep/Poll + Checkpoint/Resume           │
├─────────────────────────────────────────────────────────────────┤
│                      DOMAIN LAYER                               │
│  TouchDesigner Bridge (9988) │ Houdini Bridge (9989)           │
├─────────────────────────────────────────────────────────────────┤
│                      CORE INFRASTRUCTURE                        │
│  Inference Orchestrator │ Memory Runtime │ Checkpoint Lifecycle │
│  Bridge Health Tracker │ Error Normalizer │ Provider Router     │
├─────────────────────────────────────────────────────────────────┤
│                      LEARNING LAYER                             │
│  Feedback Loop │ Error Memory │ Success Patterns │ Fine-tune   │
├─────────────────────────────────────────────────────────────────┤
│                      RECORDING LAYER                            │
│  Session Recording │ Trace Collection │ Dataset Builder         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Modüller ve Durumları

### Agent Core (`app/agent_core/`)

| Modül | Dosya | Görev | Durum |
|-------|-------|-------|-------|
| Autonomous Loop | `autonomous_loop.py` | 6 aşamalı döngü: OBSERVE→RETRIEVE→CHOOSE→EXECUTE→VERIFY→PROMOTE | ✅ Aktif |
| Runtime Loop | `runtime_loop.py` | Recipe execution, step retry, memory retrieval, checkpoint | ✅ Aktif |
| Backend Selector | `backend_selector.py` | Bridge/DirectAPI/DryRun seçimi, health-aware | ✅ |
| Backend Policy | `backend_policy.py` | Backend öncelikleri ve fallback kuralları | ✅ |
| Killswitch | `killswitch.py` | Global acil durdurma mekanizması | ✅ |
| OCR Engine | `ocr_engine.py` | Tesseract/EasyOCR wrapper, discovery, fallback | ✅ |
| Health Monitor | `autonomous_loop_health.py` | BridgeHealthTracker entegrasyonu | ✅ |
| Decision Policy | `autonomous_loop_decision.py` | Stop condition değerlendirme | ✅ |
| Goal Consumer | `autonomous_loop_goals.py` | Priority-based goal selection | ✅ |
| Task Decomposition | `decomposition_*.py` | Recursive task decomposition (bounded) | ✅ |

### Core Infrastructure (`app/core/`)

| Modül | Görev | Durum |
|-------|-------|-------|
| `inference_orchestrator.py` | Ollama→Gemini fallback, cache, budget | ✅ |
| `memory_runtime.py` | Pattern retrieval/writeback, enhanced retrieval | ✅ |
| `checkpoint.py` | Execution state kayıt/resume modelleri | ✅ |
| `checkpoint_lifecycle.py` | Checkpoint oluşturma, doğrulama, boundary detection | ✅ |
| `checkpoint_resume.py` | Resume manager, context restoration | ✅ |
| `bridge_health.py` | Bridge ping/inspect health checks | ✅ |
| `bridge_health_tracker.py` | Stateful health tracking | ✅ |
| `error_normalizer.py` | Normalize raw errors into typed categories | ✅ |
| `provider_router.py` | Route inference to local/remote providers | ✅ |
| `prompt_cache.py` | Cache prompts to reduce token usage | ✅ |
| `rag_index.py` | JSONL, transcript, web_ingest index | ✅ |

### Goal Generator (`app/goal_generator/`)

| Modül | Görev | Durum |
|-------|-------|-------|
| `models.py` | Goal, GoalSignal, GoalType, GoalStatus, GoalPriority | ✅ |
| `store.py` | GoalStore: persistent JSONL storage | ✅ |
| `detectors.py` | Signal detection: errors, docs, memory, runtime | ✅ |
| `prioritizer.py` | Priority scoring based on impact and actionability | ✅ |
| `service.py` | GoalGeneratorService: unified goal generation | ✅ |

### Learning (`app/learning/`)

| Modül | Görev | Durum |
|-------|-------|-------|
| `recipe_executor.py` | TDBridgeExecutor, HoudiniBridgeExecutor | ✅ |
| `feedback_loop.py` | Error → retry → verify → learn cycle | ✅ |
| `error_normalizer.py` | 9 normalized error types | ✅ |
| `error_memory.py` | Store failure patterns for avoidance | ✅ |
| `success_patterns.py` | Store reusable success patterns | ✅ |
| `retry_strategy.py` | 10 retry strategy types | ✅ |
| `inverse_dynamics.py` | Action → intent labeling | ✅ |
| `video_action_extractor.py` | Extract actions from tutorial videos | ✅ |
| `transcript_distiller.py` | Transcript→Knowledge pipeline | ✅ |
| `finetune_*.py` | Fine-tuning preparation and execution | ✅ |

### Domains (`app/domains/`)

**TouchDesigner (`touchdesigner/`)**

| Modül | Görev | Durum |
|-------|-------|-------|
| `td_launcher.py` | TD launch with AI auto-start | ✅ |
| `td_execution_loop.py` | Bounded execution loop | ✅ |
| `td_live_client.py` | HTTP client for TD bridge | ✅ |
| `td_live_protocol.py` | Request/Response modelleri | ✅ |
| `td_live_commands.py` | Command builder | ✅ |
| `td_action_inference.py` | TD-specific action inference | ✅ |
| `td_graph_*.py` | Graph planning and mutation | ✅ |
| `td_visual_verifier.py` | Screenshot-based verification | ✅ |

**Houdini (`houdini/`)**

| Modül | Görev | Durum |
|-------|-------|-------|
| `houdini_launcher.py` | Houdini launch with AI auto-start | ✅ |
| `houdini_execution_loop.py` | Bounded execution loop | ✅ |
| `houdini_live_client.py` | HTTP client for Houdini bridge | ✅ |
| `houdini_live_protocol.py` | Request/Response modelleri | ✅ |
| `houdini_action_inference.py` | Houdini-specific action inference | ✅ |
| `houdini_visual_verifier.py` | Screenshot-based verification | ✅ |

### Memory (`app/memory/`)

| Modül | Görev | Durum |
|-------|-------|-------|
| `memory_reuse_adapter.py` | Unified retrieval with ranking | ✅ |
| `memory_retrieval_models.py` | Retrieval request/response models | ✅ |
| `bridge_command_memory.py` | Bridge command memory management | ✅ |
| `known_good_command_cache.py` | Cache of known-good commands | ✅ |

### Recording (`app/recording/`)

| Modül | Görev | Durum |
|-------|-------|-------|
| `session_recorder.py` | Session lifecycle management | ✅ |
| `session_runtime.py` | Runtime session event helpers | ✅ |
| `trace_events.py` | RuntimeTraceEvent schema | ✅ |
| `dataset_builder.py` | Build datasets from sessions | ✅ |
| `quality_gate.py` | Data quality validation | ✅ |

---

## Bridge Executor Durumu

### TDBridgeExecutor

```python
from app.learning.recipe_executor import TDBridgeExecutor

# Dry run (test)
td = TDBridgeExecutor(dry_run=True)
td.ping()  # True
td.execute("create_node", {"node_type": "noiseTOP"})

# Gerçek bridge
td = TDBridgeExecutor(host="127.0.0.1", port=9988)
td.ping()  # TD açıkken True
td.execute_step(step)  # Gerçek TD komutu
```

### HoudiniBridgeExecutor

```python
from app.learning.recipe_executor import HoudiniBridgeExecutor

hou = HoudiniBridgeExecutor(dry_run=True)
hou.ping()  # True
hou.execute("create_node", {"node_type": "sphere"})

# Gerçek bridge (port 9989)
hou = HoudiniBridgeExecutor(port=9989)
```

---

## Veri Akışı

```
Goal Signal → GoalGenerator → GoalStore → GoalConsumer
                                              ↓
                                        AutonomousLoop
                                              ↓
                 Memory Retrieval ← ← ← ← ← ←┘
                        ↓
                 Backend Selection
                        ↓
            ┌──────────┴──────────┐
            ↓                     ↓
      TDBridgeExecutor    HoudiniBridgeExecutor
            ↓                     ↓
            └──────────┬──────────┘
                       ↓
               VerificationMerger
                       ↓
               Memory Writeback
                       ↓
               Checkpoint Save
```

---

## Veri Dosyaları

| Dosya | İçerik |
|-------|--------|
| `data/memory/success_patterns.json` | Başarılı execution'lar |
| `data/memory/failure_patterns.json` | Başarısız attempt'ler |
| `data/memory/distilled_knowledge.json` | Transcript'ten çıkarılan bilgi |
| `data/rag_index.json` | Retrieval indeksi |
| `data/checkpoints/` | Resume noktaları |
| `data/goals/` | GoalStore JSONL dosyaları |
| `data/training/` | Fine-tune dataset'leri |

---

## OCR Entegrasyonu

### Tesseract Discovery Sırası
1. `TESSERACT_CMD` environment variable
2. System PATH (`shutil.which`)
3. Windows default paths (`C:\Program Files\Tesseract-OCR\`)
4. User-specific paths (`%LOCALAPPDATA%`, scoop, chocolatey)

### Kullanım
```python
from app.agent_core.ocr_engine import (
    get_engine_status,
    verify_tesseract_install,
    extract_text,
)

status = get_engine_status()
result = extract_text(image_path, preferred_engine="tesseract", fallback=True)
```

### CLI
```bash
python -m app.cli ocr-status
```

---

## Test Durumu

| Kategori | Test Sayısı | Durum |
|----------|-------------|-------|
| Agent Core | 150+ | ✅ |
| Backend Selection | 50+ | ✅ |
| Bridge Executors | 40+ | ✅ |
| Memory Runtime | 30+ | ✅ |
| Goal Generator | 25+ | ✅ |
| OCR | 29 | ✅ |
| Recording | 35+ | ✅ |

**Toplam:** 3803 passed, 5 failed, 12 skipped (%99.87 pass rate)

---

## Runtime Status Flow

```
IDLE → STARTING → RUNNING → SLEEPING → RUNNING
              │          │          │
              │          ↓          │
              │      RETRYING       │
              │          │          │
              │          ↓          │
              │      REPAIRING      │
              │          │          │
              ↓          ↓          ↓
           DEGRADED ◄───────────────┤
              │
              ↓
           STOPPING → STOPPED/FAILED/SUCCEEDED
```

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

## CLI Komutları

```bash
# Test çalıştır
python -m pytest tests/ -q

# Bridge ping (TD açıkken)
curl http://127.0.0.1:9988/ping

# Goal generator
python -m app.goal_generator.service

# GUI başlat
python -m gui.main

# Autonomous loop
python -m app.main run-autonomous --domain touchdesigner
```

---

## Windows Kullanıcı Kurulumu (Tesseract)

1. İndir: https://github.com/UB-Mannheim/tesseract/wiki
2. Varsayılan konuma kur veya PATH'e ekle
3. Doğrula: `tesseract --version`
4. Alternatif: `set TESSERACT_CMD=C:\path\to\tesseract.exe`

---

## Güvenlik Sınırları

- Max iterations: 100 (hard cap)
- Max retries per step: 3
- Killswitch: Global acil durdurma
- Dry-run default: Güvenli varsayılan
- Budget tracking: Step/retry/repair budget'leri
- Health monitoring: Bridge health threshold'ları

---

## Gelecek Geliştirmeler

| Öncelik | Hedef |
|---------|-------|
| P0 | End-to-end TD/Houdini task benchmark |
| P1 | Cold vs warm memory improvement ölçümü |
| P2 | Fine-tune training execution |
| P3 | Unity/Unreal domain stub'ları |
| P4 | Visual model training |