# Personal AI

Personal AI is a **local-first autonomous execution platform** for TouchDesigner and Houdini, evolving into a workflow-learning computer operator.

## Source Of Truth
- `AGENTS.md` defines non-negotiable implementation behavior.
- `progress.md` defines active phase roadmap and priorities.
- `docs/SYSTEM_MAP.md` defines current system architecture.
- `TD_DATASET_SPEC.md` and `HOUDINI_DATASET_SPEC.md` define domain dataset policies.

## What This Is Right Now
- A **fully integrated autonomous execution platform** with 6-stage loop (OBSERVE→RETRIEVE→CHOOSE→EXECUTE→VERIFY→PROMOTE)
- A **TouchDesigner-first** specialist with **complete Houdini parity**
- Bridge executors for live TD (port 9988) and Houdini (port 9989) communication
- Goal-driven self-improvement with signal detection and prioritization
- Memory runtime with enhanced retrieval and ranking
- Checkpoint/resume lifecycle for long-running tasks
- Fine-tune preparation with 47K TD + 82K Houdini training examples ready

## Current Status (2026-03-10)
- ✅ Autonomous Loop Phase 2: Sleep/poll, health monitoring, goal consumption
- ✅ Bridge Executors: TDBridgeExecutor and HoudiniBridgeExecutor fully implemented
- ✅ Goal Generator: Signal detection, prioritization, goal store
- ✅ Memory Runtime: Enhanced retrieval with ranking
- ✅ Checkpoint/Resume: Full lifecycle with boundary detection
- ⏳ Fine-tune Training: Data ready, GPU required
- ⏳ End-to-end Validation: Benchmarks pending

## Domain Expansion Order
1. ✅ TouchDesigner (complete)
2. ✅ Houdini (complete)
3. Python/self-improvement infrastructure
4. Personal assistant operations
5. Later: Unreal Engine 5
6. Later: Unity

## Quick Start
```powershell
cd D:\personal-ai
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Check system status
python -m app.main status

# Run tests
python -m pytest tests/ -q

# Start GUI
python -m gui.main

# Generate goals from current state
python -m app.goal_generator.service
```

## CLI Commands
```bash
# System status
python -m app.main status
python -m app.main agents
python -m app.main domains

# TouchDesigner
python -m app.main td-status
python -m app.main td-state-summary

# Houdini
python -m app.main houdini-status

# Offline check
python -m app.main offline-check

# OCR status
python -m app.cli ocr-status
```

## Architecture
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
└─────────────────────────────────────────────────────────────────┘
```

## Testing
```bash
# Run all tests
python -m pytest tests/ -q

# Run specific test categories
python -m pytest tests/agent_core/ -v
python -m pytest tests/domains/ -v
python -m pytest tests/learning/ -v
```

## Model Configuration
- Default reasoning model: `qwen3:14b` (Ollama)
- Vision model: `qwen3-vl:30b`
- Fast model: `qwen3:4b`
- Provider priority: **Ollama → Rule-based → Gemini → OpenAI** (fallback only)

## Scope Boundary
- Video learning is partially implemented (frame extraction, OCR, action inference)
- Real computer-use automation is implemented with safety bounds
- Uncontrolled autonomy is **not implemented and not allowed**
- All execution is bounded with explicit stop conditions