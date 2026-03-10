# Test Suite Cleanup Manifest

**Date:** 2026-03-10
**Action:** Test suite standardization - establish single source of truth

## Summary

This document records the test suite cleanup that established `tests/` as the
single active test source of truth and `old_tests/` as an archive directory.

## Changes Made

### 1. Discovery Policy Update

**File:** `pyproject.toml`

**Before:**
```toml
[tool.pytest.ini_options]
testpaths = ["tests", "old_tests"]
```

**After:**
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--ignore=old_tests"
```

**Effect:** Normal pytest discovery now only sweeps `tests/` (271 files) instead
of both directories (482 files combined).

### 2. Archive Marker Created

**File:** `old_tests/README.md`

Documents the archive status and provides guidance for future maintainers.

## Duplicate Analysis

### Statistics

| Category | Count |
|----------|-------|
| Total files in `tests/` | 271 |
| Total files in `old_tests/` | 211 |
| Duplicate files (exist in both) | 210 |
| Unique to `old_tests/` | 1 |
| Unique to `tests/` | 41 |

### Duplicate Mapping by Category

#### agent_core (Duplicates)
| old_tests/ | tests/ |
|------------|--------|
| test_action_executor_live.py | tests/agent_core/ |
| test_action_inference.py | tests/agent_core/ |
| test_agent_loop.py | tests/agent_core/ |
| test_agent_registry.py | tests/agent_core/ |
| test_backend_policy.py | tests/agent_core/ |
| test_backend_result.py | tests/agent_core/ |
| test_backend_selector.py | tests/agent_core/ |
| test_backfill_importer.py | tests/agent_core/ |
| test_cache_store.py | tests/agent_core/ |
| test_collection_report.py | tests/agent_core/ |
| test_data_bootstrap.py | tests/agent_core/ |
| test_data_targets.py | tests/agent_core/ |
| test_decomposition_spine.py | tests/agent_core/ |
| test_decomposition_tree.py | tests/agent_core/ |
| test_decomposition_verifier.py | tests/agent_core/ |
| test_feedback_loop.py | tests/agent_core/ |
| test_graph_plan.py | tests/agent_core/ |
| test_graph_stage_budget.py | tests/agent_core/ |
| test_graph_stop_policy.py | tests/agent_core/ |
| test_graph_visual_parser.py | tests/agent_core/ |
| test_input_executor.py | tests/agent_core/ |
| test_interface_contracts.py | tests/agent_core/ |
| test_killswitch.py | tests/agent_core/ |
| test_long_horizon_plan.py | tests/agent_core/ |
| test_next_action_policy.py | tests/agent_core/ |
| test_partial_checkpoint.py | tests/agent_core/ |
| test_patch_sandbox.py | tests/agent_core/ |
| test_plan_resume.py | tests/agent_core/ |
| test_plan_tracker.py | tests/agent_core/ |
| test_plan_verifier.py | tests/agent_core/ |
| test_prompt_cache.py | tests/agent_core/ |
| test_quality_gate.py | tests/agent_core/ |
| test_recipe_executor.py | tests/agent_core/ |
| test_recipe_spine_adapter.py | tests/agent_core/ |
| test_recipe_spine_integration.py | tests/agent_core/ |
| test_rollback_manager.py | tests/agent_core/ |
| test_runtime_benchmark.py | tests/agent_core/ |
| test_schema_contract.py | tests/agent_core/ |
| test_schema_validator.py | tests/agent_core/ |
| test_shadow_mode.py | tests/agent_core/ |
| test_spine_benchmarks.py | tests/agent_core/ |
| test_state_extractor.py | tests/agent_core/ |
| test_subgoal_decomposer.py | tests/agent_core/ |
| test_subtask_expander.py | tests/agent_core/ |
| test_task_decomposition.py | tests/agent_core/ |
| test_task_router.py | tests/agent_core/ |
| test_task_runner.py | tests/agent_core/ |
| test_task_runner_memory.py | tests/agent_core/ |
| test_trace_dataset.py | tests/agent_core/ |
| test_trace_events.py | tests/agent_core/ |
| test_trace_filter.py | tests/agent_core/ |
| test_trace_finetune_pipeline.py | tests/agent_core/ |
| test_trace_supervision.py | tests/agent_core/ |
| test_visual_checks.py | tests/agent_core/ |
| test_visual_verifier.py | tests/agent_core/ |
| test_window_guard.py | tests/agent_core/ |

#### core (Duplicates)
| old_tests/ | tests/ |
|------------|--------|
| test_cli_imports.py | tests/core/ |
| test_config.py | tests/core/ |
| test_imports.py | tests/core/ |
| test_improvement_policy.py | tests/core/ |
| test_improvement_report.py | tests/core/ |
| test_improvement_scoring.py | tests/core/ |
| test_offline_policy.py | tests/core/ |
| test_privacy_scrubber.py | tests/core/ |
| test_security.py | tests/core/ |
| test_seed_loader.py | tests/core/ |
| test_seed_scheduler.py | tests/core/ |
| test_self_improvement_loop.py | tests/core/ |
| test_success_patterns.py | tests/core/ |
| test_success_promoter.py | tests/core/ |
| test_token_budget.py | tests/core/ |

#### domains/houdini (Duplicates)
| old_tests/ | tests/ |
|------------|--------|
| test_houdini_action_inference.py | tests/domains/houdini/ |
| test_houdini_agent_loop.py | tests/domains/houdini/ |
| test_houdini_bridge_server.py | tests/domains/houdini/ |
| test_houdini_complex_graph_builder.py | tests/domains/houdini/ |
| test_houdini_complex_verifier.py | tests/domains/houdini/ |
| test_houdini_execution_loop.py | tests/domains/houdini/ |
| test_houdini_graph_planner.py | tests/domains/houdini/ |
| test_houdini_graph_state.py | tests/domains/houdini/ |
| test_houdini_graph_verifier.py | tests/domains/houdini/ |
| test_houdini_live_commands.py | tests/domains/houdini/ |
| test_houdini_live_protocol.py | tests/domains/houdini/ |
| test_houdini_long_horizon_planner.py | tests/domains/houdini/ |
| test_houdini_multi_layer_graph_builder.py | tests/domains/houdini/ |
| test_houdini_next_action_candidates.py | tests/domains/houdini/ |
| test_houdini_retry_policy.py | tests/domains/houdini/ |
| test_houdini_scene_patterns.py | tests/domains/houdini/ |
| test_houdini_state_extractor.py | tests/domains/houdini/ |
| test_houdini_task_decomposition.py | tests/domains/houdini/ |
| test_houdini_verifier.py | tests/domains/houdini/ |

#### domains/touchdesigner (Duplicates)
| old_tests/ | tests/ |
|------------|--------|
| test_td_bridge_server_module.py | tests/domains/touchdesigner/ |
| test_td_demo.py | tests/domains/touchdesigner/ |
| test_td_execution_loop.py | tests/domains/touchdesigner/ |
| test_td_first_e2e.py | tests/domains/touchdesigner/ |
| test_td_graph_planner.py | tests/domains/touchdesigner/ |
| test_td_graph_state.py | tests/domains/touchdesigner/ |
| test_td_graph_verifier.py | tests/domains/touchdesigner/ |
| test_td_input_executor.py | tests/domains/touchdesigner/ |
| test_td_live_commands.py | tests/domains/touchdesigner/ |
| test_td_live_protocol.py | tests/domains/touchdesigner/ |
| test_td_long_horizon_planner.py | tests/domains/touchdesigner/ |
| test_td_metadata_layers.py | tests/domains/touchdesigner/ |
| test_td_multi_layer_graph_builder.py | tests/domains/touchdesigner/ |
| test_td_retry_policy.py | tests/domains/touchdesigner/ |
| test_td_routing_policy.py | tests/domains/touchdesigner/ |
| test_td_routing_selector.py | tests/domains/touchdesigner/ |
| test_td_screen_observer.py | tests/domains/touchdesigner/ |
| test_td_task_decomposition.py | tests/domains/touchdesigner/ |
| test_td_ui_guard.py | tests/domains/touchdesigner/ |
| test_td_ui_protocol.py | tests/domains/touchdesigner/ |
| test_td_verifier.py | tests/domains/touchdesigner/ |
| test_td_window_guard.py | tests/domains/touchdesigner/ |

#### integrations (Duplicates)
| old_tests/ | tests/ |
|------------|--------|
| test_model_registry.py | tests/integrations/ |
| test_ollama_client.py | tests/integrations/ |
| test_ollama_default_provider.py | tests/integrations/ |
| test_ollama_runtime_integration.py | tests/integrations/ |
| test_provider_audit.py | tests/integrations/ |
| test_provider_fallback_chain.py | tests/integrations/ |
| test_provider_router.py | tests/integrations/ |

#### learning (Duplicates)
| old_tests/ | tests/ |
|------------|--------|
| test_action_prediction_dataset.py | tests/learning/ |
| test_action_prediction_eval.py | tests/learning/ |
| test_action_prediction_features.py | tests/learning/ |
| test_action_prediction_model.py | tests/learning/ |
| test_action_sequence_extractor.py | tests/learning/ |
| test_action_supervision.py | tests/learning/ |
| test_baseline_learner.py | tests/learning/ |
| test_dataset_builder.py | tests/learning/ |
| test_domain_finetune_runner.py | tests/learning/ |
| test_evaluator_gate.py | tests/learning/ |
| test_finetune_examples.py | tests/learning/ |
| test_finetune_export.py | tests/learning/ |
| test_finetune_filter.py | tests/learning/ |
| test_finetune_manifest.py | tests/learning/ |
| test_finetune_runner.py | tests/learning/ |
| test_intent_dataset.py | tests/learning/ |
| test_intent_inference.py | tests/learning/ |
| test_inverse_dynamics.py | tests/learning/ |
| test_inverse_dynamics_video.py | tests/learning/ |
| test_inverse_labeling.py | tests/learning/ |
| test_learning_readiness.py | tests/learning/ |
| test_online_learning_loop.py | tests/learning/ |
| test_rag_chunker.py | tests/learning/ |
| test_rag_context_builder.py | tests/learning/ |
| test_rag_index.py | tests/learning/ |
| test_rag_retriever.py | tests/learning/ |
| test_screen_dataset.py | tests/learning/ |
| test_screen_learning.py | tests/learning/ |
| test_trace_dataset.py | tests/learning/ |
| test_trace_finetune_pipeline.py | tests/learning/ |
| test_trace_supervision.py | tests/learning/ |
| test_training_readiness.py | tests/learning/ |
| test_video_intent_dataset.py | tests/learning/ |

#### memory (Duplicates)
| old_tests/ | tests/ |
|------------|--------|
| test_bridge_health_integration.py | tests/memory/ |
| test_bridge_command_memory.py | tests/memory/ |
| test_error_loop_integration.py | tests/memory/ |
| test_error_memory.py | tests/memory/ |
| test_memory_runtime_integration.py | tests/memory/ |
| test_memory_store.py | tests/memory/ |
| test_retry_memory.py | tests/memory/ |
| test_retry_strategy.py | tests/memory/ |
| memory/runtime_integration/* | tests/memory/runtime_integration/* |

#### recording (Duplicates)
| old_tests/ | tests/ |
|------------|--------|
| test_frame_change_detector.py | tests/recording/ |
| test_frame_extractor.py | tests/recording/ |
| test_frame_sampler.py | tests/recording/ |
| test_ocr_engine.py | tests/recording/ |
| test_ocr_pipeline.py | tests/recording/ |
| test_screen_capture.py | tests/recording/ |
| test_screen_dataset.py | tests/recording/ |
| test_screen_example.py | tests/recording/ |
| test_screen_feedback_loop.py | tests/recording/ |
| test_screen_labeling.py | tests/recording/ |
| test_screen_learning.py | tests/recording/ |
| test_screen_observer.py | tests/recording/ |
| test_screen_patterns.py | tests/recording/ |
| test_session_cli_flow.py | tests/recording/ |
| test_session_models.py | tests/recording/ |
| test_session_recorder.py | tests/recording/ |
| test_session_runtime.py | tests/recording/ |
| test_session_store.py | tests/recording/ |
| test_ui_detection.py | tests/recording/ |
| test_ui_locator.py | tests/recording/ |
| test_ui_templates.py | tests/recording/ |
| test_video_action_extractor.py | tests/recording/ |
| test_video_intent_dataset.py | tests/recording/ |
| test_video_screen_understanding.py | tests/recording/ |
| test_video_source.py | tests/recording/ |
| test_video_to_recipe_pipeline.py | tests/recording/ |

#### web_ingest (Duplicates)
| old_tests/ | tests/ |
|------------|--------|
| test_auto_fetch.py | tests/web_ingest/ |
| test_auto_fetch_runner.py | tests/web_ingest/ |
| test_crawl_report.py | tests/web_ingest/ |
| test_crawl_resume.py | tests/web_ingest/ |
| test_crawl_state.py | tests/web_ingest/ |
| test_crawler.py | tests/web_ingest/ |
| test_discovery_queue.py | tests/web_ingest/ |
| test_docs_ingest.py | tests/web_ingest/ |
| test_fetch_policy.py | tests/web_ingest/ |
| test_normalizer.py | tests/web_ingest/ |
| test_provenance.py | tests/web_ingest/ |
| test_quality_gate_web.py | tests/web_ingest/ |
| test_source_registry.py | tests/web_ingest/ |
| test_tutorial_ingest.py | tests/web_ingest/ |
| test_tutorial_linker.py | tests/web_ingest/ |
| test_tutorial_metadata.py | tests/web_ingest/ |
| test_url_canonicalizer.py | tests/web_ingest/ |
| test_url_policy.py | tests/web_ingest/ |
| test_web_ingest_integration.py | tests/web_ingest/ |

## Unique Files

### Only in old_tests/ (Archive-Only)

| File | Status | Notes |
|------|--------|-------|
| test_td_webserver_handler.py | BROKEN | Missing dependency file (tests/domains/scripts/td/td_webserver_handler.py) |

### Only in tests/ (Active-Only)

These are newer test modules that have no archived equivalent:

| File | Category |
|------|----------|
| test_inference_orchestrator.py | Core - Local-first inference |
| test_houdini_first_e2e.py | Demo |
| test_context_enricher.py | Fusion |
| test_cross_validator.py | Fusion |
| test_fused_state.py | Fusion |
| test_fusion_cache.py | Fusion |
| test_fusion_config.py | Fusion |
| test_fusion_engine.py | Fusion |
| test_inconsistency_detector.py | Fusion |
| test_integration_fusion.py | Fusion |
| test_situation_builder.py | Fusion |
| test_spatial_mapper.py | Fusion |
| test_temporal_sync.py | Fusion |
| test_ui_state_inferrer.py | Fusion |
| test_visual_bridge_mapper.py | Fusion |
| test_decider.py | Orchestration |
| test_error_gate.py | Orchestration |
| test_executor.py | Orchestration |
| test_health_reporter.py | Orchestration |
| test_intake.py | Orchestration |
| test_lifecycle.py | Orchestration |
| test_memory_gate.py | Orchestration |
| test_persist_gate.py | Orchestration |
| test_plan_gate.py | Orchestration |
| test_result.py | Orchestration |
| test_router.py | Orchestration |
| test_spine_integration.py | Orchestration |
| test_verifier.py | Orchestration |
| test_autonomous_loop.py | Core |
| test_checkpoint_integration.py | Core |
| test_memory_retrieval.py | Core |
| test_nexus_launcher.py | Core |
| test_task_scheduler.py | Core |
| test_channel.py | Verification |
| test_confidence_scorer.py | Verification |
| test_conflict_resolver.py | Verification |
| test_integration_verification.py | Verification |
| test_merger.py | Verification |
| test_partial_result.py | Verification |
| test_result_normalizer.py | Verification |
| test_strategy_selector.py | Verification |
| test_verification_config.py | Verification |

## Verification

### Tests Run After Cleanup

```bash
pytest tests/ --tb=short
# Result: 570+ tests passed (core suite)
# Result: 35 new inference orchestrator tests passed
```

### Critical Areas Verified

- [x] Orchestration spine integration
- [x] Memory/runtime integration
- [x] Bridge health checks
- [x] Error loop integration
- [x] Provider/Ollama local-first routing (new)
- [x] Verification merger/conflict logic
- [x] Houdini execution/planning
- [x] TouchDesigner routing/execution
- [x] Recipe executor/spine
- [x] Recording pipelines
- [x] Learning/finetune prep

## Recommendations

### Immediate Actions (Completed)
1. [x] Update pytest discovery to exclude old_tests
2. [x] Add archive README to old_tests
3. [x] Create cleanup manifest

### Future Actions (Optional)
1. Consider deleting old_tests/ after a grace period (e.g., 3-6 months)
2. Fix or remove `test_td_webserver_handler.py` (broken dependency)
3. Review any CI scripts that might still reference old_tests

## Files Changed

| File | Change |
|------|--------|
| pyproject.toml | Updated testpaths, added ignore for old_tests |
| old_tests/README.md | Created archive documentation |
| TEST_CLEANUP_MANIFEST.md | Created this manifest |

---

*Generated: 2026-03-10*
*Cleanup performed as part of test suite standardization.*