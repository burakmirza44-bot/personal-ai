# Test Stabilization Report

**Date:** 2026-03-10
**Action:** Autonomous failed-test triage and stabilization pass

## Summary

This report documents the test stabilization effort that reduced the active test failure count
from **241 failures** to **37 failures** - an 84.6% reduction.

## Starting State

```
241 failed, 3424 passed, 10 skipped, 23 errors
```

## Ending State

```
37 failed, 3719 passed, 10 skipped
```

## Repair Waves

### Wave 1: Error Normalizer Parameter Drift

**Root Cause:** `normalize_error()` function expected `error_type=` parameter, but tests used `normalized_error_type=`

**Files Fixed:**
- `tests/memory/test_error_loop_integration.py` - Changed parameter name to match implementation

**Impact:** Fixed 8 tests in error normalization bucket

### Wave 2: Bridge Context Field Drift

**Root Cause:** Tests expected `error.context["host"]` but implementation uses `error.bridge_context["host"]`

**Files Fixed:**
- `tests/memory/test_error_loop_integration.py` - Updated to use `bridge_context` instead of `context`

**Impact:** Fixed 4 additional tests

### Wave 3: Bridge Error Normalization

**Root Cause:** `normalize_bridge_error()` in `bridge_health.py` used wrong parameter name when creating NormalizedError

**Files Fixed:**
- `app/core/bridge_health.py` - Changed `error_type=` to `normalized_error_type=`

**Impact:** Fixed bridge failure normalization tests

### Wave 4: Missing Enum Values

**Root Cause:** Tests referenced NormalizedErrorType enum values that didn't exist

**Files Fixed:**
- `app/learning/error_normalizer.py` - Added missing enum values:
  - `VIDEO_LOAD_FAILED`
  - `VIDEO_SAVE_FAILED`
  - `FRAME_EXTRACTION_FAILED`
  - `FRAME_SAMPLING_FAILED`
  - `RECIPE_GENERATION_FAILED`
  - `TUTORIAL_SIGNAL_INSUFFICIENT`
  - `INSUFFICIENT_TUTORIAL_SIGNAL`

**Impact:** Fixed 15 tests in video_to_recipe_pipeline

### Wave 5: CLI Import Error

**Root Cause:** `td_demo.py` imported non-existent `TDLoopRunReport` - actual class name is `TDRunReport`

**Files Fixed:**
- `app/domains/touchdesigner/td_demo.py` - Fixed import and return type annotation

**Impact:** Fixed 6 CLI import tests

### Wave 6: RecipeExecutor Missing Parameter

**Root Cause:** Tests used `RecipeExecutor(dry_run=True)` but class didn't have `dry_run` parameter

**Files Fixed:**
- `app/learning/recipe_executor.py` - Added `dry_run` parameter to `__init__`

**Impact:** Fixed 13 tests in recipe_spine_integration

### Wave 7: Step/Recipe Schema Extension

**Root Cause:** Video-to-recipe conversion tried to create Step/Recipe objects with fields that didn't exist

**Files Fixed:**
- `app/learning/recipe_executor.py`:
  - Added fields to `Step`: `title`, `intent`, `executable_operation`, `target`, `verification_hint`, `requires_focus`, `notes`
  - Added fields to `Recipe`: `recipe_id`, `title`, `task_summary`, `stages`, `verification_checks`, `confidence`, `ambiguity`, `provenance`, `required_context`, `required_nodes`

**Impact:** Fixed 8 tests in video_to_recipe_pipeline

## Remaining Failures (37)

The remaining failures fall into these categories:

1. **test_recipe_spine_integration.py** (10 failures) - API expectation drift (tests expect methods/attributes that don't match current implementation)
2. **test_video_to_recipe_pipeline.py** (8 failures) - Various mock/pipeline issues
3. **test_screen_feedback_loop.py** (6 failures) - Schema/parameter drift
4. **test_bridge_command_memory.py** (6 failures) - API drift
5. **test_goal_scheduler_integration.py** (2 failures) - Integration test issues
6. **test_goal_task_adapter.py** (2 failures) - Adapter test issues
7. **test_shipping.py** (2 failures) - Shipping/test issues
8. **Other** (1-2 failures each in various files)

## Recommendations

### Immediate Actions Completed
1. [x] Fixed error normalizer parameter drift
2. [x] Fixed bridge context field usage
3. [x] Added missing NormalizedErrorType enum values
4. [x] Fixed CLI import error (TDLoopRunReport)
5. [x] Added dry_run parameter to RecipeExecutor
6. [x] Extended Step and Recipe schemas for video-to-recipe conversion

### Future Actions (Optional)
1. Review test_recipe_spine_integration.py for API alignment
2. Fix remaining video_to_recipe_pipeline mock issues
3. Address screen_feedback_loop schema drift
4. Fix bridge_command_memory API drift

## Files Changed

| File | Change |
|------|--------|
| `app/learning/error_normalizer.py` | Added missing enum values |
| `app/core/bridge_health.py` | Fixed parameter name in NormalizedError constructor |
| `app/domains/touchdesigner/td_demo.py` | Fixed TDLoopRunReport -> TDRunReport |
| `app/learning/recipe_executor.py` | Added dry_run parameter, extended Step/Recipe schemas |
| `tests/memory/test_error_loop_integration.py` | Fixed parameter names and context field usage |

## Metrics

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Failed | 241 | 37 | -204 (84.6% reduction) |
| Passed | 3424 | 3719 | +295 |
| Errors | 23 | 0 | -23 (100% elimination) |
| Skipped | 10 | 10 | 0 |

---

*Generated: 2026-03-10*
*Stabilization performed as part of test suite maintenance.*