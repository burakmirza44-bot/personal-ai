"""TouchDesigner demo workflow helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.domains.touchdesigner.td_execution_loop import TDExecutionLoop, TDRunReport
from app.domains.touchdesigner.td_executor import TDExecutor, TDDemoExecutionReport
from app.domains.touchdesigner.td_tasks import TDDemoTask, build_basic_top_chain_demo_task


@dataclass(slots=True)
class TDDemoPackage:
    """Compiled package for the first TD demo flow."""

    task: TDDemoTask
    report: TDDemoExecutionReport


def build_closed_loop_demo_task() -> TDDemoTask:
    """Return the closed-loop MVP demo task (basic_top_chain)."""
    return build_basic_top_chain_demo_task()


def run_closed_loop_demo(
    dry_run: bool = True,
    use_live_bridge: bool = False,
    target_network: str = "/project1",
) -> TDRunReport:
    """Run bounded closed-loop demo for the first TD task."""
    loop = TDExecutionLoop()
    return loop.run_basic_top_chain(
        target_network=target_network,
        dry_run=dry_run,
        use_live_bridge=use_live_bridge,
    )


def build_first_td_demo_package(network_path: str = "/project1") -> TDDemoPackage:
    """Build the first practical TD demo package."""
    task = build_basic_top_chain_demo_task()
    executor = TDExecutor()
    report = executor.prepare_demo(task=task, network_path=network_path)
    return TDDemoPackage(task=task, report=report)


def export_first_td_demo_assets(repo_root: Path, network_path: str = "/project1") -> tuple[Path, Path]:
    """Export demo script and a concise report file."""
    package = build_first_td_demo_package(network_path=network_path)
    executor = TDExecutor()

    script_path = repo_root / "scripts" / "td" / "basic_top_chain_demo.py"
    report_path = repo_root / "reports" / "td_demo" / "basic_top_chain_demo_report.txt"

    executor.export_demo_script(package.report, script_path)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_text = (
        f"task_id: {package.task.task_id}\n"
        f"task_name: {package.task.name}\n"
        f"goal: {package.task.goal}\n"
        f"operator_sequence: {', '.join(package.task.operator_sequence)}\n"
        f"eval_passed: {package.report.eval_result.passed}\n"
        f"eval_score: {package.report.eval_result.score}\n"
        f"notes: {' | '.join(package.report.eval_result.notes)}\n"
    )
    report_path.write_text(report_text, encoding="utf-8")

    return script_path, report_path