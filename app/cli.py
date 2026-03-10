"""Command-line interface for Personal AI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from app.agent_core.screen_capture import capture_active_window, capture_fullscreen, capture_monitor
from app.agent_core.screen_observer import ScreenObserver
from app.config import load_config
from app.core.agent_registry import build_default_registry
from app.core.graph_report import summarize_graph_report
from app.core.graph_stop_policy import GraphRunState, GraphTaskContract, GraphStopPolicy
from app.core.memory_store import build_default_memory_store
from app.core.offline_policy import OfflinePolicy
from app.core.provider_audit import build_default_audit
from app.core.prompt_cache import build_default_prompt_cache
from app.core.provider_router import build_default_router
from app.core.task_runner import run_task
from app.core.token_budget import build_default_token_budget
from app.domains import build_domain_registry
from app.learning.error_normalizer import NormalizedErrorType
from app.learning.feedback_loop import create_default_feedback_loop
from app.learning.retry_memory import build_default_retry_memory_store
from app.learning.success_patterns import build_default_success_pattern_store
from app.domains.houdini.houdini_executor import HoudiniExecutor
from app.domains.houdini.houdini_graph_templates import list_houdini_template_ids
from app.domains.houdini.houdini_live_client import HoudiniLiveFileClient
from app.domains.touchdesigner.td_demo import build_first_td_demo_package, export_first_td_demo_assets
from app.domains.touchdesigner.td_execution_loop import TDExecutionLoop
from app.domains.touchdesigner.td_graph_templates import list_td_template_ids
from app.domains.touchdesigner.td_executor import TDExecutor
from app.domains.touchdesigner.td_knowledge import build_default_td_knowledge
from app.domains.touchdesigner.td_live_client import TDLiveClient
from app.domains.touchdesigner.td_retry_policy import TDRetrySettings
from app.domains.touchdesigner.td_ui_controller import TDUIController
from app.domains.touchdesigner.td_verifier import (
    build_basic_top_chain_expectation,
    summarize_verification,
    verification_input_from_live_response,
    verification_input_from_simulated_result,
    verify_basic_top_chain,
)
from app.domains.touchdesigner.td_tasks import build_basic_top_chain_demo_task
from app.integrations.ollama_client import OllamaClient
from app.learning.data_bootstrap import bootstrap_supervised_examples, load_canonical_jsonl
from app.recording.backfill_importer import scan_for_backfill_candidates, write_backfill_staging
from app.recording.collection_report import build_collection_report, write_collection_report
from app.recording.data_targets import DataTargets, coverage_summary
from app.recording.session_recorder import SessionRecorder
from app.recording.session_store import SessionStore
from app.recording.tutorial_metadata import TutorialMetadata, TutorialMetadataStore, dedupe_fetched_tutorial_metadata, new_tutorial_id
from app.web_ingest.auto_fetch import AutoFetchRunner as LegacyAutoFetchRunner, load_fetch_jobs
from app.web_ingest.auto_fetch_runner import AutoFetchRunner
from app.web_ingest.crawl_resume import resolve_resume_target
from app.web_ingest.crawl_state import CrawlStateStore
from app.web_ingest.crawler import CrawlConfig, SourceCrawler
from app.web_ingest.seed_loader import load_enabled_seeds
from app.web_ingest.seed_scheduler import SeedScheduler
from app.web_ingest.cache_store import CacheStore
from app.web_ingest.docs_ingest import DocsIngestor
from app.web_ingest.fetch_policy import build_default_fetch_policy
from app.web_ingest.source_registry import SourceRegistry
from app.web_ingest.tutorial_ingest import TutorialIngestor
from app.web_ingest.integration import (
    collect_ingested_records,
    build_tutorial_records_from_ingest,
    ingest_status,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="personal-ai", description="Personal AI staff CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show current system status")
    sub.add_parser("agents", help="List configured agent roles")
    sub.add_parser("domains", help="List enabled domains")

    houdini_do = sub.add_parser("houdini-do", help="Do a Houdini task via trial-and-error loop")
    houdini_do.add_argument("goal", help="What to do in Houdini (natural language)")
    houdini_do.add_argument("--context", default="/obj", help="Target Houdini context path")
    houdini_do.add_argument("--provider", default="gemini", choices=["gemini", "openai", "ollama"])
    houdini_do.add_argument("--attempts", type=int, default=3, help="Max retry attempts")

    memory_add = sub.add_parser("memory-add", help="Persist a memory item")
    memory_add.add_argument("content", help="Memory content")
    memory_add.add_argument("--tags", default="", help="Comma-separated tags")
    memory_add.add_argument("--domain", default="general", help="Memory domain")
    memory_add.add_argument("--source", default="", help="Optional memory source")
    memory_add.add_argument("--bucket", choices=["long_term", "short_term"], default="long_term", help="Target bucket")

    memory_list = sub.add_parser("memory-list", help="List recent memory items")
    memory_list.add_argument("--domain", default="", help="Optional domain filter")
    memory_list.add_argument("--limit", type=int, default=10, help="Number of items to show")
    memory_list.add_argument("--bucket", choices=["long_term", "short_term"], default="long_term", help="Target bucket")

    memory_search = sub.add_parser("memory-search", help="Search memory")
    memory_search.add_argument("--query", default="", help="Query text")
    memory_search.add_argument("--tags", default="", help="Comma-separated tags")
    memory_search.add_argument("--domain", default="", help="Optional domain filter")
    memory_search.add_argument("--bucket", choices=["long_term", "short_term"], default="long_term", help="Target bucket")

    sub.add_parser("memory-clear-short", help="Clear short-term memory bucket")

    memory_runtime_preview = sub.add_parser("memory-runtime-preview", help="Preview what memory would be injected at runtime")
    memory_runtime_preview.add_argument("--query", required=True, help="Query text to preview memory for")
    memory_runtime_preview.add_argument("--domain", default="", help="Optional domain filter")
    memory_runtime_preview.add_argument("--max-items", type=int, default=5, help="Max items to show per category")

    sub.add_parser("td-status", help="Show TouchDesigner specialization status")
    sub.add_parser("offline-check", help="Run offline policy check")
    sub.add_parser("td-demo-plan", help="Show first TD demo task and safe action plan")
    sub.add_parser("td-demo-export", help="Export first TD demo script to scripts/td/")

    live_plan = sub.add_parser("td-live-plan", help="Show structured live command payload for TD bridge")
    live_plan.add_argument("--network", default="/project1", help="Target TouchDesigner network path")

    live_send = sub.add_parser("td-live-send", help="Send structured command to localhost TD bridge")
    live_send.add_argument("--network", default="/project1", help="Target TouchDesigner network path")
    live_send.add_argument("--host", default="127.0.0.1", help="Bridge host")
    live_send.add_argument("--port", type=int, default=9988, help="Bridge port")
    live_send.add_argument("--timeout", type=float, default=3.0, help="Socket timeout seconds")

    td_ping = sub.add_parser("td-ping", help="Ping TouchDesigner bridge to check if it's running")
    td_ping.add_argument("--host", default="127.0.0.1", help="Bridge host")
    td_ping.add_argument("--port", type=int, default=9988, help="Bridge port")
    td_ping.add_argument("--timeout", type=float, default=2.0, help="Socket timeout seconds")

    td_inspect = sub.add_parser("td-inspect", help="Inspect a TouchDesigner network via bridge")
    td_inspect.add_argument("--network", default="/project1", help="Network path to inspect")
    td_inspect.add_argument("--host", default="127.0.0.1", help="Bridge host")
    td_inspect.add_argument("--port", type=int, default=9988, help="Bridge port")
    td_inspect.add_argument("--timeout", type=float, default=3.0, help="Socket timeout seconds")

    sub.add_parser("td-ui-plan", help="Print bounded TouchDesigner UI plan JSON")
    sub.add_parser("td-ui-dry-run", help="Run bounded TouchDesigner UI plan in dry-run mode")

    verify_demo = sub.add_parser("td-verify-demo", help="Verify basic demo result (simulated by default)")
    verify_demo.add_argument("--network", default="/project1", help="Expected target network")
    verify_demo.add_argument("--use-live-response", action="store_true", help="Verify using live bridge response")
    verify_demo.add_argument("--host", default="127.0.0.1", help="Bridge host for live verify")
    verify_demo.add_argument("--port", type=int, default=9988, help="Bridge port for live verify")
    verify_demo.add_argument("--timeout", type=float, default=3.0, help="Socket timeout seconds")

    run_loop = sub.add_parser("td-run-loop", help="Run bounded execute->verify->retry loop for basic demo")
    run_loop.add_argument("--network", default="/project1", help="Target network")
    run_loop.add_argument("--live", action="store_true", help="Use live bridge execution instead of simulation")
    run_loop.add_argument("--host", default="127.0.0.1", help="Bridge host")
    run_loop.add_argument("--port", type=int, default=9988, help="Bridge port")
    run_loop.add_argument("--timeout", type=float, default=3.0, help="Socket timeout seconds")
    run_loop.add_argument("--max-retries", type=int, default=1, help="Max bounded retries")

    td_graph_plan = sub.add_parser("td-graph-plan", help="Print bounded staged TouchDesigner graph plan")
    td_graph_plan.add_argument("--template", default="basic_top_chain", choices=list_td_template_ids(), help="TD graph template id")
    td_graph_plan.add_argument("--network", default="/project1", help="Target TouchDesigner network path")
    td_graph_plan.add_argument("--mode", default="create_new", choices=["create_new", "extend_existing", "repair_partial"], help="Planning mode")

    td_graph_verify = sub.add_parser("td-graph-verify", help="Verify TouchDesigner graph result payload against template")
    td_graph_verify.add_argument("--template", default="basic_top_chain", choices=list_td_template_ids(), help="TD graph template id")
    td_graph_verify.add_argument("--network", default="/project1", help="Target TouchDesigner network path")
    td_graph_verify.add_argument("--result-json", default="", help="Optional JSON file path with graph result payload")

    ask_cmd = sub.add_parser("ask", help="Ask a question and route to the right specialist via Ollama")
    ask_cmd.add_argument("query", help="Your question")
    ask_cmd.add_argument("--model", default=None, help="Ollama model (default: qwen3:4b)")

    sub.add_parser("ollama-status", help="Check Ollama connectivity and list available models")

    sub.add_parser("rag-build", help="Scan local docs/transcripts and build RAG index")
    rag_search = sub.add_parser("rag-search", help="Search local RAG index")
    rag_search.add_argument("query", help="Search query")
    rag_search.add_argument("--domain", default="", help="Domain filter (houdini/touchdesigner)")
    rag_search.add_argument("--top", type=int, default=5, help="Max results")
    sub.add_parser("rag-status", help="Show RAG index status")

    hou_plan = sub.add_parser("houdini-live-plan", help="Print bounded Houdini live command JSON")
    hou_plan.add_argument("--context", default="/obj", help="Target Houdini context path")

    hou_send = sub.add_parser("houdini-live-send", help="Send bounded Houdini command through local file bridge")
    hou_send.add_argument("--context", default="/obj", help="Target Houdini context path")
    hou_send.add_argument("--inbox", default=".bridge/houdini/inbox", help="Local bridge inbox directory")
    hou_send.add_argument("--outbox", default=".bridge/houdini/outbox", help="Local bridge outbox directory")
    hou_send.add_argument("--timeout", type=float, default=5.0, help="Wait timeout seconds for response file")
    hou_send.add_argument("--no-wait", action="store_true", help="Do not wait for response file")

    hou_ping = sub.add_parser("houdini-ping", help="Ping Houdini HTTP bridge to check if it's running")
    hou_ping.add_argument("--host", default="127.0.0.1", help="Bridge host")
    hou_ping.add_argument("--port", type=int, default=9989, help="Bridge port")
    hou_ping.add_argument("--timeout", type=float, default=2.0, help="Socket timeout seconds")

    hou_inspect = sub.add_parser("houdini-inspect", help="Inspect a Houdini context via HTTP bridge")
    hou_inspect.add_argument("--context", default="/obj", help="Context path to inspect")
    hou_inspect.add_argument("--host", default="127.0.0.1", help="Bridge host")
    hou_inspect.add_argument("--port", type=int, default=9989, help="Bridge port")
    hou_inspect.add_argument("--timeout", type=float, default=3.0, help="Socket timeout seconds")

    hou_graph_plan = sub.add_parser("houdini-graph-plan", help="Print bounded staged Houdini graph plan")
    hou_graph_plan.add_argument("--template", default="basic_sop_chain", choices=list_houdini_template_ids(), help="Houdini graph template id")
    hou_graph_plan.add_argument("--context", default="/obj", help="Target Houdini context path")
    hou_graph_plan.add_argument("--mode", default="create_new", choices=["create_new", "extend_existing", "repair_partial"], help="Planning mode")

    hou_graph_verify = sub.add_parser("houdini-graph-verify", help="Verify Houdini graph result payload against template")
    hou_graph_verify.add_argument("--template", default="basic_sop_chain", choices=list_houdini_template_ids(), help="Houdini graph template id")
    hou_graph_verify.add_argument("--context", default="/obj", help="Target Houdini context path")
    hou_graph_verify.add_argument("--result-json", default="", help="Optional JSON file path with graph result payload")


    sub.add_parser("houdini-benchmark-cold", help="Run cold runtime benchmark for Houdini basic_sop_chain")
    sub.add_parser("houdini-benchmark-warm", help="Run warm runtime benchmark for Houdini basic_sop_chain")
    sub.add_parser("houdini-benchmark-compare", help="Run cold+warm comparison and write runtime improvement report")

    monitor_cmd = sub.add_parser("screen-monitor", help="Ekrani anlik takip et, degisince vision modele sor (ESC ile dur)")
    monitor_cmd.add_argument("--interval", type=int, default=1000, help="Frame aralik ms (default: 1000)")
    monitor_cmd.add_argument("--threshold", type=float, default=2.0, help="Degisim esigi %% (default: 2.0)")
    monitor_cmd.add_argument("--no-vision", action="store_true", help="Vision analizi yapma, sadece degisim tespit et")
    monitor_cmd.add_argument("--vision-interval", type=float, default=3.0, help="Vision sorgu aralik saniye (default: 3)")
    monitor_cmd.add_argument("--prompt", default="Ekranda ne degisti? Hangi uygulama aktif, ne yapiliyor? Kisaca.", help="Vision prompt")
    monitor_cmd.add_argument("--duration", type=int, default=0, help="Kac saniye calis (0=ESC ile dur)")

    session_start = sub.add_parser("session-start", help="Start an explicit local recording session")
    session_start.add_argument("--domain", choices=["touchdesigner", "houdini"], required=True, help="Session domain")
    session_start.add_argument("--task-hint", default="manual_session", help="Short task hint")

    session_note = sub.add_parser("session-note", help="Append a manual note to active session")
    session_note.add_argument("text", help="Manual note text")

    session_shot = sub.add_parser("session-shot", help="Capture screenshot into active session")
    session_shot.add_argument("--enabled", action="store_true", help="Actually capture screenshot (off by default)")
    session_shot.add_argument("--label", default="shot", help="Screenshot label prefix")

    session_end = sub.add_parser("session-end", help="End active session")
    session_end.add_argument("--status", default="completed", choices=["completed", "failed", "cancelled"], help="Final session status")
    session_end.add_argument("--outcome", default="", help="Outcome label (succeeded/partial/failed)")
    session_end.add_argument("--summary", default="", help="Optional session summary text")

    sub.add_parser("session-status", help="Show active session pointer and location")

    session_list = sub.add_parser("session-list", help="List recent sessions")
    session_list.add_argument("--domain", choices=["touchdesigner", "houdini"], default="", help="Filter by domain")
    session_list.add_argument("--limit", type=int, default=10, help="Number of sessions to show")

    sub.add_parser("tutorial-dedupe", help="Archive duplicate fetched tutorial metadata by domain+url")

    tutorial_add = sub.add_parser("tutorial-add", help="Store tutorial metadata record")
    tutorial_add.add_argument("--domain", choices=["touchdesigner", "houdini"], required=True, help="Tutorial domain")
    tutorial_add.add_argument("--title", required=True, help="Tutorial title")
    tutorial_add.add_argument("--source-type", default="youtube", help="Source type (youtube/local/other)")
    tutorial_add.add_argument("--source-name", default="", help="Source name/channel")
    tutorial_add.add_argument("--duration", type=int, default=0, help="Duration in seconds")
    tutorial_add.add_argument("--topic-tags", default="", help="Comma-separated topic tags")
    tutorial_add.add_argument("--task-labels", default="", help="Comma-separated inferred task labels")
    tutorial_add.add_argument("--local-path", default="", help="Optional local file path")
    tutorial_add.add_argument("--url", default="", help="Optional URL reference")
    tutorial_add.add_argument("--notes", default="", help="Optional notes")

    session_link_tutorial = sub.add_parser("session-link-tutorial", help="Link tutorial metadata ID to active session")
    session_link_tutorial.add_argument("tutorial_id", help="Existing tutorial metadata ID")

    observe = sub.add_parser("screen-observe", help="Ekranı gör, vision modele sor")
    observe.add_argument("prompt", help="Vision modele sorulacak soru")
    observe.add_argument("--model", default="qwen3-vl:30b", help="Vision model")

    act_cmd = sub.add_parser("screen-act", help="Görevi ekranda uygula (klavye/mouse)")
    act_cmd.add_argument("task", help="Yapılacak görev")
    act_cmd.add_argument("--live", action="store_true", help="Gerçekten uygula (default: dry-run)")

    # MSS-based screen capture commands
    capture_screen = sub.add_parser("capture-screen", help="Capture fullscreen or monitor screenshot")
    capture_screen.add_argument("--monitor", type=int, default=0, help="Monitor index (0=all, 1=primary)")
    capture_screen.add_argument("--output-dir", default="./captures", help="Output directory")
    capture_screen.add_argument("--prefix", default="screen", help="Filename prefix")

    capture_window = sub.add_parser("capture-window", help="Capture active window (fallback to fullscreen if unavailable)")
    capture_window.add_argument("--output-dir", default="./captures", help="Output directory")
    capture_window.add_argument("--prefix", default="window", help="Filename prefix")

    observe_screen = sub.add_parser("observe-screen", help="Domain-aware screen observation")
    observe_screen.add_argument("--domain", default="generic", help="Domain hint (touchdesigner/houdini/generic)")
    observe_screen.add_argument("--output-dir", default="./captures", help="Output directory")
    observe_screen.add_argument("--prefer-active", action="store_true", help="Prefer active window capture")
    observe_screen.add_argument("--monitor", type=int, default=0, help="Monitor index for fullscreen fallback")

    # UI Element Detection commands
    ui_template_list = sub.add_parser("ui-template-list", help="List registered UI templates")
    ui_template_list.add_argument("--domain", default="", help="Filter by domain (touchdesigner/houdini/generic)")

    ui_detect = sub.add_parser("ui-detect", help="Find template(s) on current screen")
    ui_detect.add_argument("--template", default="", help="Single template name to find")
    ui_detect.add_argument("--templates", default="", help="Comma-separated template names")
    ui_detect.add_argument("--confidence", type=float, default=0.8, help="Match confidence threshold (0.0-1.0)")
    ui_detect.add_argument("--domain", default="", help="Search all templates in domain")
    ui_detect.add_argument("--active-window", action="store_true", help="Limit search to active window")

    ui_detect_image = sub.add_parser("ui-detect-image", help="Find template(s) in saved image")
    ui_detect_image.add_argument("--image", required=True, help="Path to image file")
    ui_detect_image.add_argument("--template", default="", help="Single template name to find")
    ui_detect_image.add_argument("--templates", default="", help="Comma-separated template names")
    ui_detect_image.add_argument("--confidence", type=float, default=0.8, help="Match confidence threshold (0.0-1.0)")

    # Task Decomposition commands
    task_decompose = sub.add_parser("task-decompose", help="Decompose goal into recursive subtasks")
    task_decompose.add_argument("--domain", required=True, choices=["touchdesigner", "houdini", "generic"], help="Task domain")
    task_decompose.add_argument("--goal", required=True, help="Goal to decompose")
    task_decompose.add_argument("--context", default="", help="Additional context")
    task_decompose.add_argument("--max-depth", type=int, default=3, help="Max decomposition depth")
    task_decompose.add_argument("--json", action="store_true", help="Output as JSON")

    task_decompose_tree = sub.add_parser("task-decompose-tree", help="Print decomposition tree structure")
    task_decompose_tree.add_argument("--domain", required=True, choices=["touchdesigner", "houdini", "generic"], help="Task domain")
    task_decompose_tree.add_argument("--goal", required=True, help="Goal to decompose")
    task_decompose_tree.add_argument("--max-depth", type=int, default=3, help="Max decomposition depth")

    task_decompose_next = sub.add_parser("task-decompose-next", help="Show next executable subtask")
    task_decompose_next.add_argument("--domain", required=True, choices=["touchdesigner", "houdini", "generic"], help="Task domain")
    task_decompose_next.add_argument("--goal", required=True, help="Goal to decompose")
    task_decompose_next.add_argument("--max-depth", type=int, default=3, help="Max decomposition depth")

    sub.add_parser("data-targets", help="Show current data collection target progress")

    data_report = sub.add_parser("data-report", help="Generate data collection report")
    data_report.add_argument("--json-out", default="reports/data_report/latest.json", help="JSON output path")
    data_report.add_argument("--md-out", default="reports/data_report/latest.md", help="Markdown output path")

    data_backfill = sub.add_parser("data-backfill", help="Scan artifacts and create backfill candidates")
    data_backfill.add_argument("--dry-run", action="store_true", help="Only print summary")
    data_backfill.add_argument("--staging", default="data/backfill/staging_candidates.jsonl", help="Staging JSONL path")

    bootstrap = sub.add_parser("bootstrap-examples", help="Bootstrap supervised examples from canonical data")
    bootstrap.add_argument("--dataset", default="data/datasets/current/canonical.jsonl", help="Canonical dataset path")
    bootstrap.add_argument("--out", default="data/datasets/current/supervised_bootstrap.jsonl", help="Output JSONL path")
    bootstrap.add_argument("--mode", choices=["original_only", "original_plus_derived"], default="original_plus_derived", help="Bootstrap mode")
# Memory runtime commands    memory_runtime_preview = sub.add_parser("memory-runtime-preview", help="Preview what memories would be injected for a task")    memory_runtime_preview.add_argument("--domain", required=True, choices=["touchdesigner", "houdini", "general"], help="Task domain")    memory_runtime_preview.add_argument("--query", required=True, help="Task query/description")    memory_runtime_preview.add_argument("--max-success", type=int, default=3, help="Max success patterns")    memory_runtime_preview.add_argument("--max-failure", type=int, default=3, help="Max failure patterns")    success_pattern_search = sub.add_parser("success-pattern-search", help="Search reusable successful patterns")    success_pattern_search.add_argument("--domain", default="", help="Domain filter")    success_pattern_search.add_argument("--query", default="", help="Search query")    success_pattern_search.add_argument("--max-items", type=int, default=5, help="Max results")    success_pattern_search.add_argument("--json", action="store_true", help="Output as JSON")    failure_pattern_search = sub.add_parser("failure-pattern-search", help="Search failure/error patterns to avoid")    failure_pattern_search.add_argument("--domain", default="", help="Domain filter")    failure_pattern_search.add_argument("--query", default="", help="Search query")    failure_pattern_search.add_argument("--max-items", type=int, default=5, help="Max results")    failure_pattern_search.add_argument("--json", action="store_true", help="Output as JSON")


    sub.add_parser("web-sources", help="List configured web ingest sources")

    fetch_docs = sub.add_parser("fetch-docs", help="Fetch bounded docs pages from allowlisted sources")
    fetch_docs.add_argument("--source-id", required=True, help="Registered source id")
    fetch_docs.add_argument("--urls", required=True, help="Comma-separated URL list")
    fetch_docs.add_argument("--max-pages", type=int, default=5, help="Max page fetch count")

    fetch_tutorials = sub.add_parser("fetch-tutorials", help="Fetch bounded tutorial page metadata")
    fetch_tutorials.add_argument("--source-id", required=True, help="Registered source id")
    fetch_tutorials.add_argument("--domain", choices=["touchdesigner", "houdini"], required=True, help="Tutorial domain")
    fetch_tutorials.add_argument("--urls", required=True, help="Comma-separated URL list")
    fetch_tutorials.add_argument("--notes", default="", help="Optional note attached to fetched metadata")

    fetch_url = sub.add_parser("fetch-url", help="Fetch one explicitly provided allowlisted URL")
    fetch_url.add_argument("--source-id", required=True, help="Registered source id")
    fetch_url.add_argument("--url", required=True, help="One URL")
    fetch_url.add_argument("--type", choices=["docs", "tutorial"], default="docs", help="Ingest type")
    fetch_url.add_argument("--domain", choices=["touchdesigner", "houdini"], default="touchdesigner", help="Domain for tutorial ingest")
    fetch_url.add_argument("--notes", default="", help="Optional tutorial note")

    sub.add_parser("web-cache-status", help="Show local web cache status")

    # Web ingest integration commands
    sub.add_parser("web-ingest-status", help="Show web ingest status and RAG readiness")

    web_rag_build = sub.add_parser("web-rag-build", help="Build RAG index from web ingest sources")
    web_rag_build.add_argument("--rebuild", action="store_true", help="Force full rebuild")

    web_rag_search = sub.add_parser("web-rag-search", help="Search web ingest content in RAG index")
    web_rag_search.add_argument("query", help="Search query")
    web_rag_search.add_argument("--domain", default="", help="Domain filter (houdini/touchdesigner)")
    web_rag_search.add_argument("--top", type=int, default=5, help="Max results")

    web_link_tutorials = sub.add_parser("web-link-tutorials", help="Link ingested tutorial records to tutorial metadata")
    web_link_tutorials.add_argument("--domain", default="", help="Optional domain filter")

    # Agent core commands
    td_shadow_start = sub.add_parser("td-shadow-start", help="Start explicit TD shadow observation session")
    td_shadow_start.add_argument("--network", default="/project1", help="Target network")

    sub.add_parser("td-shadow-stop", help="Stop active TD shadow session and print trace summary")

    td_state = sub.add_parser("td-state-summary", help="Print current structured TD state")
    td_state.add_argument("--network", default="/project1", help="Target network")
    td_state.add_argument("--live", action="store_true", help="Use live bridge (default: simulated)")

    td_infer = sub.add_parser("td-infer-last-action", help="Infer most likely last TD action from state transition")
    td_infer.add_argument("--network", default="/project1", help="Target network")

    td_next = sub.add_parser("td-next-action", help="Print ranked next safe TD action candidates")
    td_next.add_argument("--network", default="/project1", help="Target network")

    td_step = sub.add_parser("td-agent-step", help="Run one bounded TD observe->propose->execute->verify step")
    td_step.add_argument("--network", default="/project1", help="Target network")
    td_step.add_argument("--live", action="store_true", help="Use live bridge (default: dry-run)")

    td_run = sub.add_parser("td-agent-run", help="Run bounded multi-step TD agent loop")
    td_run.add_argument("--network", default="/project1", help="Target network")
    td_run.add_argument("--max-steps", type=int, default=3, help="Step cap (max 10)")
    td_run.add_argument("--max-retries", type=int, default=1, help="Retry cap per step")
    td_run.add_argument("--live", action="store_true", help="Use live bridge (default: dry-run)")

    hou_state = sub.add_parser("houdini-state-summary", help="Print current structured Houdini state")
    hou_state.add_argument("--context", default="/obj/geo1", help="Target Houdini context path")
    hou_state.add_argument("--live", action="store_true", help="Use live bridge (default: simulated)")

    hou_infer = sub.add_parser("houdini-infer-last-action", help="Infer most likely last Houdini action from state transition")
    hou_infer.add_argument("--context", default="/obj/geo1", help="Target Houdini context path")

    hou_next = sub.add_parser("houdini-next-action", help="Print ranked next safe Houdini action candidates")
    hou_next.add_argument("--context", default="/obj/geo1", help="Target Houdini context path")
    hou_next.add_argument("--task", default="", help="Optional task context hint")

    hou_step = sub.add_parser("houdini-agent-step", help="Run one bounded Houdini observe->propose->execute->verify step")
    hou_step.add_argument("--context", default="/obj/geo1", help="Target Houdini context path")
    hou_step.add_argument("--task-id", default="hou.sop.scatter_copy", help="Houdini task ID from catalog")
    hou_step.add_argument("--live", action="store_true", help="Use live bridge (default: dry-run)")

    hou_run = sub.add_parser("houdini-agent-run", help="Run bounded multi-step Houdini agent loop")
    hou_run.add_argument("--context", default="/obj/geo1", help="Target Houdini context path")
    hou_run.add_argument("--task-id", default="hou.sop.scatter_copy", help="Houdini task ID from catalog")
    hou_run.add_argument("--max-steps", type=int, default=3, help="Step cap (max 10)")
    hou_run.add_argument("--max-retries", type=int, default=1, help="Retry cap per step")
    hou_run.add_argument("--live", action="store_true", help="Use live bridge (default: dry-run)")

    fetch_auto = sub.add_parser("fetch-auto", help="Run bounded auto-fetch loop (press ESC to stop)")
    fetch_auto.add_argument("--jobs", required=True, help="Path to JSON job list")
    fetch_auto.add_argument("--max-cycles", type=int, default=3, help="Max bounded loop cycles")
    fetch_auto.add_argument("--interval", type=float, default=2.0, help="Seconds between cycles")
    fetch_auto.add_argument("--verbose", action="store_true", help="Print each URL fetch attempt and result")

    crawl_source = sub.add_parser("crawl-source", help="Run bounded deterministic crawl from one seed URL")
    crawl_source.add_argument("--source-id", required=True, help="Registered source id")
    crawl_source.add_argument("--url", required=True, help="Seed URL")
    crawl_source.add_argument("--max-pages", type=int, default=50, help="Max pages")
    crawl_source.add_argument("--max-depth", type=int, default=2, help="Max depth")
    crawl_source.add_argument("--skip-cached", action="store_true", default=True, help="Skip cached URLs")
    crawl_source.add_argument("--no-skip-cached", action="store_false", dest="skip_cached", help="Force refetch even when cached")
    crawl_source.add_argument("--include-transcripts", action="store_true", help="Optional transcript ingestion")
    crawl_source.add_argument("--report-out", default="", help="Optional report JSON path")

    run_auto_fetch = sub.add_parser("run-auto-fetch", help="Run enabled bounded seeds automatically")
    run_auto_fetch.add_argument("--seed-dir", default="data/web_ingest/seeds", help="Seed directory")
    run_auto_fetch.add_argument("--domain", default="", help="Optional domain filter")
    run_auto_fetch.add_argument("--source-id", default="", help="Optional source filter")
    run_auto_fetch.add_argument("--max-total-pages", type=int, default=0, help="Bound total pages across this explicit run")
    run_auto_fetch.add_argument("--max-pages-per-seed", type=int, default=0, help="Optional override per seed")
    run_auto_fetch.add_argument("--max-depth-per-seed", type=int, default=0, help="Optional override per seed")
    run_auto_fetch.add_argument("--skip-cached", action="store_true", default=True, help="Skip cached URLs")

    run_seed_batch = sub.add_parser("run-seed-batch", help="Run enabled crawl seeds")
    run_seed_batch.add_argument("--seed-dir", default="data/web_ingest/seeds", help="Seed directory")
    run_seed_batch.add_argument("--domain", default="", help="Optional domain filter")
    run_seed_batch.add_argument("--source-id", default="", help="Optional source filter")
    run_seed_batch.add_argument("--skip-cached", action="store_true", default=True, help="Skip cached URLs")

    crawl_resume = sub.add_parser("crawl-resume", help="Resume most recent incomplete crawl or one run_id")
    crawl_resume.add_argument("--run-id", default="", help="Optional explicit run id")
    crawl_resume.add_argument("--skip-cached", action="store_true", default=True, help="Skip cached URLs")

    sub.add_parser("crawl-stop", help="Create stop flag for running crawler")
    sub.add_parser("crawl-status", help="Show crawler state/report summary")

    # Provider router commands
    provider_route = sub.add_parser("provider-route", help="Show routing decision for a given task class")
    provider_route.add_argument("--task-class", default="complex_reasoning",
                                choices=["summarization", "retrieval_synthesis", "state_explanation",
                                         "next_action_suggestion", "graph_planning", "coding_patch",
                                         "verification_help", "complex_reasoning",
                                         "vision_like_interpretation"],
                                help="Task class to route")
    provider_route.add_argument("--domain", default="", help="Optional domain hint")
    provider_route.add_argument("--online", action="store_true", help="Enable online routing (default: offline)")
    provider_route.add_argument("--preferred-provider", default="openai",
                                choices=["rule_based", "cache_only", "local_default", "ollama", "openai", "gemini"],
                                help="Provider hint")
    provider_route.add_argument("--prompt", default="", help="Compact prompt or state summary for token/cache estimation")
    provider_route.add_argument("--file-id", action="append", default=[], help="Relevant file id/name for cache key")
    provider_route.add_argument("--template-version", default="v1", help="Prompt template version")
    provider_route.add_argument("--require-remote", action="store_true", help="Require remote if policy allows")

    sub.add_parser("token-budget-status", help="Show current token budget state")
    budget_reset = sub.add_parser("token-budget-reset", help="Reset token budget counters (dev/test use)")
    budget_reset.add_argument("--scope", choices=["task", "session", "daily", "all"], default="all", help="Budget scope to reset")
    sub.add_parser("prompt-cache-status", help="Show current prompt cache status")
    sub.add_parser("prompt-cache-clear", help="Clear prompt cache entries (dev/test use)")

    td_multigraph = sub.add_parser("td-multigraph-plan", help="Build bounded TD multi-layer graph plan")
    td_multigraph.add_argument("--chops", type=int, default=0, help="Target CHOP operator count")
    td_multigraph.add_argument("--tops", type=int, default=0, help="Target TOP operator count")
    td_multigraph.add_argument("--sops", type=int, default=0, help="Target SOP operator count")
    td_multigraph.add_argument("--goal", default="", help="Optional goal description")
    td_multigraph.add_argument("--json", action="store_true", help="Output full plan as JSON")

    hou_multigraph = sub.add_parser("houdini-multigraph-plan", help="Build bounded Houdini multi-layer graph plan")
    hou_multigraph.add_argument("--sops", type=int, default=0, help="Target SOP node count")
    hou_multigraph.add_argument("--vops", type=int, default=0, help="Target VOP node count")
    hou_multigraph.add_argument("--tops", type=int, default=0, help="Target TOP/PDG node count")
    hou_multigraph.add_argument("--goal", default="", help="Optional goal description")
    hou_multigraph.add_argument("--json", action="store_true", help="Output full plan as JSON")

    graph_stop = sub.add_parser("graph-stop-eval", help="Evaluate whether a graph run should continue, stop, or checkpoint")
    graph_stop.add_argument("--domain", choices=["touchdesigner", "houdini"], default="touchdesigner",
                            help="Domain context")
    graph_stop.add_argument("--nodes-created", type=int, default=0, help="Nodes created so far")
    graph_stop.add_argument("--steps-taken", type=int, default=0, help="Steps taken so far")
    graph_stop.add_argument("--retries", type=int, default=0, help="Retries so far")
    graph_stop.add_argument("--unchanged", type=int, default=0, help="Unchanged iteration count")
    graph_stop.add_argument("--elapsed", type=float, default=0.0, help="Elapsed seconds")
    graph_stop.add_argument("--max-nodes", type=int, default=50, help="Max node budget")
    graph_stop.add_argument("--max-steps", type=int, default=40, help="Max step budget")
    graph_stop.add_argument("--success", action="store_true", help="Declare goal reached")

    # OCR commands
    ocr_image = sub.add_parser("ocr-image", help="Run OCR on an image file")
    ocr_image.add_argument("--image", required=True, help="Path to image file")
    ocr_image.add_argument("--engine", choices=["tesseract", "easyocr"], default="tesseract", help="OCR engine")
    ocr_image.add_argument("--max-chars", type=int, default=500, help="Max chars for text output")

    ocr_status = sub.add_parser("ocr-status", help="Check OCR engine availability")

    observe_screen_ocr = sub.add_parser("observe-screen-ocr", help="Capture screenshot and run OCR")
    observe_screen_ocr.add_argument("--output-dir", default="./captures", help="Output directory")
    observe_screen_ocr.add_argument("--domain", default="generic", help="Domain hint")
    observe_screen_ocr.add_argument("--engine", choices=["tesseract", "easyocr"], default="tesseract", help="OCR engine")
    observe_screen_ocr.add_argument("--monitor", type=int, default=0, help="Monitor index (0=all)")
    observe_screen_ocr.add_argument("--max-chars", type=int, default=300, help="Max chars for OCR text")

    capture_window_ocr = sub.add_parser("capture-window-ocr", help="Capture active window and run OCR")
    capture_window_ocr.add_argument("--output-dir", default="./captures", help="Output directory")
    capture_window_ocr.add_argument("--domain", default="generic", help="Domain hint")
    capture_window_ocr.add_argument("--engine", choices=["tesseract", "easyocr"], default="tesseract", help="OCR engine")
    capture_window_ocr.add_argument("--max-chars", type=int, default=300, help="Max chars for OCR text")

    # Input executor commands
    sub.add_parser("input-status", help="Show input execution status and safety checks")

    sub.add_parser("input-dry-run", help="Run a safe example plan in dry-run mode (no real input)")

    input_execute = sub.add_parser("input-execute", help="Execute a safe example plan in real mode (requires --confirm)")
    input_execute.add_argument("--confirm", action="store_true", help="Explicitly confirm real execution")
    input_execute.add_argument("--app", choices=["touchdesigner", "houdini"], default="touchdesigner", help="Target application")

    input_test_action = sub.add_parser("input-test-action", help="Test a single input action (dry-run by default)")
    input_test_action.add_argument("--type", required=True,
                                   choices=["move_mouse", "left_click", "double_click", "key_press", "hotkey", "type_text", "wait"],
                                   help="Action type")
    input_test_action.add_argument("--x", type=int, default=0, help="X coordinate for mouse actions")
    input_test_action.add_argument("--y", type=int, default=0, help="Y coordinate for mouse actions")
    input_test_action.add_argument("--key", default="", help="Key for key_press action")
    input_test_action.add_argument("--keys", default="", help="Comma-separated keys for hotkey action")
    input_test_action.add_argument("--text", default="", help="Text for type_text action")
    input_test_action.add_argument("--duration", type=int, default=100, help="Duration in ms for wait action")
    input_test_action.add_argument("--live", action="store_true", help="Execute for real (dry-run by default)")
    input_test_action.add_argument("--app", choices=["touchdesigner", "houdini"], default="", help="Target application for focus check")

    # Feedback loop commands
    feedback_recent = sub.add_parser("feedback-recent", help="Show recent failure -> retry -> outcome records")
    feedback_recent.add_argument("--domain", default="", help="Optional domain filter")
    feedback_recent.add_argument("--limit", type=int, default=10, help="Number of records to show")

    retry_strategy_preview = sub.add_parser("retry-strategy-preview", help="Show chosen retry strategy for error")
    retry_strategy_preview.add_argument("--error", required=True, help="Error message to analyze")
    retry_strategy_preview.add_argument("--domain", required=True, choices=["touchdesigner", "houdini", "general"], help="Domain context")
    retry_strategy_preview.add_argument("--task-id", default="", help="Optional task ID")

    repair_pattern_search = sub.add_parser("repair-pattern-search", help="Search saved successful repair patterns")
    repair_pattern_search.add_argument("--domain", default="", help="Domain filter")
    repair_pattern_search.add_argument("--error-type", default="", help="Error type filter")
    repair_pattern_search.add_argument("--query", default="", help="Text search query")
    repair_pattern_search.add_argument("--limit", type=int, default=5, help="Max results")

    # Error memory commands (NEW)
    error_recent = sub.add_parser("error-recent", help="Show recent normalized errors from persistent memory")
    error_recent.add_argument("--domain", default="", help="Filter by domain (touchdesigner/houdini)")
    error_recent.add_argument("--limit", type=int, default=10, help="Number of errors to show")

    error_search = sub.add_parser("error-search", help="Search persisted error memory")
    error_search.add_argument("--domain", default="", help="Filter by domain")
    error_search.add_argument("--error-type", default="", help="Filter by normalized error type")
    error_search.add_argument("--task-id", default="", help="Filter by task ID")
    error_search.add_argument("--query", default="", help="Text search query")
    error_search.add_argument("--limit", type=int, default=5, help="Max results")

    # Screen learning commands
    screen_learn = sub.add_parser("screen-learn", help="Learn from a screen observation")
    screen_learn.add_argument("--image", required=True, help="Path to screenshot image")
    screen_learn.add_argument("--domain", required=True, choices=["touchdesigner", "houdini", "generic"], help="Domain")
    screen_learn.add_argument("--task", default="", help="Task identifier")
    screen_learn.add_argument("--session", default="", help="Session identifier")
    screen_learn.add_argument("--notes", default="", help="Optional notes")
    screen_learn.add_argument("--visible-nodes", default="", help="Comma-separated visible node names")
    screen_learn.add_argument("--source", default="manual", choices=["manual", "runtime_verification", "session_recording"], help="Source of observation")

    screen_dataset_status = sub.add_parser("screen-dataset-status", help="Show screen learning dataset status")
    screen_dataset_status.add_argument("--verbose", action="store_true", help="Show detailed breakdown")

    screen_patterns = sub.add_parser("screen-patterns", help="Show extracted screen patterns")
    screen_patterns.add_argument("--domain", default="", help="Filter by domain")
    screen_patterns.add_argument("--pattern-type", default="", help="Filter by type (success/failure/stage/output/error)")
    screen_patterns.add_argument("--limit", type=int, default=10, help="Max results")

    screen_label_image = sub.add_parser("screen-label-image", help="Label a screenshot without storing")
    screen_label_image.add_argument("--image", required=True, help="Path to screenshot image")
    screen_label_image.add_argument("--domain", default="", help="Domain hint")

    screen_update = sub.add_parser("screen-update", help="Run screen learning update cycle")
    screen_update.add_argument("--full", action="store_true", help="Run full update instead of quick")

    # Self-improvement commands
    self_improve_preview = sub.add_parser("self-improve-preview", help="Preview next improvement without applying")
    self_improve_preview.add_argument("--source", choices=["error_memory", "test_failures", "docs_drift"], default="error_memory", help="Source of improvement opportunities")

    self_improve_run = sub.add_parser("self-improve-run", help="Run one bounded self-improvement cycle")
    self_improve_run.add_argument("--auto-apply", action="store_true", help="Auto-apply low-risk patches that pass validation")
    self_improve_run.add_argument("--max-proposals", type=int, default=1, help="Maximum proposals per session")

    self_improve_review = sub.add_parser("self-improve-review", help="Review improvement proposals")
    self_improve_review.add_argument("--proposal-id", help="Review specific proposal")
    self_improve_review.add_argument("--latest", action="store_true", help="Review latest proposal")
    self_improve_review.add_argument("--pending", action="store_true", help="List pending proposals")
    self_improve_review.add_argument("--json", action="store_true", help="Output as JSON")

    self_improve_apply = sub.add_parser("self-improve-apply", help="Apply approved improvement")
    self_improve_apply.add_argument("--proposal-id", required=True, help="Proposal ID to apply")
    self_improve_apply.add_argument("--force", action="store_true", help="Force apply even without approval")
    self_improve_apply.add_argument("--dry-run", action="store_true", help="Show what would be done")

    self_improve_rollback = sub.add_parser("self-improve-rollback", help="Rollback applied improvement")
    self_improve_rollback.add_argument("--rollback-id", help="Rollback point ID")
    self_improve_rollback.add_argument("--latest", action="store_true", help="Rollback most recent")
    self_improve_rollback.add_argument("--improvement-id", help="Rollback by improvement ID")
    self_improve_rollback.add_argument("--reason", default="user_requested", help="Reason for rollback")
    self_improve_rollback.add_argument("--list", action="store_true", help="List active rollbacks")

    self_improve_history = sub.add_parser("self-improve-history", help="Show improvement history")
    self_improve_history.add_argument("--limit", type=int, default=10, help="Number of records to show")

    # Long-horizon planning commands
    plan_create = sub.add_parser("plan-create", help="Create a long-horizon plan from a goal")
    plan_create.add_argument("--domain", required=True, choices=["touchdesigner", "houdini"], help="Target domain")
    plan_create.add_argument("--goal", required=True, help="Goal description")
    plan_create.add_argument("--task-id", default="", help="Optional task ID")
    plan_create.add_argument("--task-type", default="build", choices=["build", "repair", "extend"], help="Task type")

    plan_status = sub.add_parser("plan-status", help="Show current plan checkpoint state")
    plan_status.add_argument("--plan-id", default="", help="Plan ID (uses latest if not specified)")

    plan_next = sub.add_parser("plan-next-subgoal", help="Print current/next subgoal and success criteria")
    plan_next.add_argument("--plan-id", default="", help="Plan ID (uses latest if not specified)")

    plan_resume = sub.add_parser("plan-resume", help="Resume latest incomplete plan or given plan_id")
    plan_resume.add_argument("--plan-id", default="", help="Plan ID (uses latest incomplete if not specified)")

    td_long_plan = sub.add_parser("td-long-plan", help="Create a TD-specific long-horizon plan")
    td_long_plan.add_argument("--goal", required=True, help="Goal description")
    td_long_plan.add_argument("--task-id", default="", help="Task ID")
    td_long_plan.add_argument("--template", default="custom",
                              choices=["basic_top_chain", "chop_top_bridge", "multilayer_top_system", "extend_network", "repair_output", "custom"],
                              help="Plan template")
    td_long_plan.add_argument("--layers", type=int, default=3, help="Number of layers for multilayer template")

    houdini_long_plan = sub.add_parser("houdini-long-plan", help="Create a Houdini-specific long-horizon plan")
    houdini_long_plan.add_argument("--goal", required=True, help="Goal description")
    houdini_long_plan.add_argument("--task-id", default="", help="Task ID")
    houdini_long_plan.add_argument("--template", default="custom",
                                   choices=["basic_sop_chain", "geo_processing_chain", "constraint_prep", "dop_prep", "repair_parameter", "attach_null", "custom"],
                                   help="Plan template")

    # Dashboard commands
    status_dashboard = sub.add_parser("status-dashboard", help="Show comprehensive health dashboard")
    status_dashboard.add_argument("--json", action="store_true", help="Output as JSON")
    status_dashboard.add_argument("--refresh", action="store_true", help="Live refresh mode (5s interval)")
    status_dashboard.add_argument("--output", default="", help="Save JSON to file")
    status_dashboard.add_argument("--compact", action="store_true", help="Compact single-line output")

    return parser


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Run CLI command."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    config = load_config()
    registry = build_default_registry()
    domains = build_domain_registry()

    repo_root = config.repo_root if (config.repo_root / "memory").exists() else config.repo_root.parent
    recorder = SessionRecorder(SessionStore(config.repo_root))
    tutorial_store = TutorialMetadataStore(config.repo_root / "data" / "tutorials" / "metadata")
    source_registry = SourceRegistry()
    memory_store = build_default_memory_store(repo_root)
    memory_store.load()

    if args.command == "houdini-do":
        from app.domains.houdini.houdini_trial_loop import run_trial_loop
        print(f"Goal: {args.goal}")
        print(f"Provider: {args.provider} | Context: {args.context} | Max attempts: {args.attempts}")
        print("Running trial loop...\n")
        result = run_trial_loop(
            goal=args.goal,
            target_context=args.context,
            max_attempts=args.attempts,
            provider=args.provider,
        )
        print(result.summary())
        for a in result.attempts:
            print(f"  [{a.attempt}] {a.source} -> {a.status}: {a.message}")
        if result.succeeded and result.final_code:
            print(f"\nWorking code:\n{result.final_code[:500]}")
        return 0 if result.succeeded else 1

    if args.command == "status":
        print("personal-ai: active")
        print(f"repo_root: {config.repo_root}")
        print(f"primary_domain: {config.primary_domain}")
        print(f"default_provider: {config.default_provider}")
        return 0

    if args.command == "status-dashboard":
        from app.dashboard import DashboardCollector, DashboardRenderer
        import time

        collector = DashboardCollector(repo_root=repo_root)

        def render_dashboard():
            report = collector.collect_all()
            renderer = DashboardRenderer()

            if args.json:
                print(renderer.render_json(report))
            elif args.compact:
                print(renderer.render_compact(report))
            else:
                print(renderer.render(report))

            if args.output:
                collector.export_json(args.output)
                print(f"\nSaved to: {args.output}")

            return report

        if args.refresh:
            try:
                while True:
                    print("\033[2J\033[H")  # Clear screen
                    render_dashboard()
                    print("\nPress Ctrl+C to stop...")
                    time.sleep(5)
            except KeyboardInterrupt:
                print("\nDashboard stopped.")
        else:
            render_dashboard()
        return 0

    if args.command == "agents":
        for role in registry.list_roles():
            print(role)
        return 0

    if args.command == "domains":
        for domain in domains:
            if domain.enabled:
                print(domain.name)
        return 0

    if args.command == "memory-add":
        item = memory_store.add(
            args.content,
            tags=_split_csv(args.tags),
            domain=args.domain,
            source=args.source or None,
            bucket=args.bucket,
        )
        print("memory_add_status:", "ok")
        print("bucket:", args.bucket)
        print("created_at:", item.created_at)
        print("domain:", item.domain)
        print("tags:", ", ".join(item.tags) if item.tags else "-")
        return 0

    if args.command == "memory-list":
        bucket = args.bucket
        items = memory_store.search(domain=args.domain, bucket=bucket)[: max(0, args.limit)] if args.domain else memory_store.recent(args.limit, bucket=bucket)
        print("memory_list_count:", len(items))
        print("bucket:", bucket)
        for item in items:
            print(f"- [{item.created_at}] ({item.domain}) {item.content}")
        return 0

    if args.command == "memory-search":
        bucket = args.bucket
        items = memory_store.search(query=args.query, tags=_split_csv(args.tags), domain=args.domain or None, bucket=bucket)
        print("memory_search_count:", len(items))
        print("bucket:", bucket)
        for item in items:
            print(f"- [{item.created_at}] ({item.domain}) {item.content}")
        return 0

    if args.command == "memory-clear-short":
        memory_store.clear_short_term()
        print("memory_clear_short_status:", "ok")
        print("short_term_count:", len(memory_store.short_term))
        return 0

    if args.command == "memory-runtime-preview":
        return cmd_memory_runtime_preview(args, memory_store, repo_root)

    if args.command == "success-pattern-search":
        return cmd_success_pattern_search(args, repo_root)

    if args.command == "failure-pattern-search":
        return cmd_failure_pattern_search(args, repo_root)

    if args.command == "td-status":
        kb = build_default_td_knowledge()
        print("domain: touchdesigner")
        print(f"operator_families: {len(kb.families)}")
        print(f"task_categories: {len(kb.task_categories)}")
        return 0

    if args.command == "offline-check":
        policy = OfflinePolicy(offline_mode=config.offline_mode)
        print("offline_mode:", policy.offline_mode)
        print("allows_local_docs:", policy.allows_operation("read_local_docs"))
        print("allows_remote_fetch:", policy.allows_operation("remote_fetch"))
        return 0

    if args.command == "td-demo-plan":
        package = build_first_td_demo_package()
        print("td_demo_task:", package.task.name)
        print("goal:", package.task.goal)
        print("operators:", " -> ".join(package.task.operator_sequence))
        print("plan:")
        for idx, step in enumerate(package.report.action_plan, start=1):
            print(f"  {idx}. {step}")
        print("eval_passed:", package.report.eval_result.passed)
        print("score:", package.report.eval_result.score)
        return 0

    if args.command == "td-demo-export":
        script_path, report_path = export_first_td_demo_assets(Path(config.repo_root))
        print("exported_script:", script_path)
        print("exported_report:", report_path)
        return 0

    if args.command == "td-live-plan":
        executor = TDExecutor()
        package = executor.prepare_live_basic_top_chain(target_network=args.network)
        print(json.dumps(package.request.to_dict(), indent=2))
        return 0

    if args.command == "td-live-send":
        executor = TDExecutor()
        package = executor.prepare_live_basic_top_chain(target_network=args.network)
        client = TDLiveClient(host=args.host, port=args.port, timeout_seconds=args.timeout)
        try:
            response = client.send_command(package.request)
        except Exception as exc:
            print("td_live_send_status: error")
            print("td_live_send_message:", str(exc))
            return 1

        print("td_live_send_status:", response.status)
        print("td_live_send_message:", response.message)
        if response.result:
            print("td_live_send_result:")
            print(json.dumps(response.result, indent=2))
        return 0

    if args.command == "td-ping":
        from app.domains.touchdesigner.td_live_client import TDLiveClient as _TDLiveClient
        client = _TDLiveClient(host=args.host, port=args.port, timeout_seconds=args.timeout)
        try:
            result = client.ping()
            print("td_ping_status:", result.get("status", "unknown"))
            print("td_ping_app:", result.get("app", "unknown"))
            return 0
        except Exception as exc:
            print("td_ping_status: error")
            print("td_ping_message:", str(exc))
            return 1

    if args.command == "td-inspect":
        from app.domains.touchdesigner.td_live_client import TDLiveClient as _TDLiveClient
        client = _TDLiveClient(host=args.host, port=args.port, timeout_seconds=args.timeout)
        try:
            result = client.inspect_network(path=args.network)
            print("td_inspect_status:", result.get("status", "unknown"))
            print("td_inspect_path:", result.get("path", args.network))
            print("td_inspect_operator_count:", result.get("operator_count", 0))
            if "operators" in result:
                print("td_inspect_operators:")
                for op in result["operators"]:
                    print(f"  - {op.get('name', '?')} [{op.get('type', '?')}] ({op.get('family', '?')})")
            return 0
        except Exception as exc:
            print("td_inspect_status: error")
            print("td_inspect_message:", str(exc))
            return 1

    if args.command == "td-ui-plan":
        plan = TDExecutor().prepare_ui_basic_top_chain_plan()
        print(json.dumps(plan.to_dict(), indent=2))
        return 0

    if args.command == "td-ui-dry-run":
        plan = TDExecutor().prepare_ui_basic_top_chain_plan()
        report = TDUIController().execute_plan(plan, dry_run=True)
        print("td_ui_dry_run_status:", report.status)
        print("td_ui_dry_run_executed:", len(report.executed_actions))
        print("td_ui_dry_run_stopped:", report.stopped_by_killswitch)
        if report.message:
            print("td_ui_dry_run_message:", report.message)
        return 0

    if args.command == "td-verify-demo":
        task = build_basic_top_chain_demo_task()
        expectation = build_basic_top_chain_expectation(task, target_network=args.network)

        if args.use_live_response:
            try:
                response = TDExecutor().execute_live_basic_top_chain(
                    target_network=args.network,
                    host=args.host,
                    port=args.port,
                    timeout_seconds=args.timeout,
                )
            except Exception as exc:
                print("td_verify_status: error")
                print("td_verify_message:", str(exc))
                return 1
            verification_input = verification_input_from_live_response(response, task, args.network)
        else:
            verification_input = verification_input_from_simulated_result(task, args.network)

        result = verify_basic_top_chain(expectation, verification_input)
        print("td_verify_status:", result.status)
        print("td_verify_passed:", result.passed)
        print("td_verify_summary:", summarize_verification(result))
        return 0

    if args.command == "td-run-loop":
        loop = TDExecutionLoop(retry_settings=TDRetrySettings(max_retries=max(0, args.max_retries)))
        report = loop.run_basic_top_chain(
            target_network=args.network,
            dry_run=not args.live,
            use_live_bridge=args.live,
            live_host=args.host,
            live_port=args.port,
            live_timeout=args.timeout,
        )
        print("td_loop_final_status:", report.final_status)
        print("td_loop_succeeded:", report.succeeded)
        print("td_loop_attempts:", len(report.attempts))
        print("td_loop_retries_used:", report.retries_used)
        if report.attempts:
            last = report.attempts[-1]
            print("td_loop_last_attempt:", last.attempt_index)
            print("td_loop_last_message:", last.message)
        return 0

    if args.command == "td-graph-plan":
        plan = TDExecutor().prepare_graph_plan(
            template_id=args.template,
            target_network=args.network,
            mode=args.mode,
        )
        print(json.dumps(plan.to_dict(), indent=2))
        return 0

    if args.command == "td-graph-verify":
        if args.result_json:
            payload = json.loads((Path(config.repo_root) / args.result_json).read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                print("td_graph_verify_status: error")
                print("message: result json must decode to an object")
                return 1
            result_data = payload
        else:
            result_data = {
                "chain": ["noiseTOP", "levelTOP", "nullTOP"],
                "operators": [
                    {"name": "noiseTOP", "operator_type": "noiseTOP", "family": "TOP", "path": f"{args.network}/noiseTOP"},
                    {"name": "levelTOP", "operator_type": "levelTOP", "family": "TOP", "path": f"{args.network}/levelTOP"},
                    {"name": "nullTOP", "operator_type": "nullTOP", "family": "TOP", "path": f"{args.network}/nullTOP"},
                ],
            }
        report = TDExecutor().verify_graph_result(result_data=result_data, template_id=args.template, target_network=args.network)
        print("td_graph_verify:", summarize_graph_report(report))
        print(json.dumps(report.to_dict(), indent=2))
        return 0

    if args.command == "ollama-status":
        client = OllamaClient()
        print("ollama_status:", client.status())
        return 0

    if args.command == "rag-build":
        from app.core.rag_index import build_index, save_index
        from app.core.rag_context_builder import invalidate_cache
        print("Scanning local docs and transcripts...")
        chunks = build_index()
        if not chunks:
            print("No data found. Run channel_learn.py or docs_learn.py first.")
            return 1
        path = save_index(chunks)
        invalidate_cache()
        domains = sorted({c.domain for c in chunks})
        sources = len({c.source_id for c in chunks})
        print(f"Index built: {len(chunks)} chunks | {sources} sources | domains: {domains}")
        print(f"Saved: {path}")
        return 0

    if args.command == "rag-search":
        from app.core.rag_index import load_index
        from app.core.rag_retriever import _build_idf, search
        from app.core.rag_models import RagQuery
        chunks = load_index()
        if not chunks:
            print("Index not found. Run: python -m app.cli rag-build")
            return 1
        idf = _build_idf(chunks)
        q = RagQuery(text=args.query, domain=args.domain, max_results=args.top)
        hits = search(q, chunks, idf=idf)
        if not hits:
            print("No results.")
            return 0
        for i, hit in enumerate(hits, 1):
            print(f"\n[{i}] score={hit.relevance_score:.2f} | {hit.chunk.domain} | {hit.chunk.source_type}")
            print(f"    {hit.chunk.title[:70]}")
            print(f"    {hit.chunk.text[:200]}...")
        return 0

    if args.command == "rag-status":
        from app.core.rag_index import index_status
        status = index_status()
        if not status.get("exists"):
            print("RAG index not found. Run: python -m app.cli rag-build")
            return 0
        print(f"RAG Index Status")
        print(f"  Path:    {status['path']}")
        print(f"  Built:   {status['built_at']}")
        print(f"  Chunks:  {status['chunk_count']}")
        print(f"  Sources: {status['source_count']}")
        print(f"  Domains: {status['domains']}")
        return 0

    if args.command == "ask":
        result = run_task(args.query, model=args.model)
        sys.stdout.buffer.write(f"[domain: {result.domain} | role: {result.role} | model: {result.model}]\n\n".encode("utf-8"))
        if result.ok:
            sys.stdout.buffer.write((result.response + "\n").encode("utf-8"))
        else:
            sys.stdout.buffer.write(f"ERROR: {result.error}\n".encode("utf-8"))
            return 1
        sys.stdout.buffer.flush()
        return 0

    if args.command == "houdini-live-plan":
        package = HoudiniExecutor().prepare_live_basic_sop_chain(target_context=args.context)
        print(json.dumps(package.request.to_dict(), indent=2))
        return 0

    if args.command == "houdini-live-send":
        package = HoudiniExecutor().prepare_live_basic_sop_chain(target_context=args.context)
        inbox = Path(config.repo_root) / args.inbox
        outbox = Path(config.repo_root) / args.outbox
        client = HoudiniLiveFileClient(inbox_dir=inbox, outbox_dir=outbox, timeout_seconds=args.timeout)

        try:
            response = client.send_command(package.request, wait_for_response=not args.no_wait)
        except Exception as exc:
            print("houdini_live_send_status: error")
            print("houdini_live_send_message:", str(exc))
            return 1

        print("houdini_live_send_status:", response.status)
        print("houdini_live_send_message:", response.message)
        if response.result:
            print("houdini_live_send_result:")
            print(json.dumps(response.result, indent=2))
        return 0

    if args.command == "houdini-ping":
        from app.domains.houdini.houdini_live_client import HoudiniLiveClient
        client = HoudiniLiveClient(host=args.host, port=args.port, timeout_seconds=args.timeout)
        try:
            result = client.ping()
            print("houdini_ping_status:", result.get("status", "unknown"))
            print("houdini_ping_app:", result.get("app", "unknown"))
            return 0
        except Exception as exc:
            print("houdini_ping_status: error")
            print("houdini_ping_message:", str(exc))
            return 1

    if args.command == "houdini-inspect":
        from app.domains.houdini.houdini_live_client import HoudiniLiveClient
        client = HoudiniLiveClient(host=args.host, port=args.port, timeout_seconds=args.timeout)
        try:
            result = client.inspect_context(path=args.context)
            print("houdini_inspect_status:", result.get("status", "unknown"))
            print("houdini_inspect_path:", result.get("path", args.context))
            print("houdini_inspect_node_count:", result.get("node_count", 0))
            if "nodes" in result:
                print("houdini_inspect_nodes:")
                for node in result["nodes"]:
                    print(f"  - {node.get('name', '?')} [{node.get('type', '?')}]")
            return 0
        except Exception as exc:
            print("houdini_inspect_status: error")
            print("houdini_inspect_message:", str(exc))
            return 1

    if args.command == "houdini-graph-plan":
        plan = HoudiniExecutor().prepare_graph_plan(
            template_id=args.template,
            target_context=args.context,
            mode=args.mode,
        )
        print(json.dumps(plan.to_dict(), indent=2))
        return 0

    if args.command == "houdini-graph-verify":
        if args.result_json:
            payload = json.loads((Path(config.repo_root) / args.result_json).read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                print("houdini_graph_verify_status: error")
                print("message: result json must decode to an object")
                return 1
            result_data = payload
        else:
            result_data = {
                "chain": ["grid1", "scatter1", "attribwrangle1", "OUT"],
                "nodes": [
                    {"name": "grid1", "node_type": "grid", "path": f"{args.context}/grid1", "parent_context": args.context},
                    {"name": "scatter1", "node_type": "scatter", "path": f"{args.context}/scatter1", "parent_context": args.context},
                    {"name": "attribwrangle1", "node_type": "attribwrangle", "path": f"{args.context}/attribwrangle1", "parent_context": args.context},
                    {"name": "OUT", "node_type": "null", "path": f"{args.context}/OUT", "parent_context": args.context},
                ],
            }
        report = HoudiniExecutor().verify_graph_result(result_data=result_data, template_id=args.template, target_context=args.context)
        print("houdini_graph_verify:", summarize_graph_report(report))
        print(json.dumps(report.to_dict(), indent=2))
        return 0

    if args.command == "session-start":
        manifest = recorder.start_session(domain=args.domain, task_hint=args.task_hint)
        session_dir = recorder.store.session_dir(manifest.metadata.session_id, manifest.metadata.domain)
        print("session_status: active")
        print("session_id:", manifest.metadata.session_id)
        print("domain:", manifest.metadata.domain)
        print("task_hint:", manifest.metadata.task_hint)
        print("session_path:", session_dir)
        return 0

    if args.command == "session-note":
        try:
            note = recorder.record_note(args.text)
        except RuntimeError as exc:
            print("session_note_status: error")
            print("session_note_message:", str(exc))
            return 1
        print("session_note_status: recorded")
        print("session_id:", note.session_id)
        return 0

    if args.command == "session-shot":
        try:
            shot = recorder.record_screenshot(enabled=args.enabled, label=args.label)
        except RuntimeError as exc:
            print("session_shot_status: error")
            print("session_shot_message:", str(exc))
            return 1
        print("session_shot_status:", shot.status)
        print("screenshot_path:", shot.screenshot_path)
        print("message:", shot.message)
        return 0

    if args.command == "session-end":
        try:
            manifest = recorder.end_session(
                status=args.status,
                outcome=args.outcome,
                summary=args.summary,
            )
        except RuntimeError as exc:
            print("session_end_status: error")
            print("session_end_message:", str(exc))
            return 1
        print("session_end_status:", manifest.metadata.status)
        print("session_id:", manifest.metadata.session_id)
        print("outcome:", manifest.run_outcome or args.outcome or args.status)
        print("event_count:", manifest.action_count + manifest.verification_count + manifest.retry_count)
        print("screenshot_count:", manifest.screenshot_count)
        return 0

    if args.command == "session-status":
        status = recorder.session_status()
        if not status:
            print("session_status: none")
            return 0
        session_dir = recorder.store.session_dir(status["session_id"], status["domain"])
        manifest = recorder.store.load_manifest(status["session_id"], status["domain"])

        # Count events
        events_path = recorder.store.events_path(status["session_id"], status["domain"])
        event_count = 0
        if events_path.exists():
            event_count = sum(1 for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip())

        print("session_status: active")
        print("session_id:", status["session_id"])
        print("domain:", status["domain"])
        print("task_hint:", manifest.metadata.task_hint)
        print("started_at:", manifest.metadata.started_at)
        print("event_count:", event_count)
        print("screenshot_count:", manifest.screenshot_count)
        print("session_path:", session_dir)
        return 0

    if args.command == "session-list":
        from app.recording.session_runtime import list_recent_sessions
        domain_filter = args.domain if args.domain else None
        sessions = list_recent_sessions(limit=args.limit, domain=domain_filter, repo_root=config.repo_root)
        print("session_list_count:", len(sessions))
        for s in sessions:
            print(f"- [{s['domain']}] {s['session_id']}: {s['task_hint']} ({s['status']}, {s['event_count']} events)")
        return 0


    if args.command == "tutorial-dedupe":
        report = dedupe_fetched_tutorial_metadata(Path(config.repo_root) / "data" / "tutorials" / "metadata")
        print("tutorial_dedupe_status: completed")
        print("scanned:", report.scanned)
        print("duplicate_groups:", report.duplicate_groups)
        print("archived_files:", report.archived_files)
        print("kept_files:", report.kept_files)
        if report.archive_dir:
            print("archive_dir:", report.archive_dir)
        return 0
    if args.command == "tutorial-add":
        tutorial_id = new_tutorial_id(prefix=args.domain)
        metadata = TutorialMetadata(
            tutorial_id=tutorial_id,
            source_type=args.source_type,
            source_name=args.source_name,
            title=args.title,
            duration_seconds=max(0, args.duration),
            topic_tags=_split_csv(args.topic_tags),
            task_labels=_split_csv(args.task_labels),
            local_path=args.local_path,
            url_reference=args.url,
            notes=args.notes,
            domain=args.domain,
        )
        path = tutorial_store.save(metadata)
        print("tutorial_add_status: saved")
        print("tutorial_id:", tutorial_id)
        print("metadata_path:", path)
        return 0

    if args.command == "session-link-tutorial":
        try:
            manifest = recorder.link_tutorial_reference(args.tutorial_id)
        except RuntimeError as exc:
            print("session_link_tutorial_status: error")
            print("session_link_tutorial_message:", str(exc))
            return 1
        print("session_link_tutorial_status: linked")
        print("session_id:", manifest.metadata.session_id)
        print("tutorial_id:", args.tutorial_id)
        return 0

    if args.command == "data-targets":
        report = build_collection_report(Path(config.repo_root))
        sessions_by_domain = report.payload.get("sessions_by_domain", {})
        task_counts = report.payload.get("task_coverage", {})
        target = coverage_summary(sessions_by_domain, task_counts, targets=DataTargets())
        print("data_targets_status: ok")
        for item in target.to_dict().get("session_progress", []):
            print(f"{item['domain']}: {item['current_count']}/{item['target_count']} (remaining={item['remaining']})")
        missing = target.to_dict().get("missing_task_coverage", {})
        if missing:
            print("missing_task_coverage:", missing)
        return 0

    if args.command == "data-report":
        report = build_collection_report(Path(config.repo_root))
        json_path, md_path = write_collection_report(
            report,
            Path(config.repo_root) / args.json_out,
            Path(config.repo_root) / args.md_out,
        )
        print("data_report_status: completed")
        print("json_report:", json_path)
        print("markdown_report:", md_path)
        print("canonical_example_count:", report.payload.get("canonical_example_count", 0))
        print("supervised_example_count:", report.payload.get("supervised_example_count", 0))
        return 0

    if args.command == "data-backfill":
        candidates = scan_for_backfill_candidates(Path(config.repo_root))
        print("data_backfill_candidates:", len(candidates))
        if args.dry_run:
            for item in candidates[:5]:
                print("candidate:", item.example_id, item.quality_status, item.source_path)
            return 0
        staging_path = write_backfill_staging(candidates, Path(config.repo_root) / args.staging)
        print("data_backfill_staging:", staging_path)
        return 0

    if args.command == "bootstrap-examples":
        rows = load_canonical_jsonl(str(Path(config.repo_root) / args.dataset))
        output_rows, summary = bootstrap_supervised_examples(rows, mode=args.mode)
        out_path = Path(config.repo_root) / args.out
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as handle:
            for row in output_rows:
                handle.write(json.dumps(row, ensure_ascii=True))
                handle.write("\n")
        print("bootstrap_examples_status: completed")
        print("mode:", args.mode)
        print("original_count:", summary.original_count)
        print("derived_count:", summary.derived_count)
        print("total_count:", summary.total_count)
        print("output:", out_path)
        return 0


    if args.command == "web-sources":
        seeds = load_enabled_seeds(Path(config.repo_root) / "data/web_ingest/seeds")
        for source in source_registry.list_for_cli():
            print(json.dumps(source, ensure_ascii=True))
        print("configured_seed_count:", len(seeds))
        return 0

    if args.command == "fetch-docs":
        policy = build_default_fetch_policy(explicit_online_enabled=True)
        ingestor = DocsIngestor(repo_root=Path(config.repo_root), policy=policy, registry=source_registry)
        urls = [item.strip() for item in args.urls.split(",") if item.strip()]
        records = ingestor.ingest_urls(source_id=args.source_id, urls=urls, max_pages=max(0, args.max_pages))
        print("fetch_docs_status: completed")
        print("fetched_count:", len(records))
        for item in records:
            print("doc:", item.title, "|", item.url)
        return 0

    if args.command == "fetch-tutorials":
        policy = build_default_fetch_policy(explicit_online_enabled=True)
        ingestor = TutorialIngestor(repo_root=Path(config.repo_root), policy=policy)
        urls = [item.strip() for item in args.urls.split(",") if item.strip()]
        results = [
            ingestor.ingest_url(source_id=args.source_id, domain=args.domain, url=url, notes=args.notes)
            for url in urls
        ]
        print("fetch_tutorials_status: completed")
        print("fetched_count:", len(results))
        for item in results:
            print("tutorial:", item.tutorial_id, "|", item.url)
        return 0

    if args.command == "fetch-url":
        policy = build_default_fetch_policy(explicit_online_enabled=True)
        if args.type == "docs":
            record = DocsIngestor(repo_root=Path(config.repo_root), policy=policy, registry=source_registry).ingest_url(
                source_id=args.source_id,
                url=args.url,
            )
            print("fetch_url_status: completed")
            print("record_type: docs")
            print("title:", record.title)
            print("url:", record.url)
            return 0

        result = TutorialIngestor(repo_root=Path(config.repo_root), policy=policy).ingest_url(
            source_id=args.source_id,
            domain=args.domain,
            url=args.url,
            notes=args.notes,
        )
        print("fetch_url_status: completed")
        print("record_type: tutorial")
        print("tutorial_id:", result.tutorial_id)
        print("url:", result.url)
        return 0

    if args.command == "web-cache-status":
        status = CacheStore(Path(config.repo_root)).status()
        print("web_cache_status: ok")
        print("raw_files:", status["raw_files"])
        print("normalized_files:", status["normalized_files"])
        print("metadata_files:", status["metadata_files"])
        state_dir = Path(config.repo_root) / "data" / "web_ingest" / "state"
        seen_path = state_dir / "seen_urls.json"
        hash_path = state_dir / "content_hashes.json"
        seen_count = 0
        hash_count = 0
        if seen_path.exists():
            try:
                seen_count = len(json.loads(seen_path.read_text(encoding="utf-8")))
            except Exception:
                seen_count = 0
        if hash_path.exists():
            try:
                hash_count = len(json.loads(hash_path.read_text(encoding="utf-8")))
            except Exception:
                hash_count = 0
        print("seen_urls:", seen_count)
        print("content_hashes:", hash_count)
        return 0

    if args.command == "web-ingest-status":
        status = ingest_status(Path(config.repo_root))
        print("web_ingest_status: ok")
        print("total_records:", status["total_records"])
        print("quality_accepted:", status["quality_accepted"])
        print("quality_rejected:", status["quality_rejected"])
        print("rag_ready:", status["rag_ready"])
        print("quality_breakdown:")
        for q, count in status["quality_breakdown"].items():
            print(f"  {q}: {count}")
        print("by_source:")
        for src, count in status["by_source"].items():
            print(f"  {src}: {count}")
        print("by_domain:")
        for dom, count in status["by_domain"].items():
            print(f"  {dom}: {count}")
        return 0

    if args.command == "web-rag-build":
        from app.core.rag_index import build_index, save_index
        from app.core.rag_context_builder import invalidate_cache
        print("Building RAG index from web ingest sources...")
        chunks = build_index(repo_root=Path(config.repo_root), include_web_ingest=True)
        if not chunks:
            print("No data found. Run fetch-docs or fetch-tutorials first.")
            return 1
        path = save_index(chunks)
        invalidate_cache()
        domains = sorted({c.domain for c in chunks})
        sources = len({c.source_id for c in chunks})
        web_chunks = sum(1 for c in chunks if c.source_type in ("doc", "tutorial_meta", "transcript"))
        print(f"Index built: {len(chunks)} chunks | {sources} sources | domains: {domains}")
        print(f"Web ingest chunks: {web_chunks}")
        print(f"Saved: {path}")
        return 0

    if args.command == "web-rag-search":
        from app.core.rag_index import load_index
        from app.core.rag_retriever import _build_idf, search
        from app.core.rag_models import RagQuery
        chunks = load_index()
        if not chunks:
            print("Index not found. Run: python -m app.main web-rag-build")
            return 1
        # Filter to web ingest sources only
        web_chunks = [c for c in chunks if c.source_type in ("doc", "tutorial_meta", "transcript")]
        if not web_chunks:
            print("No web ingest content in index. Run fetch-docs/fetch-tutorials first.")
            return 1
        idf = _build_idf(web_chunks)
        q = RagQuery(text=args.query, domain=args.domain, max_results=args.top)
        hits = search(q, web_chunks, idf=idf)
        if not hits:
            print("No results from web ingest content.")
            return 0
        print(f"Found {len(hits)} results from web ingest:")
        for i, hit in enumerate(hits, 1):
            print(f"\n[{i}] score={hit.relevance_score:.2f} | {hit.chunk.domain} | {hit.chunk.source_type}")
            print(f"    {hit.chunk.title[:70]}")
            print(f"    {hit.chunk.text[:200]}...")
        return 0

    if args.command == "web-link-tutorials":
        collection = collect_ingested_records(
            Path(config.repo_root),
            quality_filter=("high_signal", "acceptable"),
        )
        if not collection.records:
            print("No ingested records found. Run fetch-docs/fetch-tutorials first.")
            return 1
        tutorials = build_tutorial_records_from_ingest(collection, tutorial_store)
        print("web_link_tutorials_status: completed")
        print("linked_count:", len(tutorials))
        for t in tutorials[:10]:
            print(f"  {t.tutorial_id} | {t.domain} | {t.title[:50]}")
        if len(tutorials) > 10:
            print(f"  ... and {len(tutorials) - 10} more")
        return 0

    if args.command == "fetch-auto":
        policy = build_default_fetch_policy(explicit_online_enabled=True)
        jobs = load_fetch_jobs(Path(config.repo_root) / args.jobs)
        if not jobs:
            print("fetch_auto_status: no_jobs")
            return 1
        print("fetch_auto_status: running")
        print("hint: press ESC to stop")
        runner = LegacyAutoFetchRunner(repo_root=Path(config.repo_root), policy=policy, registry=source_registry)
        event_hook = (lambda message: print(message)) if args.verbose else None
        report = runner.run_loop(jobs=jobs, interval_seconds=max(0.0, args.interval), max_cycles=max(1, args.max_cycles), event_hook=event_hook)
        print("fetch_auto_cycles:", report.cycles_run)
        print("fetch_auto_jobs_total:", report.jobs_total)
        print("fetch_auto_jobs_succeeded:", report.jobs_succeeded)
        print("fetch_auto_jobs_failed:", report.jobs_failed)
        print("fetch_auto_stopped_by_esc:", report.stopped_by_esc)
        return 0

    if args.command == "crawl-source":
        crawler = SourceCrawler(repo_root=Path(config.repo_root), registry=source_registry)
        report_out = Path(config.repo_root) / args.report_out if args.report_out else None
        report = crawler.run(
            CrawlConfig(
                source_id=args.source_id,
                start_url=args.url,
                max_pages=max(1, args.max_pages),
                max_depth=max(0, args.max_depth),
                skip_cached=bool(args.skip_cached),
                include_transcripts=bool(args.include_transcripts),
                report_out=report_out,
            )
        )
        print("crawl_status: completed")
        print("source_id:", report.source_id)
        print("discovered_urls:", report.discovered_urls)
        print("fetched_urls:", report.fetched_urls)
        print("new_urls:", report.new_urls)
        print("cached_hits:", report.cached_hits)
        print("rejected:", report.rejected)
        print("stopped_reason:", report.stopped_reason)
        print("elapsed_seconds:", f"{report.elapsed_seconds:.2f}")
        return 0

    if args.command == "run-auto-fetch":
        print("hint: press ESC to stop gracefully")
        runner = AutoFetchRunner(repo_root=Path(config.repo_root), crawler=SourceCrawler(repo_root=Path(config.repo_root), registry=source_registry, stop_checker=None))
        summary = runner.run_enabled_seeds(
            seed_dir=Path(config.repo_root) / args.seed_dir,
            domain=args.domain or None,
            source_id=args.source_id or None,
            max_total_pages=args.max_total_pages or None,
            max_pages_per_seed=args.max_pages_per_seed or None,
            max_depth_per_seed=args.max_depth_per_seed or None,
            skip_cached=bool(args.skip_cached),
        )
        print("run_auto_fetch_mode:", summary.mode)
        print("run_auto_fetch_runs:", len(summary.run_ids))
        print("run_auto_fetch_stopped_reason:", summary.stopped_reason)
        for line in summary.run_reports:
            print(line)
        return 0

    if args.command == "run-seed-batch":
        print("hint: press ESC to stop gracefully")
        seeds = load_enabled_seeds(Path(config.repo_root) / args.seed_dir)
        scheduler = SeedScheduler()
        summary = scheduler.select(seeds, domain=args.domain or None, source_id=args.source_id or None)
        print("due_seed_count:", len(summary.due_seeds))
        print("run_seed_count:", len(summary.run_seeds))
        print("skipped_seed_count:", len(summary.skipped_seeds))
        print("blocked_seed_count:", len(summary.blocked_seeds))
        runner = AutoFetchRunner(repo_root=Path(config.repo_root), crawler=SourceCrawler(repo_root=Path(config.repo_root), registry=source_registry, stop_checker=None))
        result = runner.run_enabled_seeds(
            seed_dir=Path(config.repo_root) / args.seed_dir,
            domain=args.domain or None,
            source_id=args.source_id or None,
            skip_cached=bool(args.skip_cached),
        )
        for line in result.run_reports:
            print(line)
        return 0

    if args.command == "crawl-resume":
        runner = AutoFetchRunner(repo_root=Path(config.repo_root), crawler=SourceCrawler(repo_root=Path(config.repo_root), registry=source_registry, stop_checker=None))
        summary = runner.resume_existing_run(run_id=args.run_id or None, skip_cached=bool(args.skip_cached))
        print("crawl_resume_runs:", len(summary.run_ids))
        print("crawl_resume_reason:", summary.stopped_reason)
        for line in summary.run_reports:
            print(line)
        return 0

    if args.command == "crawl-stop":
        stop_path = Path(config.repo_root) / "data" / "web_ingest" / "state" / "stop_crawl.flag"
        stop_path.parent.mkdir(parents=True, exist_ok=True)
        stop_path.write_text("stop", encoding="utf-8")
        print("crawl_stop_status: requested")
        print("stop_flag:", stop_path)
        return 0

    if args.command == "crawl-status":
        state_store = CrawlStateStore(Path(config.repo_root))
        status = state_store.status_summary()
        seen_count = len(json.loads(((Path(config.repo_root) / "data" / "web_ingest" / "state" / "seen_urls.json").read_text(encoding="utf-8"))) ) if (Path(config.repo_root) / "data" / "web_ingest" / "state" / "seen_urls.json").exists() else 0
        hash_count = len(json.loads(((Path(config.repo_root) / "data" / "web_ingest" / "state" / "content_hashes.json").read_text(encoding="utf-8"))) ) if (Path(config.repo_root) / "data" / "web_ingest" / "state" / "content_hashes.json").exists() else 0
        latest_run_id = status.get("latest_incomplete_run_id", "")
        queue_count = 0
        if latest_run_id:
            checkpoint = state_store.load_checkpoint(str(latest_run_id))
            if checkpoint is not None:
                queue_count = len(checkpoint.queue)
        resume_target = resolve_resume_target(Path(config.repo_root))
        print("crawl_status: ok")
        print("seen_urls:", seen_count)
        print("content_hashes:", hash_count)
        print("stop_flag_exists:", status.get("stop_flag_exists", False))
        print("latest_incomplete_run_id:", latest_run_id)
        print("resumable:", resume_target.resumable)
        print("queued_urls:", queue_count)
        return 0
    if args.command == "screen-monitor":
        from app.core.screen_monitor import ScreenMonitor
        import time as _time

        print("screen_monitor: starting")
        print(f"interval: {args.interval}ms | threshold: {args.threshold}% | vision: {not args.no_vision}")
        print("hint: Ctrl+C veya --duration ile dur\n")

        monitor = ScreenMonitor(
            interval_ms=args.interval,
            change_threshold_pct=args.threshold,
            vision_on_change=not args.no_vision,
            vision_interval_s=args.vision_interval,
            vision_prompt=args.prompt,
        )
        monitor.start()
        try:
            if args.duration > 0:
                _time.sleep(args.duration)
            else:
                while monitor.running:
                    _time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            monitor.stop()
            stats = monitor.stats()
            print(f"\nscreen_monitor_frames: {stats['frames_captured']}")
            print(f"screen_monitor_changes: {stats['changes_detected']}")
        return 0

    if args.command == "screen-observe":
        from app.core.screen_agent import ask_vision
        response = ask_vision(args.prompt, model=args.model)
        safe = response.encode("utf-8", errors="replace").decode("utf-8")
        sys.stdout.buffer.write((safe + "\n").encode("utf-8", errors="replace"))
        sys.stdout.buffer.flush()
        return 0

    if args.command == "screen-act":
        from app.core.screen_agent import run_agent
        dry_run = not args.live
        actions = run_agent(args.task, dry_run=dry_run)
        print(f"screen_act_actions: {len(actions)}")
        print(f"screen_act_mode: {'dry-run' if dry_run else 'live'}")
        return 0

    if args.command == "td-shadow-start":
        from app.agent_core.shadow_mode import ShadowSession
        shadow = ShadowSession(domain="touchdesigner")
        trace = shadow.start(mode="observe")
        # Record current window
        title = shadow.active_window_title()
        shadow.record_observe(window_title=title)
        print("td_shadow_status: active")
        print("trace_id:", trace.trace_id)
        print("domain:", trace.domain)
        print("active_window:", title or "(unknown)")
        print("hint: run td-shadow-stop to end and print summary")
        return 0

    if args.command == "td-shadow-stop":
        print("td_shadow_stop: no persistent session in CLI mode")
        print("hint: use TDAgentLoop.attach_shadow() in code, or run td-agent-step/td-agent-run which log traces automatically")
        return 0

    if args.command == "td-state-summary":
        from app.domains.touchdesigner.td_state_extractor import (
            extract_td_state_from_result,
            summarize_state,
        )
        if args.live:
            try:
                from app.domains.touchdesigner.td_executor import TDExecutor
                from app.domains.touchdesigner.td_live_client import TDLiveClient
                package = TDExecutor().prepare_live_basic_top_chain(target_network=args.network)
                client = TDLiveClient(host="127.0.0.1", port=9988, timeout_seconds=3.0)
                response = client.send_command(package.request)
                result = response.result if isinstance(response.result, dict) else {}
                state = extract_td_state_from_result(result, args.network)
            except Exception as exc:
                print("td_state_status: error")
                print("message:", str(exc))
                return 1
        else:
            result = {"network": args.network, "chain": ["noiseTOP", "levelTOP"], "operators": []}
            state = extract_td_state_from_result(result, args.network)
        print("td_state_summary:", summarize_state(state))
        print("stage:", state.stage)
        print("operator_count:", len(state.operators))
        print("is_complete:", state.is_complete)
        print("missing:", state.missing_expected or "none")
        return 0

    if args.command == "td-infer-last-action":
        from app.domains.touchdesigner.td_state_extractor import extract_td_state_from_result
        from app.domains.touchdesigner.td_action_inference import infer_td_action
        # Simulate before/after: before = empty, after = partial chain
        state_before = extract_td_state_from_result({"network": args.network, "chain": [], "operators": []}, args.network)
        state_after = extract_td_state_from_result({"network": args.network, "chain": ["noiseTOP", "levelTOP"], "operators": []}, args.network)
        inference = infer_td_action(state_before, state_after)
        print("td_infer_action:", inference.inferred_action)
        print("td_infer_confidence:", f"{inference.confidence:.2f}")
        print("td_infer_reason:", inference.reason)
        return 0

    if args.command == "td-next-action":
        from app.domains.touchdesigner.td_state_extractor import extract_td_state_from_result
        from app.domains.touchdesigner.td_next_action_candidates import rank_td_next_actions
        state = extract_td_state_from_result(
            {"network": args.network, "chain": ["noiseTOP", "levelTOP"], "operators": []},
            args.network,
        )
        candidates = rank_td_next_actions(state)
        print("td_next_action_candidates:", len(candidates))
        for i, c in enumerate(candidates[:5], 1):
            print(f"  {i}. [{c.safety_status}] {c.label} (score={c.score:.2f}) — {c.rationale}")
        return 0

    if args.command == "td-agent-step":
        from app.domains.touchdesigner.td_agent_loop import TDAgentLoop
        loop = TDAgentLoop(
            target_network=args.network,
            max_steps=1,
            dry_run=not args.live,
            use_live_bridge=args.live,
        )
        step = loop.run_step(step_index=1)
        print("td_agent_step_state:", step.loop_state.value)
        print("td_agent_action:", step.action_label)
        print("td_agent_passed:", step.passed)
        print("td_agent_message:", step.message)
        print("td_agent_state:", step.state_summary)
        print("td_agent_inferred:", step.inferred_action)
        print("td_agent_next_candidates:", ", ".join(step.next_candidates))
        return 0

    if args.command == "td-agent-run":
        from app.domains.touchdesigner.td_agent_loop import TDAgentLoop
        loop = TDAgentLoop(
            target_network=args.network,
            max_steps=args.max_steps,
            max_retries=args.max_retries,
            dry_run=not args.live,
            use_live_bridge=args.live,
        )
        result = loop.run()
        print("td_agent_run_id:", result.run_id)
        print("td_agent_final_state:", result.final_state.value)
        print("td_agent_succeeded:", result.succeeded)
        print("td_agent_steps_taken:", result.steps_taken)
        for s in result.steps:
            print(f"  step {s.step_index}: {s.loop_state.value} | {s.action_label} | passed={s.passed} | {s.message}")
        return 0

    if args.command == "houdini-state-summary":
        from app.domains.houdini.houdini_state_extractor import (
            extract_houdini_state_from_result,
            summarize_houdini_state,
        )
        result = {
            "context": args.context,
            "nodes": ["scatter", "copytopoints"],
            "connections": [["scatter", "copytopoints"]],
        }
        state = extract_houdini_state_from_result(result)
        print("houdini_state_summary:", summarize_houdini_state(state))
        print("context_type:", state.context_type)
        print("node_count:", len(state.nodes))
        print("has_output_node:", state.has_output_node)
        print("has_rop_node:", state.has_rop_node)
        print("cook_errors:", len(state.cook_errors))
        return 0

    if args.command == "houdini-infer-last-action":
        from app.domains.houdini.houdini_state_extractor import extract_houdini_state_from_result
        from app.domains.houdini.houdini_action_inference import infer_houdini_action
        state_before = extract_houdini_state_from_result({"context": args.context, "nodes": [], "connections": []})
        state_after = extract_houdini_state_from_result({
            "context": args.context,
            "nodes": ["scatter", "copytopoints"],
            "connections": [["scatter", "copytopoints"]],
        })
        inference = infer_houdini_action(state_before, state_after)
        print("houdini_infer_action:", inference.action_type)
        print("houdini_infer_confidence:", f"{inference.confidence:.2f}")
        print("houdini_infer_notes:", inference.notes)
        return 0

    if args.command == "houdini-benchmark-cold":
        from app.domains.houdini.houdini_runtime_benchmark import build_default_houdini_runtime_benchmark
        run = build_default_houdini_runtime_benchmark(Path(config.repo_root)).run(mode="cold")
        print("houdini_benchmark_mode: cold")
        print("run_id:", run.run_id)
        print("bridge_reachable:", run.bridge_reachable)
        print("local_ollama_used:", run.local_ollama_used)
        print("memory_injected_count:", run.memory_injected_count)
        print("error_memory_injected_count:", run.error_memory_injected_count)
        print("steps_attempted:", run.steps_attempted)
        print("retries_attempted:", run.retries_attempted)
        print("verification_outcome:", run.verification_outcome)
        print("final_status:", run.final_status)
        return 0

    if args.command == "houdini-benchmark-warm":
        from app.domains.houdini.houdini_runtime_benchmark import build_default_houdini_runtime_benchmark
        run = build_default_houdini_runtime_benchmark(Path(config.repo_root)).run(mode="warm")
        print("houdini_benchmark_mode: warm")
        print("run_id:", run.run_id)
        print("bridge_reachable:", run.bridge_reachable)
        print("local_ollama_used:", run.local_ollama_used)
        print("memory_injected_count:", run.memory_injected_count)
        print("error_memory_injected_count:", run.error_memory_injected_count)
        print("steps_attempted:", run.steps_attempted)
        print("retries_attempted:", run.retries_attempted)
        print("verification_outcome:", run.verification_outcome)
        print("final_status:", run.final_status)
        return 0

    if args.command == "houdini-benchmark-compare":
        from app.domains.houdini.houdini_runtime_benchmark import build_default_houdini_runtime_benchmark
        from app.evals.improvement_report import write_improvement_report
        comparison = build_default_houdini_runtime_benchmark(Path(config.repo_root)).compare()
        json_path, md_path = write_improvement_report(comparison, Path(config.repo_root))
        print("houdini_benchmark_mode: compare")
        print("conclusion:", comparison.conclusion)
        print("fewer_retries:", comparison.fewer_retries)
        print("avoided_prior_error:", comparison.avoided_prior_error)
        print("faster_success:", comparison.faster_success)
        print("report_json:", json_path)
        print("report_md:", md_path)
        return 0

    if args.command == "houdini-next-action":
        from app.domains.houdini.houdini_state_extractor import extract_houdini_state_from_result
        from app.domains.houdini.houdini_next_action_candidates import rank_houdini_next_actions
        state = extract_houdini_state_from_result({
            "context": args.context,
            "nodes": ["scatter", "copytopoints"],
            "connections": [["scatter", "copytopoints"]],
        })
        candidates = rank_houdini_next_actions(state, task_context=args.task)
        print("houdini_next_action_candidates:", len(candidates))
        for i, c in enumerate(candidates[:5], 1):
            print(f"  {i}. [{c.action_type}] p={c.priority} {c.description} — {c.rationale}")
        return 0

    if args.command == "houdini-agent-step":
        from app.domains.houdini.houdini_agent_loop import HoudiniAgentLoop
        loop = HoudiniAgentLoop(
            task_id=args.task_id,
            target_context=args.context,
            max_steps=1,
            dry_run=not args.live,
            use_live_bridge=args.live,
        )
        step = loop.run_step(step_index=1)
        print("houdini_agent_step_state:", step.loop_state.value)
        print("houdini_agent_action:", step.action_label)
        print("houdini_agent_passed:", step.passed)
        print("houdini_agent_message:", step.message)
        print("houdini_agent_state:", step.state_summary)
        print("houdini_agent_inferred:", step.inferred_action)
        print("houdini_agent_next_candidates:", ", ".join(step.next_candidates))
        return 0

    if args.command == "houdini-agent-run":
        from app.domains.houdini.houdini_agent_loop import HoudiniAgentLoop
        loop = HoudiniAgentLoop(
            task_id=args.task_id,
            target_context=args.context,
            max_steps=args.max_steps,
            max_retries=args.max_retries,
            dry_run=not args.live,
            use_live_bridge=args.live,
        )
        result = loop.run()
        print("houdini_agent_run_id:", result.run_id)
        print("houdini_agent_final_state:", result.final_state.value)
        print("houdini_agent_succeeded:", result.succeeded)
        print("houdini_agent_steps_taken:", result.steps_taken)
        for s in result.steps:
            print(f"  step {s.step_index}: {s.loop_state.value} | {s.action_label} | passed={s.passed} | {s.message}")
        return 0

    if args.command == "provider-route":
        budget = build_default_token_budget()
        cache = build_default_prompt_cache()
        router = build_default_router(offline_mode=not args.online, budget=budget, cache=cache)
        if args.online:
            from app.core.provider_router import ProviderRouter
            router = ProviderRouter(
                offline_mode=False,
                preferred_remote=args.preferred_provider,
                budget=budget,
                cache=cache,
            )
        decision = router.route(
            task_class=args.task_class,
            domain=args.domain,
            prompt=args.prompt,
            preferred_provider=args.preferred_provider,
            require_remote=args.require_remote,
            compact_state_summary=args.prompt,
            relevant_file_ids=args.file_id,
            prompt_template_version=args.template_version,
        )
        audit = build_default_audit()
        audit.record(task_class=args.task_class, domain=args.domain, decision=decision)
        print("provider_route_status:", "ok")
        print("task_class:", args.task_class)
        print("domain:", args.domain or "(none)")
        print("chosen_provider:", decision.chosen_provider)
        print("decision_reason:", decision.decision_reason)
        print("local_first_applied:", decision.local_first_applied)
        print("cache_checked:", decision.cache_checked)
        print("cache_hit:", decision.cache_hit)
        print("remote_allowed:", decision.remote_allowed)
        print("blocked_by_offline:", decision.blocked_by_offline)
        print("blocked_by_budget:", decision.blocked_by_budget)
        print("blocked_by_missing_credentials:", decision.blocked_by_missing_credentials)
        print("estimated_cost_class:", decision.estimated_cost_class)
        return 0

    if args.command == "token-budget-status":
        budget = build_default_token_budget()
        state = budget.state()
        audit = budget.audit_snapshot()
        print("token_budget_status:", "blocked" if state.blocked else "ok")
        print("remaining_daily:", state.remaining_daily)
        print("remaining_session:", state.remaining_session)
        print("remaining_task:", state.remaining_task)
        print("blocked:", state.blocked)
        if state.block_reason:
            print("block_reason:", state.block_reason)
        print("remote_reserved:", audit["remote_reserved"])
        print("remote_consumed:", audit["remote_consumed"])
        return 0

    if args.command == "token-budget-reset":
        budget = build_default_token_budget()
        budget.reset_budget(args.scope)
        print("token_budget_reset_status:", "ok")
        print("scope:", args.scope)
        return 0

    if args.command == "prompt-cache-status":
        cache = build_default_prompt_cache()
        status = cache.status()
        print("prompt_cache_status:", "ok")
        print("entry_count:", status["entry_count"])
        print("total_hits:", status["total_hits"])
        print("storage_dir:", status["storage_dir"])
        return 0

    if args.command == "prompt-cache-clear":
        cache = build_default_prompt_cache()
        cache.clear()
        print("prompt_cache_clear_status:", "ok")
        print("entry_count:", 0)
        return 0

    if args.command == "td-multigraph-plan":
        from app.domains.touchdesigner.td_multi_layer_graph_builder import TDMultiLayerGraphBuilder
        builder = TDMultiLayerGraphBuilder()
        plan = builder.create_new_multilayer_graph(
            chop_count=max(0, args.chops),
            top_count=max(0, args.tops),
            sop_count=max(0, args.sops),
            goal=args.goal,
        )
        if args.json:
            import json as _json
            print(_json.dumps(plan.to_dict(), indent=2))
        else:
            print("td_multigraph_plan_status: ok")
            print("graph_plan_id:", plan.graph_plan_id)
            print("goal:", plan.goal)
            print("requested_complexity:", plan.total_requested_complexity)
            print("estimated_node_budget:", plan.estimated_node_budget)
            print("module_count:", len(plan.module_plans))
            print("binding_count:", len(plan.interface_bindings))
            if plan.oversized_warning:
                print("WARNING:", plan.oversized_warning)
            for m in plan.module_plans:
                print(f"  module: {m.module_id} | family={m.family} | stage={m.stage} | nodes={m.planned_node_count}")
            for b in plan.interface_bindings:
                print(f"  binding: {b.binding_id} | {b.connection_mode}")
            print("notes:")
            for note in plan.bounded_execution_notes:
                print(f"  - {note}")
        return 0

    if args.command == "houdini-multigraph-plan":
        from app.domains.houdini.houdini_multi_layer_graph_builder import HoudiniMultiLayerGraphBuilder
        builder = HoudiniMultiLayerGraphBuilder()
        plan = builder.create_new_multilayer_graph(
            sop_count=max(0, args.sops),
            vop_count=max(0, args.vops),
            top_count=max(0, args.tops),
            goal=args.goal,
        )
        if args.json:
            import json as _json
            print(_json.dumps(plan.to_dict(), indent=2))
        else:
            print("houdini_multigraph_plan_status: ok")
            print("graph_plan_id:", plan.graph_plan_id)
            print("goal:", plan.goal)
            print("requested_complexity:", plan.total_requested_complexity)
            print("estimated_node_budget:", plan.estimated_node_budget)
            print("module_count:", len(plan.module_plans))
            print("binding_count:", len(plan.interface_bindings))
            if plan.oversized_warning:
                print("WARNING:", plan.oversized_warning)
            for m in plan.module_plans:
                print(f"  module: {m.module_id} | context={m.context} | stage={m.stage} | nodes={m.planned_node_count}")
            for b in plan.interface_bindings:
                print(f"  binding: {b.binding_id} | {b.connection_mode}")
            print("notes:")
            for note in plan.bounded_execution_notes:
                print(f"  - {note}")
        return 0

    if args.command == "graph-stop-eval":
        policy = GraphStopPolicy()
        contract = GraphTaskContract(
            goal=f"evaluate {args.domain} graph run",
            success_definition="All modules present and connected.",
            stop_definition="Budget or no-progress threshold hit.",
            max_nodes_total=args.max_nodes,
            max_steps=args.max_steps,
            max_unchanged_iterations=3,
        )
        state = GraphRunState(
            nodes_created=args.nodes_created,
            steps_taken=args.steps_taken,
            retries=args.retries,
            unchanged_iterations=args.unchanged,
            elapsed_seconds=args.elapsed,
        )
        decision, reason = policy.evaluate(
            contract=contract,
            state=state,
            success_reached=args.success,
        )
        print("graph_stop_eval_status: ok")
        print("domain:", args.domain)
        print("decision:", decision)
        print("reason:", reason if reason else "(none)")
        print("nodes_created:", state.nodes_created)
        print("steps_taken:", state.steps_taken)
        print("retries:", state.retries)
        print("unchanged_iterations:", state.unchanged_iterations)
        return 0

    # MSS-based screen capture commands
    if args.command == "capture-screen":
        output_dir = Path(args.output_dir)
        if args.monitor > 0:
            result = capture_monitor(
                output_dir=output_dir,
                monitor_index=args.monitor,
                filename_prefix=args.prefix,
            )
        else:
            result = capture_fullscreen(
                output_dir=output_dir,
                monitor_index=0,
                filename_prefix=args.prefix,
            )
        print("capture_status:", "ok" if result.success else "failed")
        print("image_path:", str(result.image_path))
        print("capture_mode:", result.metadata.capture_mode)
        print("dimensions:", f"{result.metadata.width}x{result.metadata.height}")
        if result.metadata.window_title:
            print("window_title:", result.metadata.window_title)
        if not result.success:
            print("message:", result.metadata.message)
        return 0 if result.success else 1

    if args.command == "capture-window":
        output_dir = Path(args.output_dir)
        result = capture_active_window(
            output_dir=output_dir,
            filename_prefix=args.prefix,
        )
        print("capture_status:", "ok" if result.success else "failed")
        print("image_path:", str(result.image_path))
        print("capture_mode:", result.metadata.capture_mode)
        print("dimensions:", f"{result.metadata.width}x{result.metadata.height}")
        if result.metadata.window_title:
            print("window_title:", result.metadata.window_title)
        print("message:", result.metadata.message)
        return 0 if result.success else 1

    if args.command == "observe-screen":
        output_dir = Path(args.output_dir)
        observer = ScreenObserver()
        result = observer.observe_for_domain(
            domain=args.domain,
            output_dir=output_dir,
            prefer_active=args.prefer_active,
        )
        print("observe_status:", "ok" if result.screenshot.success else "failed")
        print("observation_id:", result.summary.observation_id)
        print("domain:", result.summary.domain)
        print("capture_mode:", result.summary.capture_mode)
        print("screenshot_path:", result.summary.screenshot_path)
        print("dimensions:", f"{result.screenshot.metadata.width}x{result.screenshot.metadata.height}")
        if result.summary.window_title:
            print("window_title:", result.summary.window_title)
        print("note:", result.summary.note)
        return 0 if result.screenshot.success else 1

    # UI Element Detection commands
    if args.command == "ui-template-list":
        from app.agent_core.ui_templates import list_templates, list_domains

        if args.domain:
            templates = list_templates(domain=args.domain)
            print(f"templates in domain '{args.domain}':")
        else:
            templates = list_templates()
            print("all registered templates:")

        if not templates:
            print("  (no templates found)")
            print(f"\ntemplate root: data/ui_templates/")
            print("domains:", ", ".join(list_domains()) or "(none)")
        else:
            for t in templates:
                tags_str = f" tags={t.tags}" if t.tags else ""
                note_str = f" # {t.notes}" if t.notes else ""
                print(f"  - {t.name} [{t.domain}] -> {t.path}{tags_str}{note_str}")
            print(f"\ntotal: {len(templates)}")
        return 0

    if args.command == "ui-detect":
        from app.agent_core.ui_locator import UILocator, locate_for_domain

        locator = UILocator(default_confidence=args.confidence)

        # Determine which templates to search
        template_names: list[str] = []
        if args.template:
            template_names = [args.template]
        elif args.templates:
            template_names = [t.strip() for t in args.templates.split(",") if t.strip()]
        elif args.domain:
            # Search all templates in domain
            results, summary = locate_for_domain(
                domain=args.domain,
                confidence=args.confidence,
            )
            print(f"ui_detect domain={args.domain} confidence={args.confidence}")
            print(f"summary: {summary.note}")
            for r in results:
                status = "FOUND" if r.found else "not found"
                coords = f" at ({r.center_x}, {r.center_y})" if r.found else ""
                conf_str = f" confidence={r.confidence:.2f}" if r.found else ""
                print(f"  {r.template_name}: {status}{coords}{conf_str}")
            return 0 if summary.matches_found > 0 else 1
        else:
            print("error: specify --template, --templates, or --domain")
            return 1

        # Search for specified templates
        results = locator.locate_named_templates(
            template_names=template_names,
            confidence=args.confidence,
            use_active_window=args.active_window,
        )

        print(f"ui_detect confidence={args.confidence} active_window={args.active_window}")
        found_count = 0
        for r in results:
            if r.found:
                found_count += 1
                print(f"  {r.template_name}: FOUND at ({r.center_x}, {r.center_y}) size {r.width}x{r.height} confidence={r.confidence:.2f}")
            else:
                print(f"  {r.template_name}: not found ({r.message})")

        return 0 if found_count > 0 else 1

    if args.command == "ui-detect-image":
        from app.agent_core.ui_locator import UILocator

        image_path = Path(args.image)
        if not image_path.exists():
            print(f"error: image not found: {image_path}")
            return 1

        locator = UILocator(default_confidence=args.confidence)

        # Determine which templates to search
        template_names: list[str] = []
        if args.template:
            template_names = [args.template]
        elif args.templates:
            template_names = [t.strip() for t in args.templates.split(",") if t.strip()]
        else:
            print("error: specify --template or --templates")
            return 1

        print(f"ui_detect_image image={image_path} confidence={args.confidence}")
        found_count = 0
        for name in template_names:
            result = locator.locate_in_screenshot(
                screenshot_path=image_path,
                template_name=name,
                confidence=args.confidence,
            )
            if result.found:
                found_count += 1
                print(f"  {result.template_name}: FOUND at ({result.center_x}, {result.center_y}) size {result.width}x{result.height} confidence={result.confidence:.2f}")
            else:
                print(f"  {result.template_name}: not found ({result.message})")

        return 0 if found_count > 0 else 1

    # Task Decomposition commands
    if args.command == "task-decompose":
        from app.agent_core.task_decomposition import DecompositionEngine
        from app.agent_core.decomposition_verifier import verify_decomposition
        import json

        engine = DecompositionEngine(max_depth=args.max_depth)
        decomp = engine.decompose_task(
            goal=args.goal,
            domain=args.domain,
            context=args.context,
            max_depth=args.max_depth,
        )

        # Verify
        verification = verify_decomposition(decomp)

        if args.json:
            output = {
                "decomposition_id": decomp.decomposition_id,
                "goal": decomp.goal,
                "domain": decomp.domain,
                "total_nodes": len(decomp.nodes),
                "total_leaves": len(decomp.get_leaves()),
                "max_depth": decomp.max_depth,
                "status": decomp.status,
                "verification": verification.to_dict(),
                "nodes": {k: v.to_dict() for k, v in decomp.nodes.items()},
            }
            print(json.dumps(output, indent=2))
        else:
            print(f"Decomposition: {decomp.decomposition_id}")
            print(f"Goal: {decomp.goal}")
            print(f"Domain: {decomp.domain}")
            print(f"Nodes: {len(decomp.nodes)} ({len(decomp.get_leaves())} leaves)")
            print(f"Max Depth: {decomp.max_depth}")
            print(f"Verification: {'PASSED' if verification.passed else 'FAILED'}")
            if verification.warnings:
                print(f"Warnings: {', '.join(verification.warnings)}")

        return 0 if verification.passed else 1

    if args.command == "task-decompose-tree":
        from app.agent_core.task_decomposition import DecompositionEngine

        engine = DecompositionEngine(max_depth=args.max_depth)
        decomp = engine.decompose_task(
            goal=args.goal,
            domain=args.domain,
            max_depth=args.max_depth,
        )

        def print_tree(node_id: str, indent: int = 0) -> None:
            node = decomp.nodes.get(node_id)
            if not node:
                return
            prefix = "  " * indent
            leaf_mark = "*" if node.is_leaf else ""
            print(f"{prefix}{leaf_mark} [{node.task_type}] {node.title}")
            for child_id in node.children:
                print_tree(child_id, indent + 1)

        print(f"Decomposition Tree: {decomp.goal}")
        print()
        print_tree(decomp.root_node_id)
        return 0

    if args.command == "task-decompose-next":
        from app.agent_core.task_decomposition import DecompositionEngine

        engine = DecompositionEngine(max_depth=args.max_depth)
        decomp = engine.decompose_task(
            goal=args.goal,
            domain=args.domain,
            max_depth=args.max_depth,
        )

        next_node = decomp.get_next_executable()
        if next_node:
            print(f"Next executable subtask:")
            print(f"  Node ID: {next_node.node_id}")
            print(f"  Title: {next_node.title}")
            print(f"  Description: {next_node.description}")
            print(f"  Task Type: {next_node.task_type}")
            print(f"  Step Budget: {next_node.bounded_step_budget}")
            print(f"  Retry Budget: {next_node.bounded_retry_budget}")
            if next_node.success_criteria:
                print(f"  Success Criteria: {next_node.success_criteria}")
            if next_node.steps:
                print(f"  Steps ({len(next_node.steps)}):")
                for step in next_node.steps:
                    print(f"    - {step.description}")
        else:
            print("No pending executable subtasks found.")
            print("All subtasks may be complete or blocked by dependencies.")

        return 0

    # OCR commands
    if args.command == "ocr-image":
        from pathlib import Path
        from app.agent_core.ocr_engine import extract_text, get_engine_status
        from app.agent_core.ocr_pipeline import summarize_ocr

        image_path = Path(args.image)
        if not image_path.exists():
            print("ocr_status: error")
            print("message: Image file not found")
            return 1

        result = extract_text(image_path, preferred_engine=args.engine)
        summary = summarize_ocr(result, max_chars=args.max_chars)

        print("ocr_status:", "ok" if result.success else "failed")
        print("engine:", result.engine_name)
        print("success:", result.success)
        print("average_confidence:", f"{result.average_confidence:.1f}%")
        print("text_regions:", result.text_box_count)
        if result.message:
            print("message:", result.message)
        print("\nextracted_text:")
        print(summary.full_text)
        return 0 if result.success else 1

    if args.command == "ocr-status":
        from app.agent_core.ocr_engine import get_engine_status, verify_tesseract_install

        status = get_engine_status()
        print("=== OCR Engine Status ===\n")

        # Tesseract details
        t = status["tesseract"]
        print("Tesseract:")
        print(f"  available: {t['available']}")
        if t['available']:
            print(f"  version: {t.get('version', 'unknown')}")
            print(f"  path: {t['path']}")
            print(f"  source: {t['source']}")
        else:
            print(f"  message: {t['message']}")
        print(f"  install_hint: {t['install_hint']}")
        print()

        # EasyOCR details
        e = status["easyocr"]
        print("EasyOCR:")
        print(f"  available: {e['available']}")
        print(f"  install_hint: {e['install_hint']}")
        print()

        # Summary
        print(f"preferred: {status.get('preferred', 'none')}")
        print(f"fallback_order: {status.get('fallback_order', [])}")

        # Verification guidance if Tesseract missing
        if not t['available']:
            print("\n--- Tesseract Verification ---")
            ok, msg = verify_tesseract_install()
            print(msg)

        return 0

    if args.command == "observe-screen-ocr":
        from pathlib import Path
        from app.agent_core.screen_observer import ScreenObserver

        output_dir = Path(args.output_dir)
        observer = ScreenObserver()
        result = observer.observe_with_ocr(
            output_dir=output_dir,
            domain=args.domain,
            mode="fullscreen" if args.monitor == 0 else "monitor",
            engine=args.engine,
            run_ocr=True,
            monitor_index=args.monitor,
        )
        print("observe_status:", "ok" if result.success else "failed")
        print("observation_id:", result.observation_id)
        print("domain:", result.domain)
        print("screenshot_path:", str(result.image_path))
        print("capture_mode:", result.screenshot.metadata.capture_mode)
        print("dimensions:", f"{result.screenshot.metadata.width}x{result.screenshot.metadata.height}")
        if result.screenshot.metadata.window_title:
            print("window_title:", result.screenshot.metadata.window_title)
        print("ocr_enabled:", result.has_ocr)
        print("ocr_engine:", result.ocr_engine)
        print("ocr_success:", result.ocr_success)
        if result.ocr_summary:
            print("ocr_confidence:", result.ocr_summary.confidence_label)
            print("ocr_average_confidence:", f"{result.ocr_summary.average_confidence:.1f}%")
            print("ocr_text_regions:", result.ocr_summary.text_box_count)
            print("\nocr_text:")
            print(result.ocr_summary.full_text)
        return 0 if result.success else 1

    if args.command == "capture-window-ocr":
        from pathlib import Path
        from app.agent_core.screen_observer import ScreenObserver

        output_dir = Path(args.output_dir)
        observer = ScreenObserver()
        result = observer.observe_active_window_with_ocr(
            output_dir=output_dir,
            domain=args.domain,
            engine=args.engine,
        )
        print("capture_status:", "ok" if result.success else "failed")
        print("observation_id:", result.observation_id)
        print("domain:", result.domain)
        print("screenshot_path:", str(result.image_path))
        print("capture_mode:", result.screenshot.metadata.capture_mode)
        print("dimensions:", f"{result.screenshot.metadata.width}x{result.screenshot.metadata.height}")
        if result.screenshot.metadata.window_title:
            print("window_title:", result.screenshot.metadata.window_title)
        print("ocr_enabled:", result.has_ocr)
        print("ocr_engine:", result.ocr_engine)
        print("ocr_success:", result.ocr_success)
        if result.ocr_summary:
            print("ocr_confidence:", result.ocr_summary.confidence_label)
            print("ocr_average_confidence:", f"{result.ocr_summary.average_confidence:.1f}%")
            print("ocr_text_regions:", result.ocr_summary.text_box_count)
            print("\nocr_text:")
            print(result.ocr_summary.full_text)
        return 0 if result.success else 1

    # Input executor commands
    if args.command == "input-status":
        from app.agent_core import (
            get_active_window_title,
            is_global_stop_requested,
            WindowGuard,
        )

        print("input_execution_status:")
        print(f"  active_window: {get_active_window_title() or '(unknown)'}")
        print(f"  killswitch_active: {is_global_stop_requested()}")
        print(f"  dry_run_default: True")

        # Check TouchDesigner focus
        td_guard = WindowGuard(expected_hints=["TouchDesigner"])
        td_focused = td_guard.is_expected_window_focused()
        print(f"  touchdesigner_focused: {td_focused}")

        # Check Houdini focus
        hou_guard = WindowGuard(expected_hints=["Houdini"])
        hou_focused = hou_guard.is_expected_window_focused()
        print(f"  houdini_focused: {hou_focused}")

        print("\nblocked_keys: delete, del, win, super, pause, break, printscreen")
        print("blocked_hotkeys: alt+f4, ctrl+alt+del, ctrl+w, win+l, win+d, win+tab")
        print("blocked_text_patterns: password, passwd, secret, token, apikey")
        return 0

    if args.command == "input-dry-run":
        from app.agent_core import (
            ActionPlan,
            InputAction,
            ActionExecutor,
            get_active_window_title,
        )

        # Build a safe example plan
        actions = (
            InputAction(
                action_id="demo_001",
                action_type="wait",
                duration_ms=100,
                description="Wait 100ms",
                safety_level="safe",
                requires_focus=False,
            ),
            InputAction(
                action_id="demo_002",
                action_type="key_press",
                keys=("tab",),
                description="Press Tab key",
                safety_level="safe",
                requires_focus=True,
            ),
            InputAction(
                action_id="demo_003",
                action_type="type_text",
                text="test_operator",
                description="Type test operator name",
                safety_level="safe",
                requires_focus=True,
            ),
        )

        plan = ActionPlan(
            plan_id="demo_dry_run_plan",
            task_id="demo_task",
            target_window_hint="TouchDesigner",
            actions=actions,
            max_actions=10,
        )

        print(f"dry_run: True")
        print(f"plan_id: {plan.plan_id}")
        print(f"action_count: {len(plan.actions)}")
        print(f"active_window: {get_active_window_title() or '(unknown)'}")
        print()

        executor = ActionExecutor(dry_run=True)
        summary = executor.execute_plan(plan, dry_run=True)

        print(f"execution_status: {summary.message}")
        print(f"executed_count: {summary.executed_count}")
        print(f"blocked_count: {summary.blocked_count}")
        print(f"failed_count: {summary.failed_count}")
        print(f"stopped_by_killswitch: {summary.stopped_by_killswitch}")
        print()

        for result in summary.results:
            status = "OK" if result.success else "BLOCKED" if result.blocked else "FAILED"
            print(f"  [{status}] {result.action_id} ({result.action_type})")
            if result.blocked_reason:
                print(f"       blocked_reason: {result.blocked_reason}")

        return 0

    if args.command == "input-execute":
        from app.agent_core import (
            ActionPlan,
            InputAction,
            ActionExecutor,
            get_active_window_title,
            WindowGuard,
        )

        if not args.confirm:
            print("ERROR: Real execution requires --confirm flag")
            print("Usage: personal-ai input-execute --confirm --app touchdesigner")
            return 1

        # Determine target window hints
        if args.app == "touchdesigner":
            window_hints = ["TouchDesigner"]
        elif args.app == "houdini":
            window_hints = ["Houdini"]
        else:
            window_hints = []

        # Check focus
        guard = WindowGuard(expected_hints=window_hints)
        active_window = get_active_window_title()
        is_focused = guard.is_expected_window_focused()

        print(f"real_execution: True")
        print(f"target_app: {args.app}")
        print(f"active_window: {active_window or '(unknown)'}")
        print(f"target_focused: {is_focused}")
        print()

        if not is_focused:
            print("BLOCKED: Target application is not focused")
            print(f"Please bring {args.app} to the foreground before executing real input")
            return 1

        # Build a safe example plan
        actions = (
            InputAction(
                action_id="real_001",
                action_type="wait",
                duration_ms=50,
                description="Short wait",
                safety_level="safe",
                requires_focus=False,
            ),
        )

        plan = ActionPlan(
            plan_id="demo_real_plan",
            task_id="demo_task",
            target_window_hint=args.app.capitalize(),
            actions=actions,
            max_actions=10,
        )

        executor = ActionExecutor(
            dry_run=False,
            expected_window_hints=window_hints,
        )
        summary = executor.execute_plan(plan, dry_run=False)

        print(f"execution_status: {summary.message}")
        print(f"executed_count: {summary.executed_count}")
        print(f"blocked_count: {summary.blocked_count}")
        print(f"failed_count: {summary.failed_count}")

        return 0 if summary.blocked_count == 0 and summary.failed_count == 0 else 1

    if args.command == "input-test-action":
        from app.agent_core import (
            InputAction,
            InputExecutor,
            WindowGuard,
            get_active_window_title,
        )

        dry_run = not args.live

        # Determine window hints
        window_hints = []
        if args.app == "touchdesigner":
            window_hints = ["TouchDesigner"]
        elif args.app == "houdini":
            window_hints = ["Houdini"]

        # Build action based on type
        if args.type == "move_mouse":
            action = InputAction(
                action_id="test_move",
                action_type="move_mouse",
                x=args.x,
                y=args.y,
                description="Test mouse move",
            )
        elif args.type == "left_click":
            action = InputAction(
                action_id="test_click",
                action_type="left_click",
                x=args.x if args.x else None,
                y=args.y if args.y else None,
                description="Test left click",
            )
        elif args.type == "double_click":
            action = InputAction(
                action_id="test_dblclick",
                action_type="double_click",
                x=args.x if args.x else None,
                y=args.y if args.y else None,
                description="Test double click",
            )
        elif args.type == "key_press":
            action = InputAction(
                action_id="test_key",
                action_type="key_press",
                keys=(args.key,) if args.key else (),
                description="Test key press",
            )
        elif args.type == "hotkey":
            keys = tuple(k.strip() for k in args.keys.split(",") if k.strip())
            action = InputAction(
                action_id="test_hotkey",
                action_type="hotkey",
                keys=keys,
                description="Test hotkey",
            )
        elif args.type == "type_text":
            action = InputAction(
                action_id="test_type",
                action_type="type_text",
                text=args.text,
                description="Test typing",
            )
        elif args.type == "wait":
            action = InputAction(
                action_id="test_wait",
                action_type="wait",
                duration_ms=args.duration,
                description="Test wait",
            )
        else:
            print(f"Unknown action type: {args.type}")
            return 1

        print(f"action_type: {args.type}")
        print(f"dry_run: {dry_run}")
        print(f"active_window: {get_active_window_title() or '(unknown)'}")
        if window_hints:
            guard = WindowGuard(expected_hints=window_hints)
            print(f"target_focused: {guard.is_expected_window_focused()}")
        print()

        executor = InputExecutor(
            dry_run=dry_run,
            expected_window_hints=window_hints,
        )
        result = executor.execute_action(action)

        status = "OK" if result.success else "BLOCKED" if result.blocked else "FAILED"
        print(f"status: {status}")
        print(f"action_id: {result.action_id}")
        if result.blocked_reason:
            print(f"blocked_reason: {result.blocked_reason}")
        print(f"details: {result.details}")

        return 0 if result.success else 1

    # Feedback loop commands
    if args.command == "feedback-recent":
        return cmd_feedback_recent(args)

    if args.command == "retry-strategy-preview":
        return cmd_retry_strategy_preview(args)

    if args.command == "repair-pattern-search":
        return cmd_repair_pattern_search(args)

    # Error memory commands (NEW)
    if args.command == "error-recent":
        return cmd_error_recent(args)

    if args.command == "error-search":
        return cmd_error_search(args)

    # Screen learning commands
    if args.command == "screen-learn":
        return cmd_screen_learn(args)

    if args.command == "screen-dataset-status":
        return cmd_screen_dataset_status(args)

    if args.command == "screen-patterns":
        return cmd_screen_patterns(args)

    if args.command == "screen-label-image":
        return cmd_screen_label_image(args)

    if args.command == "screen-update":
        return cmd_screen_update(args)

    # Long-horizon planning commands
    if args.command == "plan-create":
        return cmd_plan_create(args)

    if args.command == "plan-status":
        return cmd_plan_status(args)

    if args.command == "plan-next-subgoal":
        return cmd_plan_next_subgoal(args)

    if args.command == "plan-resume":
        return cmd_plan_resume(args)

    if args.command == "td-long-plan":
        return cmd_td_long_plan(args)

    if args.command == "houdini-long-plan":
        return cmd_houdini_long_plan(args)

    parser.error(f"Unknown command: {args.command}")
    return 2


def cmd_memory_runtime_preview(args: argparse.Namespace, memory_store, repo_root: Path) -> int:
    """Preview what memory would be injected at runtime for a given query."""
    from app.learning.error_memory import build_default_error_memory_store
    from app.learning.success_patterns import build_default_success_pattern_store

    query = args.query
    domain = args.domain or None
    max_items = args.max_items

    print(f"Query: {query[:100]}...")
    if domain:
        print(f"Domain: {domain}")
    print()

    # Load memory store
    memory_store.load()

    # Get relevant memory items
    print("=== LONG-TERM MEMORY ===")
    long_term_hits = memory_store.search(query=query, domain=domain, bucket="long_term")[:max_items]
    if long_term_hits:
        for item in long_term_hits:
            print(f"- [{item.domain}] {item.content[:120]}...")
            if item.tags:
                print(f"  tags: {', '.join(item.tags[:3])}")
    else:
        print("(no matching items)")
    print()

    print("=== SHORT-TERM MEMORY ===")
    short_term_hits = memory_store.search(query=query, domain=domain, bucket="short_term")[:max_items]
    if short_term_hits:
        for item in short_term_hits:
            print(f"- [{item.domain}] {item.content[:120]}...")
    else:
        print("(no matching items)")
    print()

    # Get relevant error memory
    print("=== ERROR MEMORY ===")
    error_store = build_default_error_memory_store(repo_root)
    error_hits = error_store.retrieve_relevant(
        domain=domain or "general",
        task_id="",
        query=query,
        max_items=max_items,
    )
    if error_hits:
        for err in error_hits:
            print(f"- [{err.error_type}] {err.message[:100]}...")
            print(f"  fix: {err.recommended_fix[:80]}...")
    else:
        print("(no matching errors)")
    print()

    # Get relevant success patterns
    print("=== SUCCESS PATTERNS ===")
    pattern_store = build_default_success_pattern_store(repo_root)
    patterns = pattern_store.search(domain=domain, query=query)[:max_items]
    if patterns:
        for pat in patterns:
            print(f"- [{pat.domain}] {pat.fix_description[:100]}...")
            print(f"  strategy: {pat.fix_strategy}")
            if pat.usage_count:
                print(f"  uses: {pat.usage_count}, success_rate: {pat.success_rate:.2f}")
    else:
        print("(no matching patterns)")
    print()

    # Summary
    total = len(long_term_hits) + len(short_term_hits) + len(error_hits) + len(patterns)
    print(f"Total items to inject: {total}")

    return 0


def cmd_success_pattern_search(args: argparse.Namespace, repo_root: Path) -> int:
    """Search for reusable success patterns."""
    from app.learning.success_patterns import build_default_success_pattern_store

    domain = args.domain or None
    query = args.query or ""
    max_items = args.max_items

    store = build_default_success_pattern_store(repo_root)
    store.load()

    patterns = store.search(domain=domain, query=query)[:max_items]

    if args.json:
        import json
        print(json.dumps([p.to_dict() for p in patterns], indent=2))
    else:
        print(f"Found {len(patterns)} success patterns")
        if domain:
            print(f"Domain: {domain}")
        if query:
            print(f"Query: {query}")
        print()

        for i, pat in enumerate(patterns, 1):
            print(f"{i}. [{pat.domain}] {pat.fix_description[:80]}...")
            print(f"   Type: {pat.error_type}")
            print(f"   Strategy: {pat.fix_strategy}")
            if pat.usage_count:
                print(f"   Uses: {pat.usage_count}, Success rate: {pat.success_rate:.2%}")
            if pat.tags:
                print(f"   Tags: {', '.join(pat.tags[:5])}")
            print()

    return 0


def cmd_failure_pattern_search(args: argparse.Namespace, repo_root: Path) -> int:
    """Search for failure/error patterns to avoid."""
    from app.learning.error_memory import build_default_error_memory_store

    domain = args.domain or None
    query = args.query or ""
    max_items = args.max_items

    store = build_default_error_memory_store(repo_root)
    store.load()

    items = store.retrieve_relevant(
        domain=domain or "general",
        task_id="",
        query=query,
        max_items=max_items,
    )

    if args.json:
        import json
        print(json.dumps([item.to_dict() for item in items], indent=2))
    else:
        print(f"Found {len(items)} failure patterns")
        if domain:
            print(f"Domain: {domain}")
        if query:
            print(f"Query: {query}")
        print()

        for i, item in enumerate(items, 1):
            print(f"{i}. [{item.domain}] {item.error_type}")
            print(f"   Error: {item.message[:80]}...")
            print(f"   Fix: {item.recommended_fix[:80]}...")
            print(f"   Task: {item.task_id}")
            print()

    return 0


def cmd_screen_learn(args: argparse.Namespace) -> int:
    """Learn from a screen observation."""
    from pathlib import Path
    from app.learning.screen_learning import learn_from_screen

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"error: image not found: {image_path}")
        return 1

    visible_nodes = []
    if args.visible_nodes:
        visible_nodes = [n.strip() for n in args.visible_nodes.split(",") if n.strip()]

    result = learn_from_screen(
        screenshot_path=image_path,
        domain=args.domain,
        task_id=args.task,
        session_id=args.session,
        notes=args.notes,
        visible_nodes=visible_nodes,
        source=args.source,
    )

    print(f"example_id: {result.example_id}")
    print(f"domain: {result.domain}")
    print(f"task_id: {result.task_id}")
    print(f"stage_label: {result.stage_label}")
    print(f"outcome_label: {result.outcome_label}")
    print(f"error_label: {result.error_label}")
    print(f"confidence: {result.confidence:.2f}")
    print(f"ambiguous: {result.ambiguous}")
    print(f"patterns_extracted: {result.patterns_extracted}")
    print(f"patterns_reinforced: {result.patterns_reinforced}")

    return 0


def cmd_screen_dataset_status(args: argparse.Namespace) -> int:
    """Show screen learning dataset status."""
    from pathlib import Path
    from app.learning.screen_dataset import build_default_screen_dataset
    from app.learning.screen_pattern_store import build_default_screen_pattern_store

    repo_root = Path.cwd()
    dataset = build_default_screen_dataset(repo_root)
    pattern_store = build_default_screen_pattern_store(repo_root)

    summary = dataset.summary()
    pattern_summary = pattern_store.summary()

    print("=== SCREEN DATASET ===")
    print(f"total_examples: {summary.total_examples}")
    print(f"avg_confidence: {summary.avg_confidence:.2f}")
    print(f"ambiguous_count: {summary.ambiguous_count}")
    print()

    if args.verbose:
        print("Domain distribution:")
        for domain, count in sorted(summary.domain_counts.items()):
            print(f"  {domain}: {count}")
        print()

        print("Outcome distribution:")
        for outcome, count in sorted(summary.outcome_label_counts.items()):
            print(f"  {outcome}: {count}")
        print()

        print("Stage distribution:")
        for stage, count in sorted(summary.stage_label_counts.items()):
            print(f"  {stage}: {count}")
        print()

    print("=== SCREEN PATTERNS ===")
    print(f"total_patterns: {pattern_summary['total_patterns']}")
    print(f"avg_confidence: {pattern_summary['avg_confidence']:.2f}")
    print(f"avg_support: {pattern_summary['avg_support']:.1f}")

    if args.verbose:
        print()
        print("Pattern types:")
        for ptype, count in sorted(pattern_summary['type_counts'].items()):
            print(f"  {ptype}: {count}")

    return 0


def cmd_screen_patterns(args: argparse.Namespace) -> int:
    """Show extracted screen patterns."""
    from pathlib import Path
    from app.learning.screen_pattern_store import build_default_screen_pattern_store

    repo_root = Path.cwd()
    store = build_default_screen_pattern_store(repo_root)

    patterns = store.search_patterns(
        domain=args.domain or None,
        pattern_type=args.pattern_type or None,
    )[:args.limit]

    if not patterns:
        print("No screen patterns found.")
        return 0

    print(f"Found {len(patterns)} screen patterns:")
    print()

    for pattern in patterns:
        print(f"Pattern: {pattern.pattern_id}")
        print(f"  Domain: {pattern.domain}")
        print(f"  Type: {pattern.pattern_type}")
        print(f"  Summary: {pattern.summary}")
        print(f"  Confidence: {pattern.confidence:.2f}")
        print(f"  Support: {pattern.support_count}")
        if pattern.visible_indicators:
            print(f"  Visible: {', '.join(pattern.visible_indicators[:3])}")
        if pattern.missing_indicators:
            print(f"  Missing: {', '.join(pattern.missing_indicators[:3])}")
        print()

    return 0


def cmd_screen_label_image(args: argparse.Namespace) -> int:
    """Label a screenshot without storing."""
    from pathlib import Path
    from app.learning.screen_labeling import ScreenLabeler, LabelingContext
    from app.learning.screen_example import generate_example_id

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"error: image not found: {image_path}")
        return 1

    # Try OCR if available
    ocr_text = ""
    try:
        from app.agent_core.ocr_pipeline import extract_text_only
        ocr_text = extract_text_only(image_path, min_confidence=30.0)
    except Exception:
        pass

    labeler = ScreenLabeler()
    context = LabelingContext(
        ocr_text=ocr_text,
        domain=args.domain,
    )

    example_id = generate_example_id()
    label = labeler.label_from_context(example_id, context)

    print(f"image: {image_path}")
    print(f"stage_label: {label.stage_label}")
    print(f"  confidence: {label.stage_confidence:.2f}")
    print(f"outcome_label: {label.outcome_label}")
    print(f"  confidence: {label.outcome_confidence:.2f}")
    print(f"error_label: {label.error_label}")
    print(f"  confidence: {label.error_confidence:.2f}")
    print(f"verification_label: {label.verification_label}")
    print(f"ambiguous: {label.ambiguous}")
    if label.ambiguity_reason:
        print(f"ambiguity_reason: {label.ambiguity_reason}")

    if ocr_text:
        print(f"\nOCR text (first 200 chars):\n{ocr_text[:200]}...")

    return 0


def cmd_screen_update(args: argparse.Namespace) -> int:
    """Run screen learning update cycle."""
    from pathlib import Path
    from app.learning.screen_update_cycle import ScreenUpdateCycle

    repo_root = Path.cwd()
    cycle = ScreenUpdateCycle()

    if args.full:
        result = cycle.full_update()
    else:
        result = cycle.quick_update()

    print(f"cycle_id: {result.cycle_id}")
    print(f"examples_processed: {result.examples_processed}")
    print(f"patterns_extracted: {result.patterns_extracted}")
    print(f"patterns_reinforced: {result.patterns_reinforced}")
    print(f"patterns_pruned: {result.patterns_pruned}")
    print(f"duration_seconds: {result.duration_seconds:.2f}")
    print()
    print(f"examples: {result.examples_before} -> {result.examples_after}")
    print(f"patterns: {result.patterns_before} -> {result.patterns_after}")

    return 0


def cmd_feedback_recent(args: argparse.Namespace) -> int:
    """Show recent failure -> retry -> outcome records."""
    from pathlib import Path
    from app.learning.retry_memory import build_default_retry_memory_store

    repo_root = Path.cwd()
    retry_memory = build_default_retry_memory_store(repo_root)

    # Get recent items
    items = retry_memory.get_recent(args.limit)
    if args.domain:
        items = [i for i in items if i.domain == args.domain]

    if not items:
        print("No feedback records found.")
        return 0

    print(f"Recent feedback records (last {len(items)}):")
    print("-" * 60)

    for item in items:
        status = "SUCCESS" if item.success else "FAILED"
        print(f"[{status}] {item.created_at}")
        print(f"  Domain: {item.domain}")
        print(f"  Task: {item.task_id}")
        print(f"  Error: {item.normalized_error.normalized_error_type.value}")
        print(f"  Strategy: {item.strategy.strategy_type.value}")
        print(f"  Retry #{item.retry_number}")
        if item.stop_reason:
            print(f"  Stop reason: {item.stop_reason}")
        print()

    return 0


def cmd_retry_strategy_preview(args: argparse.Namespace) -> int:
    """Show chosen retry strategy for an error."""
    from app.learning.error_normalizer import normalize_error
    from app.learning.retry_strategy import choose_retry_strategy, should_retry

    # Normalize the error
    normalized = normalize_error(
        raw_error=args.error,
        domain=args.domain,
        task_id=args.task_id or "preview",
    )

    print("Error Analysis:")
    print("-" * 40)
    print(f"Raw error: {args.error[:100]}...")
    print(f"Normalized type: {normalized.normalized_error_type.value}")
    print(f"Confidence: {normalized.confidence:.2f}")
    print(f"Fix hint: {normalized.fix_hint}")
    print()

    # Choose strategy
    strategy = choose_retry_strategy(
        normalized_error=normalized,
        prior_retry_count=0,
    )

    # Check if retry is advised
    should_do_retry = should_retry(normalized, 0, 2)

    print("Selected Retry Strategy:")
    print("-" * 40)
    print(f"Strategy type: {strategy.strategy_type.value}")
    print(f"Rationale: {strategy.rationale}")
    print(f"Expected fix: {strategy.expected_fix}")
    print(f"Action budget: {strategy.bounded_action_budget}")
    print(f"Retry budget: {strategy.bounded_retry_budget}")
    print(f"Confidence: {strategy.confidence:.2f}")
    print(f"Requires verification: {strategy.requires_verification}")
    print()
    print(f"Should retry: {should_do_retry}")

    return 0


def cmd_error_recent(args: argparse.Namespace) -> int:
    """Show recent normalized errors from persistent memory."""
    from pathlib import Path
    from app.learning.error_memory import recent_error_memory

    repo_root = Path.cwd()

    domain = args.domain or None
    errors = recent_error_memory(repo_root, domain=domain, max_items=args.limit)

    if not errors:
        print("No error memory found.")
        return 0

    print(f"Recent {len(errors)} errors:")
    print("-" * 60)

    for err in errors:
        print(f"[{err.error_type}] {err.error_id}")
        print(f"  Domain: {err.domain}")
        print(f"  Task: {err.task_id}")
        print(f"  Message: {err.message[:100]}...")
        if err.recommended_fix:
            print(f"  Fix: {err.recommended_fix[:80]}...")
        print(f"  Created: {err.created_at}")
        print()

    return 0


def cmd_error_search(args: argparse.Namespace) -> int:
    """Search persisted error memory."""
    from pathlib import Path
    from app.learning.error_memory import search_error_memory

    repo_root = Path.cwd()

    errors = search_error_memory(
        repo_root,
        domain=args.domain or None,
        error_type=args.error_type or None,
        task_id=args.task_id or None,
        query=args.query,
        max_items=args.limit,
    )

    if not errors:
        print("No matching errors found.")
        return 0

    print(f"Found {len(errors)} matching errors:")
    print("-" * 60)

    for err in errors:
        print(f"[{err.error_type}] {err.error_id}")
        print(f"  Domain: {err.domain}")
        print(f"  Task: {err.task_id}")
        print(f"  Message: {err.message[:100]}...")
        if err.recommended_fix:
            print(f"  Fix: {err.recommended_fix[:80]}...")
        print(f"  Created: {err.created_at}")
        print()

    return 0


def cmd_repair_pattern_search(args: argparse.Namespace) -> int:
    """Search saved successful repair patterns."""
    from pathlib import Path
    from app.learning.success_patterns import build_default_success_pattern_store

    repo_root = Path.cwd()
    pattern_store = build_default_success_pattern_store(repo_root)

    # Search patterns
    patterns = pattern_store.search(
        domain=args.domain or None,
        error_type=args.error_type or None,
        query=args.query,
    )

    patterns = patterns[:args.limit]

    if not patterns:
        print("No repair patterns found.")
        return 0

    print(f"Found {len(patterns)} repair patterns:")
    print("-" * 60)

    for pattern in patterns:
        print(f"Pattern: {pattern.pattern_id}")
        print(f"  Domain: {pattern.domain}")
        print(f"  Error type: {pattern.error_type}")
        print(f"  Fix: {pattern.fix_description}")
        print(f"  Strategy: {pattern.fix_strategy}")
        print(f"  Success rate: {pattern.success_rate:.2f} ({pattern.usage_count} uses)")
        if pattern.tags:
            print(f"  Tags: {', '.join(pattern.tags)}")
        if pattern.fix_steps:
            print(f"  Steps: {len(pattern.fix_steps)}")
        print()

    return 0


def cmd_plan_create(args: argparse.Namespace) -> int:
    """Create a long-horizon plan from a goal."""
    from app.agent_core.subgoal_decomposer import decompose_goal

    task_id = args.task_id or f"{args.domain}_task_{_utc_timestamp()}"
    plan = decompose_goal(
        goal=args.goal,
        domain=args.domain,
        task_id=task_id,
        task_type=args.task_type,
    )

    print(f"plan_id: {plan.plan_id}")
    print(f"domain: {plan.domain}")
    print(f"goal: {plan.goal}")
    print(f"status: {plan.status.value}")
    print(f"subgoals: {len(plan.subgoals)}")
    print()
    for i, s in enumerate(plan.subgoals, 1):
        print(f"  {i}. [{s.stage_type}] {s.title}")
        print(f"     steps: {s.bounded_step_budget}, retries: {s.bounded_retry_budget}")
        if s.dependencies:
            print(f"     deps: {', '.join(s.dependencies)}")
    print()
    print(f"max_total_steps: {plan.constraints.max_total_steps}")
    print(f"max_total_retries: {plan.constraints.max_total_retries}")
    print()
    print(f"Hint: Use 'plan-status --plan-id {plan.plan_id}' to track progress.")
    return 0


def cmd_plan_status(args: argparse.Namespace) -> int:
    """Show current plan checkpoint state."""
    from app.agent_core.plan_memory import PlanMemory

    memory = PlanMemory()

    if args.plan_id:
        plan, checkpoint = memory.load_plan_with_checkpoint(args.plan_id)
    else:
        plan, checkpoint = memory.latest_incomplete_plan()

    if plan is None:
        print("No plan found.")
        return 1

    print(f"plan_id: {plan.plan_id}")
    print(f"domain: {plan.domain}")
    print(f"goal: {plan.goal}")
    print(f"status: {plan.status.value}")
    print()

    completed = plan.completed_subgoal_ids()
    failed = plan.failed_subgoal_ids()
    pending = plan.pending_subgoal_ids()

    print(f"completed: {len(completed)}/{len(plan.subgoals)}")
    print(f"failed: {len(failed)}")
    print(f"pending: {len(pending)}")
    print(f"steps_taken: {plan.total_steps_taken}/{plan.constraints.max_total_steps}")
    print(f"retries_used: {plan.total_retries_used}/{plan.constraints.max_total_retries}")
    print()

    if checkpoint:
        print(f"checkpoint_id: {checkpoint.checkpoint_id}")
        print(f"checkpoint_notes: {checkpoint.notes or '(none)'}")

    if plan.current_subgoal_id:
        current = plan.get_subgoal(plan.current_subgoal_id)
        if current:
            print()
            print(f"current_subgoal: {current.title}")
            print(f"  status: {current.status.value}")
            print(f"  steps: {current.steps_taken}/{current.bounded_step_budget}")

    return 0


def cmd_plan_next_subgoal(args: argparse.Namespace) -> int:
    """Print current/next subgoal and success criteria."""
    from app.agent_core.plan_memory import PlanMemory

    memory = PlanMemory()

    if args.plan_id:
        plan, _ = memory.load_plan_with_checkpoint(args.plan_id)
    else:
        plan, _ = memory.latest_incomplete_plan()

    if plan is None:
        print("No plan found.")
        return 1

    current = plan.get_current_subgoal()
    next_sg = plan.get_next_pending_subgoal()

    if current:
        print(f"current_subgoal_id: {current.subgoal_id}")
        print(f"title: {current.title}")
        print(f"description: {current.description}")
        print(f"stage_type: {current.stage_type}")
        print(f"status: {current.status.value}")
        print(f"step_budget: {current.bounded_step_budget}")
        print(f"retry_budget: {current.bounded_retry_budget}")
        print(f"steps_taken: {current.steps_taken}")
        print(f"retries_used: {current.retries_used}")
        print()
        print("success_criteria:")
        if current.success_criteria.expected_nodes:
            print(f"  expected_nodes: {list(current.success_criteria.expected_nodes)}")
        if current.success_criteria.expected_connections:
            print(f"  expected_connections: {list(current.success_criteria.expected_connections)}")
        if current.success_criteria.expected_output_path:
            print(f"  expected_output_path: {current.success_criteria.expected_output_path}")
        if current.dependencies:
            print(f"dependencies: {list(current.dependencies)}")
    else:
        print("No current subgoal.")

    if next_sg and next_sg != current:
        print()
        print(f"next_subgoal_id: {next_sg.subgoal_id}")
        print(f"next_title: {next_sg.title}")
        print(f"next_stage_type: {next_sg.stage_type}")

    return 0


def cmd_plan_resume(args: argparse.Namespace) -> int:
    """Resume latest incomplete plan or given plan_id."""
    from app.agent_core.plan_resume import resume_plan, get_resume_summary

    if args.plan_id:
        summary = get_resume_summary(args.plan_id)
        print(summary)
        return 0

    decision = resume_plan(plan_id=None, auto_start=False)

    if not decision.should_resume:
        print(f"Cannot resume: {decision.reason}")
        if decision.warnings:
            for w in decision.warnings:
                print(f"  Warning: {w}")
        return 1

    print(f"plan_id: {decision.plan.plan_id}")
    print(f"domain: {decision.plan.domain}")
    print(f"goal: {decision.plan.goal}")
    print()
    print(f"resume_from_subgoal: {decision.resume_subgoal_id}")

    if decision.tracker:
        state = decision.tracker.current_plan_status()
        print(f"progress: {state.progress_pct:.1f}%")
        print(f"completed: {state.completed_count}")
        print(f"remaining: {state.remaining_subgoals}")

    print()
    print(f"reason: {decision.reason}")

    if decision.warnings:
        print()
        for w in decision.warnings:
            print(f"  Hint: {w}")

    return 0


def cmd_td_long_plan(args: argparse.Namespace) -> int:
    """Create a TD-specific long-horizon plan."""
    from app.domains.touchdesigner.td_long_horizon_planner import create_td_long_horizon_plan

    task_id = args.task_id or f"td_task_{_utc_timestamp()}"
    plan = create_td_long_horizon_plan(
        goal=args.goal,
        task_id=task_id,
        template=args.template,
        layers=args.layers,
    )

    print(f"plan_id: {plan.plan_id}")
    print(f"domain: {plan.domain}")
    print(f"goal: {plan.goal}")
    print(f"template: {args.template}")
    print(f"status: {plan.status.value}")
    print(f"subgoals: {len(plan.subgoals)}")
    print()

    for i, s in enumerate(plan.subgoals, 1):
        print(f"  {i}. [{s.stage_type}] {s.title}")
        if s.dependencies:
            print(f"     deps: {', '.join(s.dependencies)}")

    print()
    print(f"Hint: Use 'plan-status --plan-id {plan.plan_id}' to track progress.")
    return 0


def cmd_houdini_long_plan(args: argparse.Namespace) -> int:
    """Create a Houdini-specific long-horizon plan."""
    from app.domains.houdini.houdini_long_horizon_planner import create_houdini_long_horizon_plan

    task_id = args.task_id or f"hou_task_{_utc_timestamp()}"
    plan = create_houdini_long_horizon_plan(
        goal=args.goal,
        task_id=task_id,
        template=args.template,
    )

    print(f"plan_id: {plan.plan_id}")
    print(f"domain: {plan.domain}")
    print(f"goal: {plan.goal}")
    print(f"template: {args.template}")
    print(f"status: {plan.status.value}")
    print(f"subgoals: {len(plan.subgoals)}")
    print()

    for i, s in enumerate(plan.subgoals, 1):
        print(f"  {i}. [{s.stage_type}] {s.title}")
        if s.dependencies:
            print(f"     deps: {', '.join(s.dependencies)}")

    print()
    print(f"Hint: Use 'plan-status --plan-id {plan.plan_id}' to track progress.")
    return 0


def _utc_timestamp() -> str:
    """Return UTC timestamp string for IDs."""
    from datetime import datetime
    return datetime.utcnow().strftime("%Y%m%d%H%M%S")


def _split_csv(value: str) -> tuple[str, ...]:
    """Split comma-delimited CLI field into normalized tuple."""
    if not value.strip():
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())




















