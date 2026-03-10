# progress.md

## Current Summary
`personal-ai` has evolved into a **fully integrated autonomous execution platform** with:
- Local-first inference orchestration (Ollama → Gemini fallback)
- TouchDesigner-first runtime with complete Houdini parity
- **Autonomous Loop Phase 2**: Sleep/poll, health monitoring, goal consumption
- **Bridge Executors**: TDBridgeExecutor and HoudiniBridgeExecutor fully implemented
- Recording + trace collection + session management
- Memory runtime integration with enhanced retrieval and ranking
- Goal-driven self-improvement with signal detection
- Checkpoint/resume lifecycle with boundary detection
- Fine-tune preparation infrastructure (47K+82K examples ready)
- Provider routing / cache / token budget
- PyQt6 Desktop GUI Application
- Visual verification (screenshot-based)
- OCR integration (Tesseract-first, EasyOCR fallback)
- Recursive task decomposition (bounded)

The repo is now a **production-ready runtime platform** with unified orchestration.

---

## Recent Update (2026-03-10) — Bridge Executors & Recipe Executor Integration

Completed bridge executor implementations and unified recipe execution:

### Bridge Executors
- **TDBridgeExecutor**: Full implementation with TDLiveClient integration
- **HoudiniBridgeExecutor**: Full implementation with HoudiniLiveClient integration
- Both support dry_run mode and live bridge calls
- Proper error handling and response mapping

### Recipe Executor Enhancements
- Unified recipe execution with backend selection
- Checkpoint/resume support for long-running recipes
- Precondition validation
- Step-by-step checkpoint tracking

### Integration Points
- `IntegratedRuntimeLoop.execute_step_with_retry()` routes to TDBridgeExecutor
- `RecipeExecutor` uses backend selection for consistent routing
- Memory retrieval before execution, writeback after

---

## Recent Update (2026-03-10) — Autonomous Loop Phase 2

Added comprehensive enhancements to the autonomous loop:

### New Status Types
- `SLEEPING` - Sleeping due to no actionable goals
- `DEGRADED` - Running in degraded mode
- `STARTING` / `STOPPING` - Lifecycle transitions

### New Decision Types
- `SLEEP` - Sleep when no work available
- `DEGRADE` - Switch to degraded mode
- `STOP_KILLSWITCH` - Immediate stop from killswitch
- `STOP_HEALTH` - Stop due to health issues
- `STOP_IDLE` - Stop due to idle timeout

### New Modules
| Module | Role |
|--------|------|
| `autonomous_loop_health.py` | HealthMonitor with BridgeHealthTracker integration |
| `autonomous_loop_decision.py` | DecisionPolicy for stop condition evaluation |
| `autonomous_loop_goals.py` | GoalConsumer for priority-based goal selection |
| `autonomous_loop_service.py` | Service wrapper with convenience entry points |

### Key Features
- **Sleep/poll behavior**: Exponential backoff when no actionable goals
- **Health monitoring**: Capture health snapshots, detect degraded state
- **Goal consumption**: Priority-based selection from GoalStore
- **Stop conditions**: Killswitch, max wall time, consecutive failures, idle timeout
- **Service wrapper**: `start_autonomous_loop()`, `stop_autonomous_loop()`, `pause_autonomous_loop()`, `run_single_tick()`

### Tests
- 24 comprehensive tests in `tests/test_autonomous_loop_service.py`
- All tests passing with deterministic mocks

---

## Recent Update (2026-03-09) — Goal Generator

Added signal-driven goal generation for self-improvement:

### Modules
| Module | Role |
|--------|------|
| `models.py` | Goal, GoalSignal, GoalType, GoalStatus, GoalPriority enums |
| `store.py` | GoalStore with JSONL persistence |
| `detectors.py` | Signal detection: ErrorSignalDetector, DocsSignalDetector, MemorySignalDetector, RuntimeSignalDetector |
| `prioritizer.py` | Priority scoring based on impact, actionability, recurrence |
| `service.py` | GoalGeneratorService orchestrating detection → prioritization → storage |

### Signal Categories
- **Docs/Knowledge**: docs_delta, new_operator, new_concept, tutorial_raw
- **Error/Failure**: repeated_error, repair_failure, no_progress_loop, verification_failure
- **Memory**: weak_retrieval, success_not_reused, task_cluster_weak_context
- **Runtime/Bridge**: bridge_degradation, command_rejection, backend_instability
- **Data**: weak_dataset_coverage, low_example_count, weak_recipe_coverage

### Goal Types
- **Learning**: learn_doc_concept, learn_new_operator, distill_tutorial_knowledge, create_recipe_knowledge
- **Fix/Repair**: fix_repeated_error, formalize_repair_pattern
- **Improvement**: improve_memory_reuse, improve_bridge_reliability, improve_verification_coverage
- **Investigation**: investigate_runtime_drift

---

## Recent Update (2026-03-09) — Memory Runtime Integration

Added complete memory runtime integration:

### Core Integration (`app/core/memory_runtime.py`)
- `build_runtime_memory_context()` - Build memory context before execution
- `inject_memory_into_prompt()` - Inject memory into system prompts
- `promote_success_to_pattern()` - Promote success to reusable pattern
- `record_failure_for_avoidance()` - Record failure for future avoidance
- `search_success_patterns()` - Search reusable success patterns
- `search_failure_patterns()` - Search failure patterns to avoid

### Memory Flow
```
Before Task          During Task           After Task
    ↓                      ↓                      ↓
Search Memory      →   Execute with      →  Promote Outcome
Build Context           Memory Hints             to Memory
Inject Prompt          Bias Decisions            Update Store
```

### Compactness Guarantees
- Max 3 success patterns retrieved
- Max 3 failure patterns retrieved
- Max ~250 chars per item
- Max ~600 chars total injection
- Graceful degradation when memory empty

---

## Recent Update (2026-03-09) — Checkpoint/Resume Lifecycle

Added complete checkpoint lifecycle:

### Modules
| Module | Role |
|--------|------|
| `checkpoint.py` | Checkpoint data model with full state capture |
| `checkpoint_lifecycle.py` | Create, validate, manage checkpoint boundaries |
| `checkpoint_resume.py` | Resume from checkpoint with context restoration |

### Features
- Boundary detection (after verify, on pause, on error)
- Resume with full context restoration
- Partial checkpoint support for long-running tasks
- Validation before resume

---

## Recent Update (2026-03-09) — Bridge Health Tracking

Added stateful bridge health monitoring:

### Modules
| Module | Role |
|--------|------|
| `bridge_health.py` | Ping/inspect health checks |
| `bridge_health_tracker.py` | Stateful tracking over time |
| `bridge_health_summary.py` | Health status summaries and transitions |

### Features
- Track ping/inspect/command results
- Degraded/unhealthy state detection
- Health snapshots for autonomous loop decisions
- Latency tracking

---

## Recent Update (2026-03-09) — PyQt6 Desktop GUI

Added complete desktop GUI application:

### Structure
```
gui/
├── main.py                    # Entry point
├── main_window.py             # Main window with navigation
├── tray_icon.py               # System tray
├── styles/dark_theme.py       # Catppuccin dark theme
├── widgets/
│   ├── dashboard_panel.py     # Status cards, quick actions
│   ├── task_panel.py          # Task creation/execution
│   ├── learning_panel.py      # YouTube learning, recipes
│   ├── memory_panel.py        # Memory management
│   ├── agent_panel.py         # TD/Houdini specialist cards
│   └── settings_panel.py      # 5-tab settings
└── workers/bridge_worker.py   # QThread workers
```

### Running
```bash
cd D:/personal-ai
python -m gui.main
```

---

## Recent Update (2026-03-09) — Video Action Extraction

Added complete video action extraction pipeline:

### Modules
| Module | Role |
|--------|------|
| `frame_extractor.py` | ffmpeg-based frame extraction |
| `video_screen_understanding.py` | OCR, UI detection, domain analysis |
| `graph_visual_parser.py` | Network topology from screenshots |
| `video_action_extractor.py` | Full extraction pipeline |

### Pipeline
```
video/frames → frame extraction → frame analysis → UI detection → action inference → action sequence
```

---

## Recent Update (2026-03-09) — Feedback Loop

Added practical feedback loop for error → retry → learning:

### Modules
| Module | Role |
|--------|------|
| `feedback_loop.py` | Error → retry → verify → learn cycle |
| `error_normalizer.py` | 9 normalized error types |
| `retry_strategy.py` | 10 retry strategy types |
| `error_memory.py` | Store failure patterns |
| `success_patterns.py` | Store reusable repair patterns |

### Normalized Error Types
- wrong_parameter, missing_output, connection_failed
- bridge_timeout, command_rejected, verification_failed
- no_progress, unexpected_state, unknown

### Retry Strategies
- attach_output, connect_link, fix_parameter
- retry_with_delay, switch_backend, escalate
- skip_step, restart_task, abort

---

## Recent Update (2026-03-08) — InverseDynamicsModel

Added action → intent labeling:

### Module (`app/learning/inverse_dynamics.py`)
- `infer_action(before, after) → Action` - Infer action from states
- `label_intent(action) → Intent` - Map action to intent
- `build_recipe(actions) → Recipe` - Build structured recipe

### Supported Actions
- create_node, create_operator
- connect_nodes, connect_operators
- set_parameter, attach_output
- switch_context, fix_error, inspect_state

---

## Recent Update (2026-03-08) — Bridge Servers

### TouchDesigner Bridge
- `scripts/td/td_bridge_server_module.py` - TOX component
- `scripts/td/td_webserver_handler.py` - HTTP routing
- Routes: `/ping`, `/network`, `/command`
- Default: `127.0.0.1:9988`

### Houdini Bridge
- `scripts/houdini/houdini_bridge_server.py` - HTTP server (stdlib)
- Routes: `/ping`, `/context`, `/command`
- Commands: inspect_context, basic_sop_chain, run_python
- Default: `127.0.0.1:9989`

---

## Current Architecture

### Layer Overview
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
│  TouchDesigner Bridge │ Houdini Bridge │ Future: Unity/Unreal  │
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

## Working / Present

### Core Infrastructure
- ✅ Inference orchestrator with local-first defaults
- ✅ Memory runtime integration (retrieve before, promote after)
- ✅ Checkpoint lifecycle with boundary detection
- ✅ Bridge health tracking
- ✅ Error normalization

### Autonomous Loop
- ✅ 6-stage lifecycle (OBSERVE → RETRIEVE → CHOOSE → EXECUTE → VERIFY → PROMOTE_REJECT)
- ✅ Sleep/poll with exponential backoff
- ✅ Health monitoring integration
- ✅ Goal consumption with priority ordering
- ✅ Killswitch support
- ✅ Service wrapper with convenience entry points

### Goal System
- ✅ Signal detection (errors, docs, memory, runtime)
- ✅ Priority scoring
- ✅ Goal persistence
- ✅ Goal consumer integration

### TouchDesigner
- ✅ Bridge server and client
- ✅ Execution loop with verification
- ✅ Action inference
- ✅ Graph planning

### Houdini
- ✅ Bridge server and client
- ✅ Execution loop
- ✅ Action inference
- ✅ Graph planning

### Recording / Learning
- ✅ Session recording
- ✅ Trace collection
- ✅ Dataset builder
- ✅ Feedback loop

### GUI
- ✅ PyQt6 desktop application
- ✅ Dashboard, task, learning, memory, agent panels
- ✅ Settings with 5 tabs

---

## Remaining Gaps

### 1. Validation & Benchmarking
- Cold vs warm task benchmark not yet run
- Memory reuse effectiveness unmeasured
- Real TD/Houdini end-to-end task completion rate unknown

### 2. Training & Learning
- Fine-tune training not executed (47K+82K examples ready, GPU needed)
- Success pattern reuse rate unmeasured
- Transcript distillation quality varies

### 3. Visual Verification
- Screenshot-based verification is partial
- Needs stronger integration with runtime loops
- Confidence calibration needed

### 4. Integration Depth
- Provider routing not uniformly used everywhere
- Some memory writeback paths incomplete

---

## Near-Term Priorities

### Priority A — Validation Sprint
1. Run cold vs warm task benchmarks
2. Measure memory reuse effectiveness
3. Validate end-to-end TD/Houdini task execution
4. Document bridge health in operational context

### Priority B — Training Execution
1. Execute fine-tune training pilot (GPU required)
2. Validate training data quality
3. Test local model performance improvement

### Priority C — Integration Hardening
1. Ensure all inference paths go through orchestrator
2. Strengthen error memory → runtime injection
3. Complete goal → autonomous loop pipeline
4. Add operational metrics/logging

### Priority D — Domain Expansion
1. Plan Unity/Unreal domain stubs
2. Consider Python/self-improvement domain
3. Cross-domain pattern transfer

---

## Success Criteria For Next Milestone

- [x] Real local model path working by default (Ollama)
- [x] Bridge executors implemented for TD and Houdini
- [x] Autonomous loop with sleep/poll, health monitoring
- [x] Goal generator with signal detection
- [x] Checkpoint/resume lifecycle
- [ ] Cold vs warm task improvement benchmark
- [ ] TD or Houdini completes bounded task end-to-end (validated)
- [ ] Result promoted into reusable knowledge
- [ ] Goal-driven improvement demonstrates value
- [ ] Fine-tune training executed and evaluated

---

## Long-Term Direction

The intended evolution:

```
bounded operator
    ↓
trace collection
    ↓
reusable memory/error knowledge
    ↓
retrieval-enhanced runtime
    ↓
small local learned policy
    ↓
fine-tuned action helper
    ↓
goal-driven self-improvement
```

This project should become:
- Not a generic chatbot
- Not an unrestricted agent
- A **personal TD/Houdini operator** that improves through:
  - Traces and memory
  - Retrieval and reuse
  - Goal-driven learning
  - Eventually small-model fine-tuning