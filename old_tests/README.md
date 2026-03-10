# old_tests/ - ARCHIVE DIRECTORY

**Status: ARCHIVE ONLY - NOT PART OF ACTIVE TEST SUITE**

This directory contains legacy/archived test files that have been superseded by
tests in the main `tests/` directory. These tests are **excluded from normal
pytest discovery** and should not be run as part of regular development.

## Archive Policy

- `tests/` is the **single source of truth** for active tests
- `old_tests/` is preserved for historical reference only
- No new tests should be added to this directory
- Tests here may be outdated, broken, or have better equivalents in `tests/`

## Running Archived Tests (If Needed)

To explicitly run archived tests:

```bash
# Run specific archived test
pytest old_tests/test_specific_file.py

# Run all archived tests (not recommended)
pytest old_tests/
```

## Duplicate Mapping

| Archived File | Active Equivalent |
|--------------|-------------------|
| `old_tests/test_action_*.py` | `tests/agent_core/test_action_*.py` or `tests/learning/test_action_*.py` |
| `old_tests/test_backend_*.py` | `tests/agent_core/test_backend_*.py` |
| `old_tests/test_houdini_*.py` | `tests/domains/houdini/test_houdini_*.py` |
| `old_tests/test_td_*.py` | `tests/domains/touchdesigner/test_td_*.py` |
| `old_tests/test_memory_*.py` | `tests/memory/test_memory_*.py` |
| `old_tests/memory/` | `tests/memory/runtime_integration/` |
| ... and 200+ more files | |

## Unique Files

The following files exist ONLY in old_tests/ (no active equivalent):

- `test_td_webserver_handler.py` - **BROKEN** (missing dependency file)

## Statistics

- Total archived test files: ~211
- Files with active equivalents: ~210
- Unique archived files: 1 (broken)
- Active tests (tests/): ~271

## Cleanup Date

This archive was established on 2026-03-10 during test suite cleanup.

See `TEST_CLEANUP_MANIFEST.md` in the repo root for full details.