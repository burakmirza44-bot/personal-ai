# AGENTS.md

## Project
`personal-ai` is a **local-first personal AI runtime** focused on:
- **TouchDesigner first**, **Houdini second**
- Bounded autonomous execution with explicit safety
- Trace collection and learning preparation
- Memory retrieval and runtime reuse
- Goal-driven self-improvement

The goal is **not** an unrestricted autonomous agent.
The goal is a **bounded operator + memory + retrieval + goal-driven learning platform** that evolves into a personal action-learning assistant.

---

## Primary Priorities
When working in this repo, follow this order:

1. **Keep the runtime usable**
2. **Keep the system local-first**
3. **Preserve safety boundaries**
4. **Prefer small, testable patches**
5. **Unify existing paths before adding new features**
6. **Make learned/retrieved knowledge reusable at runtime**
7. **Do not overbuild**

If there is tension between a new feature and runtime stability, choose runtime stability.

---

## System Architecture Overview

### Core Runtime Loop
```
OBSERVE ──→ RETRIEVE ──→ CHOOSE ──→ EXECUTE ──→ VERIFY ──→ PROMOTE/REJECT
    │           │           │           │           │            │
    ▼           ▼           ▼           ▼           ▼            ▼
  Health     Memory      Backend     Bridge      Checkpoint   Memory
  Snapshot   Patterns    Selection   Command     Verification Writeback
```

### Layer Architecture

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

## Key Modules (2026-03-10)

### Agent Core (`app/agent_core/`)
The bounded autonomous execution engine.

| Module | Role |
|--------|------|
| `autonomous_loop.py` | Main loop class: 6-stage lifecycle (OBSERVE→RETRIEVE→CHOOSE→EXECUTE→VERIFY→PROMOTE_REJECT) |
| `autonomous_loop_state.py` | State models: LoopState, LoopPolicy, IterationResult, statuses, decisions |
| `autonomous_loop_service.py` | Service wrapper: start/stop/pause/resume/run_single_tick |
| `autonomous_loop_health.py` | Health monitoring with BridgeHealthTracker integration |
| `autonomous_loop_decision.py` | Decision policy: stop conditions, killswitch, health checks |
| `autonomous_loop_goals.py` | Goal consumer: priority-based selection from GoalStore |
| `backend_selector.py` | Backend selection with safety checks and health awareness |
| `decomposition_*.py` | Task decomposition with bounded recursion |
| `runtime_loop.py` | Legacy runtime loop (being unified into autonomous_loop) |
| `killswitch.py` | Global stop mechanism for emergency halt |

### Core Infrastructure (`app/core/`)
The foundational runtime infrastructure.

| Module | Role |
|--------|------|
| `inference_orchestrator.py` | **Local-first inference** - Ollama default, remote fallback |
| `memory_runtime.py` | Runtime memory integration - retrieve before, promote after |
| `checkpoint.py` | Checkpoint data models for pause/resume |
| `checkpoint_lifecycle.py` | Checkpoint creation, validation, boundaries |
| `checkpoint_resume.py` | Resume from checkpoint with context restoration |
| `bridge_health.py` | Bridge ping/inspect health checks |
| `bridge_health_tracker.py` | Stateful health tracking over time |
| `bridge_health_summary.py` | Health status summaries and transitions |
| `error_normalizer.py` | Normalize raw errors into typed categories |
| `provider_router.py` | Route inference to local/remote providers |
| `prompt_cache.py` | Cache prompts to reduce token usage |
| `memory_store.py` | Short-term and long-term memory storage |

### Goal Generator (`app/goal_generator/`)
Signal-driven goal generation for self-improvement.

| Module | Role |
|--------|------|
| `models.py` | Goal, GoalSignal, GoalType, GoalStatus, GoalPriority |
| `store.py` | GoalStore: persistent JSONL storage for goals |
| `detectors.py` | Signal detection: errors, docs, memory, runtime |
| `prioritizer.py` | Priority scoring based on impact and actionability |
| `service.py` | GoalGeneratorService: unified goal generation |

### Domains (`app/domains/`)
Domain-specific implementations.

**TouchDesigner (`touchdesigner/`)**
- `td_launcher.py` - TD launch with AI auto-start
- `td_execution_loop.py` - Bounded execution loop
- `td_live_client.py` - HTTP client for TD bridge
- `td_bridge_server_module.py` - Bridge TOX component
- `td_action_inference.py` - TD-specific action inference
- `td_graph_*.py` - Graph planning and mutation

**Houdini (`houdini/`)**
- `houdini_launcher.py` - Houdini launch with AI auto-start
- `houdini_execution_loop.py` - Bounded execution loop
- `houdini_live_client.py` - HTTP client for Houdini bridge
- `houdini_bridge_server.py` - HTTP server (stdlib)
- `houdini_action_inference.py` - Houdini-specific action inference

### Learning (`app/learning/`)
Feedback, improvement, and fine-tune preparation.

| Module | Role |
|--------|------|
| `feedback_loop.py` | Error → retry → verify → learn cycle |
| `error_normalizer.py` | 9 normalized error types |
| `error_memory.py` | Store failure patterns for avoidance |
| `success_patterns.py` | Store reusable success patterns |
| `retry_strategy.py` | 10 retry strategy types |
| `inverse_dynamics.py` | Action → intent labeling |
| `recipe_executor.py` | Execute learned recipes safely |
| `video_action_extractor.py` | Extract actions from tutorial videos |
| `action_prediction_*.py` | Simple local action prediction model |
| `finetune_*.py` | Fine-tuning preparation and execution |

### Recording (`app/recording/`)
Session recording and trace collection.

| Module | Role |
|--------|------|
| `session_recorder.py` | Session lifecycle management |
| `session_runtime.py` | Runtime session event helpers |
| `trace_events.py` | RuntimeTraceEvent schema |
| `dataset_builder.py` | Build datasets from sessions |
| `quality_gate.py` | Data quality validation |

### Orchestration (`app/orchestration/`)
Multi-gate orchestration spine.

| Module | Role |
|--------|------|
| `session_trace_collector.py` | Unified trace collection |
| `trace_spine.py` | Orchestration spine implementation |
| `lifecycle.py` | Session lifecycle management |
| `intake.py` | Task intake and routing |
| `decider.py` | Decision making |

### Memory (`app/memory/`)
Memory retrieval and reuse.

| Module | Role |
|--------|------|
| `memory_reuse_adapter.py` | Bridge command memory integration |
| `memory_retrieval_models.py` | Retrieval request/response models |
| `known_good_command_cache.py` | Cache of known-good bridge commands |
| `bridge_command_memory.py` | Bridge command memory management |

---

## Runtime Status Flow

```
IDLE ──→ STARTING ──→ RUNNING ──→ SLEEPING ──→ RUNNING
              │            │           │
              │            ▼           │
              │        RETRYING        │
              │            │           │
              │            ▼           │
              │        REPAIRING       │
              │            │           │
              ▼            ▼           ▼
           DEGRADED ◄───────────────┤
              │
              ▼
           STOPPING ──→ STOPPED/FAILED/SUCCEEDED
```

### Status Definitions
- **IDLE**: Loop not started
- **STARTING**: Loop initializing
- **RUNNING**: Actively executing
- **SLEEPING**: No actionable goals, polling with backoff
- **DEGRADED**: Running with health issues
- **RETRYING**: Retrying failed step
- **REPAIRING**: Executing repair
- **STOPPING**: Shutting down
- **STOPPED**: Stopped by user/policy
- **SUCCEEDED**: Completed successfully
- **FAILED**: Failed, cannot continue
- **BLOCKED**: Cannot proceed

---

## Loop Decision Types

| Decision | Action |
|----------|--------|
| `CONTINUE` | Continue to next iteration |
| `RETRY_CURRENT` | Retry failed step |
| `REPAIR_CURRENT` | Switch to repair path |
| `PAUSE` | Pause the loop |
| `SLEEP` | Sleep due to no actionable goals |
| `DEGRADE` | Switch to degraded mode |
| `STOP_SUCCESS` | Stop successfully |
| `STOP_ERROR` | Stop due to error |
| `STOP_KILLSWITCH` | Stop due to killswitch |
| `STOP_HEALTH` | Stop due to health issues |
| `STOP_IDLE` | Stop due to idle timeout |
| `STOP_BUDGET_EXHAUSTED` | Stop due to exhausted budgets |

---

## Stop Conditions (Priority Order)

1. **Killswitch** - Global stop requested
2. **Max Iterations** - Iteration limit reached
3. **Max Wall Time** - Time limit exceeded
4. **Max Consecutive Failures** - Failure threshold exceeded
5. **Bridge Unhealthy** - Health threshold exceeded
6. **Idle Timeout** - No work for too long
7. **Budget Exhausted** - Step/retry/repair budgets depleted

---

## Goal Types

| Category | Types |
|----------|-------|
| **Learning** | `learn_doc_concept`, `learn_new_operator`, `distill_tutorial_knowledge`, `create_recipe_knowledge` |
| **Fix/Repair** | `fix_repeated_error`, `formalize_repair_pattern` |
| **Improvement** | `improve_memory_reuse`, `improve_bridge_reliability`, `improve_verification_coverage`, `improve_data_coverage` |
| **Investigation** | `investigate_runtime_drift` |

---

## Signal Types

| Category | Types |
|----------|-------|
| **Docs/Knowledge** | `docs_delta`, `new_operator`, `new_concept`, `tutorial_raw` |
| **Error/Failure** | `repeated_error`, `repair_failure`, `no_progress_loop`, `verification_failure` |
| **Memory** | `weak_retrieval`, `success_not_reused`, `task_cluster_weak_context` |
| **Runtime/Bridge** | `bridge_degradation`, `command_rejection`, `backend_instability` |
| **Data** | `weak_dataset_coverage`, `low_example_count`, `weak_recipe_coverage` |

---

## Architectural Principles

### 1. Local-first
Default behavior works without cloud APIs:
1. Rule-based / retrieval
2. Cache
3. Local model (Ollama)
4. Remote model fallback only if explicitly allowed

### 2. Bridge-first
For TouchDesigner and Houdini:
- **Primary path** = bridge/runtime integration
- **Secondary path** = bounded mouse/keyboard fallback

### 3. Explicit, bounded automation
- No hidden background behavior
- No unrestricted desktop control
- No silent remote token spending

### 4. Learning through trace quality
Store:
- Compact state transitions
- Action traces with verification outcomes
- Normalized error facts
- Reusable success patterns

### 5. Retrieval before training
RAG/memory reuse is the first layer of learning.
Fine-tuning comes only after runtime reuse is proven.

### 6. Goal-driven self-improvement
Signals from errors, docs, memory, and runtime generate prioritized goals.
Goals are consumed by the autonomous loop for directed improvement.

---

## Guardrails

### Never do these by default
- Unrestricted crawling
- Hidden surveillance
- Unrestricted self-modification
- Silent remote provider use
- Silent destructive actions
- Giant graph generation without stop policy
- Prompting with huge unfiltered context dumps

### Always preserve
- Stop conditions
- Retry caps
- Window/focus guards
- Dry-run defaults where applicable
- Provenance for data and learning artifacts
- Compact prompt injection

---

## Coding Rules
- Python 3.11+
- Stdlib-first
- Small modules preferred
- Frozen dataclasses / `slots=True` where appropriate
- All public functions need docstrings
- Prefer deterministic behavior
- Avoid magic globals
- Avoid hidden side effects
- Keep CLI output concise and operational
- Keep file writes local, explicit, and inspectable

---

## Testing Rules
Every meaningful patch should:
1. Keep existing tests passing
2. Add targeted tests for new behavior
3. Avoid requiring real TD/Houdini/remote APIs in tests
4. Use mocks/fake bridge outputs where practical
5. Prefer regression tests for integration glue

---

## Preferred Work Order For Agents
1. Make CLI/imports/deps stable
2. Make local inference real
3. Make runtime memory reuse real
4. Make error loop real
5. Make bridge health visible
6. Unify core runtime orchestration across TD/Houdini
7. Improve RAG/transcript distillation
8. Only then push further into training/fine-tuning

---

## Definition of "Done" for a Runtime Feature
A runtime feature is done only when:
- Wired into the real runtime path
- Observable from CLI/runtime output
- Bounded by safety rules
- Tested
- Improves real behavior, not just scaffolding

---

## Current Phase Focus (2026-03-10)

### Recently Completed
- **Autonomous Loop Phase 2**: Sleep/poll behavior, health monitoring, goal consumption, service wrapper
- **Memory Runtime Integration**: Retrieve before execution, promote after, enhanced retrieval with ranking
- **Checkpoint/Resume**: Full lifecycle with boundary detection
- **Goal Generator**: Signal-driven goal generation with priority scoring
- **Bridge Health Tracking**: Stateful health monitoring
- **Bridge Executors**: TDBridgeExecutor and HoudiniBridgeExecutor fully implemented
- **Recipe Executor**: Unified recipe execution with backend selection, checkpoint support
- **Visual Verification**: Screenshot-based verification for TD and Houdini
- **Task Decomposition**: Recursive bounded decomposition with domain rules
- **OCR Integration**: Tesseract-first with EasyOCR fallback, stabilized

### Current Gaps
1. **Integration depth** - Provider routing not uniformly used everywhere
2. **Runtime validation** - Cold vs warm benchmark not yet run, real end-to-end tasks need validation
3. **Learning quality** - Fine-tune dataset ready but training not executed
4. **Visual verification** - Partial implementation, needs strengthening

### Next Priorities
1. Run cold vs warm task benchmarks
2. Validate end-to-end TD/Houdini task execution
3. Execute fine-tune training pilot
4. Strengthen bridge health visibility in production
5. Improve transcript distillation quality

---

## Notes for Future Agent Work
- Prefer **small scoped patches**
- Prefer **diff-only changes**
- Do not rewrite architecture unless explicitly asked
- Connect existing parts instead of inventing new ones
- Finish integration before replacing
- Treat this repo as a **runtime platform under construction**, not a greenfield demo