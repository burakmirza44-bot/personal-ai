# Agent Core — The FDM-Inspired Pivot

## Why This Pivot

The infrastructure was solid: recording, schema, quality gate, dataset builder, bounded execution, safety layer, web ingest. But infrastructure is not intelligence. The system did not feel like an agent — it felt like a well-organized pipeline that waited for commands.

An agent notices what is happening, infers what changed, proposes what to do next, and learns from the result.

This pivot implements the minimum credible core loop that makes the system behave more like that.

---

## What We Are Not Building

This is NOT FDM-1.

FDM-1 (Foundation Decision Model) requires:
- A large-scale video encoder trained on thousands of hours of footage
- An Inverse Dynamics Model trained on video-action pairs at scale
- A Forward Dynamics Model predicting future frames from action embeddings
- GPU-scale training infrastructure

None of that exists here, and none of it is claimed.

---

## What We Are Building

The smallest credible personal action-learning loop, inspired by the FDM direction:

```
OBSERVE          read current network state (bridge / verification / simulated)
    |
EXTRACT STATE    turn raw data into structured TDNetworkState
    |
INFER            compare before/after — what action likely happened?
    |
PROPOSE          rank next safe action candidates given current state
    |
EXECUTE          run one bounded step via existing TDExecutionLoop
    |
VERIFY           check result structurally
    |
LOG TRACE        write AgentTrace record with full step history
    |
RETRY/DONE       retry within policy cap, or declare success/failure
```

This loop is bounded, auditable, and uses the same safety infrastructure that was already in place.

---

## Core Modules

| Module | Role |
|---|---|
| `agent_core/autonomous_loop.py` | Main autonomous loop: 6-stage lifecycle, killswitch, checkpoints |
| `agent_core/autonomous_loop_state.py` | State models: LoopState, LoopPolicy, IterationResult |
| `agent_core/autonomous_loop_health.py` | HealthMonitor with BridgeHealthTracker integration |
| `agent_core/autonomous_loop_decision.py` | DecisionPolicy for stop condition evaluation |
| `agent_core/autonomous_loop_goals.py` | GoalConsumer for priority-based goal selection |
| `agent_core/autonomous_loop_service.py` | Service wrapper: start/stop/pause/resume |
| `agent_core/runtime_loop.py` | IntegratedRuntimeLoop with checkpoint, memory, bridge health |
| `agent_core/backend_selector.py` | Backend selection with health-aware routing |
| `agent_core/backend_policy.py` | Backend priority and fallback rules |
| `agent_core/killswitch.py` | Global emergency stop mechanism |
| `agent_core/agent_trace.py` | Structured trace log for one agent session |
| `agent_core/shadow_mode.py` | Explicit observe-only mode (no hidden surveillance) |
| `agent_core/state_extractor.py` | Generic AgentState protocol and base types |
| `agent_core/action_inference.py` | ActionInference types — inferred_action, confidence, reason |
| `agent_core/next_action_policy.py` | ActionCandidate types — label, score, rationale, safety_status |
| `agent_core/agent_loop.py` | LoopState enum, AgentStepResult, AgentLoopResult |
| `agent_core/ocr_engine.py` | Tesseract-first OCR with EasyOCR fallback |
| `agent_core/decomposition_*.py` | Recursive task decomposition (bounded) |
| `domains/touchdesigner/td_state_extractor.py` | TD-specific structured state from bridge/verification |
| `domains/touchdesigner/td_action_inference.py` | TD action inference (create/connect/repair/extend) |
| `domains/touchdesigner/td_next_action_candidates.py` | State-aware ranked next-action candidates |
| `domains/touchdesigner/td_agent_loop.py` | Full TD observe→infer→propose→execute→verify loop |

---

## What Is FDM-Like Here

- **Inverse-dynamics flavor**: `td_action_inference.py` compares state_before and state_after to infer what action happened — structurally similar to an IDM but using graph diffs instead of video frames.
- **Forward-dynamics flavor**: `td_next_action_candidates.py` predicts what should happen next given current state — structurally similar to an FDM policy head but using rule-weighted heuristics instead of a trained model.
- **Closed loop**: observe → infer → propose → execute → verify → log is the same conceptual loop, grounded in structural TD data rather than pixels.

## What Is Not FDM-Like

- No video encoder. State is from bridge data and verification, not from screen pixels.
- No trained IDM. Action inference is rule-based diff comparison.
- No trained FDM. Next-action ranking is heuristic, not neural.
- No large dataset. Learning from accumulated loop traces is future work (M5 in FDM_PATH.md).

---

## Why TouchDesigner First

TD has a bridge protocol, a structured verification layer, and a well-defined operator graph. This gives us real state data to work with without needing a vision model. The structural loop (graph before → action → graph after) maps directly to what a future IDM would learn from.

Houdini receives compatible abstractions. Full Houdini agent loop is now implemented with parity.

---

## Phase 2 Enhancements (2026-03-10)

### Sleep/Poll Behavior
- Exponential backoff when no actionable goals
- Resets on activity resumption
- Configurable sleep intervals

### Health Monitoring
- BridgeHealthTracker integration
- Degraded state detection
- Health snapshots for decision making

### Goal Consumption
- Priority-based selection from GoalStore
- Domain filtering
- Integration with GoalGeneratorService

### Decision Types
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
| `STOP_BUDGET_EXHAUSTED` | Stop due to exhausted budgets |

---

## Safety Properties Preserved

- Max step cap enforced (`MAX_STEPS_HARD_CAP = 10`)
- All execution goes through existing `TDExecutionLoop` with retry limits
- `dry_run=True` is the default — live execution is explicit
- No action bypasses the existing `verify_basic_top_chain` check
- All proposals are auditable in the AgentTrace log
- Shadow mode is explicit start/stop only — no hidden background threads
- Killswitch provides global emergency stop
- Budget tracking prevents runaway execution
- Health monitoring degrades gracefully on bridge issues
