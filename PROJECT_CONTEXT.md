# PROJECT_CONTEXT.md

## Executive Summary
`personal-ai` is a local-first personal AI staff system. The current implementation target is a practical assistant core plus a TouchDesigner-first specialist layer, with offline-safe behavior by default. Future learning/observation capability is planned as controlled, incremental extensions.

## Project Identity
- Project: `personal-ai`
- Mission: personal staff first, workflow-learning operator later
- Source-of-truth docs: `AGENTS.md`, `progress.md`, `TD_DATASET_SPEC.md`, `TD_ACTION_SCHEMA.md`
- Implementation style: modular, Python-first, safe by default, incremental and reversible

## What This Project Is
- A personal assistant foundation: intake, planning, routing, memory scaffolding, progress tracking
- A TouchDesigner-first domain system: TD knowledge, TD tasks, TD eval, TD-safe bridge scaffolds
- A local-first/offline-capable architecture with lightweight integrations and honest stubs
- A preparation layer for future learning inputs (docs/projects/logs/tutorial metadata)

## What This Project Is Not
- Not a production-ready computer-use agent
- Not a production-ready video-learning system
- Not a trained FDM-1-level inverse/forward dynamics action model
- Not uncontrolled autonomous coding or risky automation

## Current Priorities
1. TouchDesigner
2. Houdini
3. Python/self-improvement infrastructure
4. Personal assistant operations
5. Much later: Unreal Engine 5
6. Much later: Unity

Operational emphasis right now:
1. Personal assistant core
2. TD-first domain structure
3. Offline-capable local architecture
4. Learning/video/action only as metadata and stubs

## Architecture Overview
- Layer 1: Personal Staff Core
  - task intake, planning, memory scaffolding, state, routing, safe boundaries
- Layer 2: TouchDesigner Specialist Layer (first-class)
  - operator knowledge, task taxonomy/library, TD eval logic, safe Python bridge stubs
- Layer 3: Future Observation and Learning Layer
  - docs/project/log/tutorial metadata pipelines first
  - future screen/action traces and bounded trial loops later

Separation rule: do not mix core orchestration and future observation/learning internals prematurely.

## Agent Roles
Current role set:
- `director`
- `td_specialist`
- `memory_curator`
- `safety_guard`
- `future_researcher`
- `future_self_improvement_agent`

Role intent:
- director orchestrates and plans
- td_specialist handles TD reasoning/tasks
- safety_guard enforces policy boundaries
- memory_curator controls memory quality/promotion
- future roles remain supervised placeholders

## Working Rules
- TD is first-class domain right now
- Keep code simple, typed, and modular (`pathlib`, `dataclasses`, `typing`, `logging`)
- Public classes/functions require docstrings
- No fake capabilities; roadmap != implemented behavior
- Changes must be incremental and reversible
- Dependencies require explicit justification
- Avoid risky automation, destructive defaults, and silent behavior changes
- Workflow principle:
  - `understand -> structure -> document -> scaffold -> test`
  - then `observe -> propose -> patch -> test -> report -> approve`

## TouchDesigner Priority
Near-term TD focus:
- task taxonomy
- operator family knowledge (TOP/CHOP/SOP/DAT/COMP/MAT)
- Python bridge concepts and safe helper generation
- TD evaluation rules and reporting structure

Later TD focus:
- supervised adapters, safe observation concepts, replay-oriented analysis
- no uncontrolled UI automation in current scope

## FDM-1 Direction and Limits
Directionally inspired by FDM-1-style ideas (state/action/outcome relationships), but current project is not an FDM-1 training pipeline.

Current limits:
- no inverse-dynamics labeling pipeline in production
- no next-action model training
- no large-scale frame-level action dataset training

Current practical objective:
- structure TD tasks, metadata, and action records so evaluator/replay/action-learning experiments can be added later under safety constraints.

## TD Dataset Strategy
Primary document: `TD_DATASET_SPEC.md`

Current dataset layers (priority order):
1. TD docs (`data/td_docs/`)
2. TD task examples (`data/annotations/td_tasks/`)
3. TD tutorial metadata (`data/td_tutorials/`)
4. local project metadata (`data/projects/`)
5. TD session logs (`data/logs/`)
6. future video metadata (`data/annotations/video_metadata/`)
7. future action traces (`data/annotations/action_traces/`)

Policy highlights:
- metadata-first, local-first, privacy-first
- explicit consent for personal project reads, logs, screen/video/action trace collection
- do not capture secrets, credentials, financial/private sensitive data by default
- avoid over-annotation early (no frame-by-frame/pixel-level labeling now)

## TD Action Schema Summary
Primary document: `TD_ACTION_SCHEMA.md`

Core chain:
- `goal -> state_before -> action -> state_after -> evaluation`

Action model summary:
- required identity/context fields: `action_id`, `session_id`, `task_id`, `timestamp`, `domain`, `app_name`
- abstraction level: `ui | operator | parameter | script | file | system`
- status and safety fields: `planned/attempted/succeeded/failed/cancelled`, `safe/caution/approval_required/blocked`
- TD-specific fields: operator path/family/type, parameter before/after, network path, selection context
- UI fields (when applicable): window title, ui_event, key/mouse context

Key decision:
- prefer structure-level TD records over raw UI-only logs when possible.

## Safety Boundaries
Hard limits:
- no irreversible destructive actions by default
- no silent deletion
- no secret exfiltration
- no automatic money transfer
- no uncontrolled internet usage
- no unapproved external posting/messaging/email
- no pretending unimplemented learning systems are production-ready

Execution posture:
- dry-run and supervised by default
- explicit approval for higher-risk actions and sensitive data flows

## Offline-First Model Policy
- Offline mode is default
- Default provider policy is local Ollama-first
- App must run even if Ollama is not installed (integration is optional/stub-safe)
- Optional cloud providers are future explicit adapters

Offline works for:
- planning/routing/memory scaffolding
- local docs and local index scaffolds
- TD knowledge/tasks/eval modules

Offline-disabled/reduced:
- remote fetch
- cloud inference
- internet-dependent learning pipelines

## Roadmap
High-level phase sequence from `progress.md`:
1. Foundation
2. Personal assistant core
3. TD knowledge layer
4. TD Python helper/executor layer
5. TD eval/task library layer
6. TD learning pipeline preparation
7. Bounded TD trial loop
8. Houdini expansion
9. Self-improvement loop (approval-gated)
10. Future Unreal/Unity expansion

Near-term success signals:
- assistant usefulness increases
- TD guidance is structured and reusable
- offline core remains reliable
- no safety boundary regressions

## Current Maturity Map (2026-03-10)

Maturity levels: WORKING | PARTIAL | SCAFFOLD | MISSING

| Area | Status |
|---|---|
| Core scaffold (config, registry, router, CLI) | WORKING |
| TD knowledge + eval rubrics | WORKING |
| TD Python bridge (snippet gen) | WORKING |
| TD live protocol (client side) | WORKING |
| TD UI control (dry-run + real dispatch) | WORKING |
| TD desktop observation (screenshots) | WORKING |
| TD bridge executor (TDBridgeExecutor) | WORKING |
| TD visual verification | WORKING |
| Houdini knowledge + eval rubrics | WORKING |
| Houdini live protocol (client side) | WORKING |
| Houdini file bridge (inbox/outbox JSON) | WORKING |
| Houdini bridge executor (HoudiniBridgeExecutor) | WORKING |
| Houdini visual verification | WORKING |
| Provider router (local-first, budget-aware) | WORKING |
| Token budget (daily/session/task limits) | WORKING |
| Prompt cache (hash-based, persisted) | WORKING |
| Interface contracts (TD + Houdini + CHOP/DOP) | WORKING |
| Graph stop policy (task contract, no-progress) | WORKING |
| TD multi-layer graph builder | WORKING |
| Houdini multi-layer graph builder | WORKING |
| Houdini complexity patterns (CHOP/constraint/DOP) | WORKING |
| Houdini verifier + retry policy | WORKING |
| Houdini state extractor + action inference | WORKING |
| Houdini execution loop (execute→verify→retry) | WORKING |
| Houdini agent loop (observe→infer→propose→exec→verify) | WORKING |
| run_task() with cache + Ollama + remote routing | WORKING |
| Memory persistence (load/save JSON) | WORKING |
| Memory retrieval injected into run_task() | WORKING |
| Memory promotion after successful inference | WORKING |
| Enhanced memory retrieval with ranking | WORKING |
| RAG index (198K chunks, TF-IDF) | WORKING |
| RAG context injected into run_task() | WORKING |
| Fine-tune pipeline (validate/split/script/dry-run) | WORKING |
| Training data (47K TD + 82K Houdini Alpaca JSONL) | WORKING |
| Houdini auto_learn (curriculum→bank→patterns→transcripts→LLM) | WORKING |
| Houdini auto_learn memory integration | WORKING |
| TD auto_learn memory integration | WORKING |
| scripts/ask.py CLI | WORKING |
| LLM inference — Ollama (real HTTP calls) | WORKING |
| LLM inference — Gemini (remote fallback) | WORKING |
| TD bridge server (WebServer DAT side) | WORKING |
| Houdini bridge server (hou side script) | WORKING |
| Houdini bridge HTTP server | WORKING |
| Autonomous Loop Phase 2 (sleep/poll/health/goals) | WORKING |
| Checkpoint/Resume lifecycle | WORKING |
| Goal Generator (signal detection → prioritization) | WORKING |
| Bridge Health Tracking | WORKING |
| Error Loop Manager | WORKING |
| Recipe Executor with backend selection | WORKING |
| Recursive task decomposition | WORKING |
| Simple action prediction model (sklearn) | WORKING |
| Visual/screen understanding | WORKING |
| Video action extraction pipeline | WORKING |
| Frame extraction (ffmpeg-based) | WORKING |
| Screen understanding (OCR + UI detection) | WORKING |
| Graph visual parser | WORKING |
| MSS screen capture | WORKING |
| Local OCR (Tesseract-first, EasyOCR optional) | WORKING |
| Bounded self-improvement loop | WORKING |
| UI element detection (pyautogui + template matching) | WORKING |
| Session recording auto-integration | WORKING |
| RAG index ↔ distilled tutorial knowledge | PARTIAL |
| Web ingest ↔ RAG integration | WORKING |
| Fine-tune actual training run (GPU) | MISSING (data ready, training not yet executed) |
| TD live bridge ↔ UI automation routing policy | MISSING |
| Memory store ↔ session/recording auto-promotion | MISSING |

## Remaining Gaps (Priority Order)
1. ~~**TD + Houdini bridge servers not set up**~~ — DONE: Both bridge servers now work. TD uses TOX-friendly asset set (paste into DATs), Houdini uses HTTP server (127.0.0.1:9989).
2. **Fine-tune not trained** — 47K+82K examples validated, training script generated, but `python train_lora.py` never run (needs GPU).
3. ~~**Memory ↔ session/recording auto-promotion**~~ — DONE (`app/recording/success_promoter.py`): `try_promote_session()` and `try_promote_trace_examples()` promote succeeded outcomes; `SessionRecorder.end_session(memory=...)` hooks it automatically.
4. **TD live bridge vs UI automation** — no single policy deciding which execution mode to use per task.
5. **RAG missing distilled tutorial knowledge** — raw transcripts indexed, but structured recipe extraction not in main flow.

## Source Documents
Merged from:
- `AGENTS.md`
- `progress.md`
- `TD_DATASET_SPEC.md`
- `TD_ACTION_SCHEMA.md`
- `README.md`
- `VISION.md`
- `DOMAINS.md`
- `TD_ROADMAP.md`
- `LEARNING_ARCHITECTURE.md`
- `SELF_IMPROVEMENT.md`
- `ACTION_SCHEMA.md`
- `EVALS.md`
- `SAFETY.md`
- `MEMORY_POLICY.md`
- `MODEL_POLICY.md`
- `OFFLINE_MODE.md`

---

## FDM Path Reference
- Long-term learning roadmap is maintained in `FDM_PATH.md`.
- Any learning/training work must follow `FDM_PATH.md` milestone order.
- Rule: no model-training claims before Milestone 1-4 data foundations are complete.

## Recent Implemented Work (2026-03-06)
- Session recording infrastructure added (`app/recording/*`): explicit start/end, event logging, notes, screenshots, manifest.
- Tutorial metadata layer added and operational (`tutorial-add`, local metadata JSON files).
- Session-tutorial linking added (`session-link-tutorial`) for curation traceability.
- TouchDesigner tutorial and channel metadata batches imported and linked to sessions.
- Bounded TD/Houdini live bridge and TD closed-loop components remain active as execution backbone.

## Pipeline Update (2026-03-06)
- Schema lock layer added: `app/recording/schema_contract.py`, `schema_validator.py`.
- Data quality gate added: `app/recording/quality_gate.py` with valid/partial/invalid classification and reason histograms.
- Canonical dataset builder added: `app/recording/dataset_builder.py`, `dataset_splits.py`, `privacy_scrubber.py`, `scripts/dataset_build.py`.
- New docs added: `docs/SCHEMA_CONTRACT.md`, `docs/DATA_QUALITY_GATE.md`, `docs/DATASET_BUILDER.md`.

## Learning Layer Update (2026-03-06)
- Action supervision layer added (`app/learning/action_supervision.py`) with strict proposed/executed/verification fields.
- Inverse-style labeling prep added (`app/learning/inverse_labeling.py`) with conservative ambiguity handling.
- Baseline learner added (`app/learning/baseline_learner.py`, `baseline_inference.py`) as narrow next-safe-action selector.
- Offline evaluator gate added (`app/learning/evaluator_gate.py`) with pass/fail blocking reasons.
- Model card/risk note and local registry flow added (`model_card.py`, `model_registry.py`).
- Training/eval scripts added: `scripts/train_baseline.py`, `scripts/eval_baseline.py`.

## Data Volume Growth Update (2026-03-06)
- Data growth modules added: targets, session templates, backfill importer, tutorial linker, collection report.
- Learning-side data expansion added: bootstrap + conservative derived examples.
- New scripts added: `data_backfill.py`, `data_report.py`, `bootstrap_examples.py`.
- CLI commands added: `data-targets`, `data-report`, `data-backfill`, `bootstrap-examples`.


## Cost-Control Update (2026-03-07)
- Provider routing is now local-first, cache-aware, offline-aware, and budget-gated.
- Prompt cache is now persisted locally under `data/cache/prompts/`.
- Token budget is now persisted locally so CLI status/reset commands remain explicit and auditable.
- Remote providers remain explicit opt-in only and never bypass offline mode.
