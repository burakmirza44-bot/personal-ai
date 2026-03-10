#!/usr/bin/env python
"""
Feedback Loop Demo - Kapalı çevrim öğrenme demosu

Bu script, feedback loop sisteminin nasıl çalıştığını gösterir:
1. Inference çalıştırır
2. Çıktıyı değerlendirir
3. Reward hesaplar
4. Training data toplar
5. İyileştirme raporu oluşturur

Kullanım:
    python scripts/demo_feedback_loop.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from feedback.loop import (
    FeedbackOrchestrator,
    FeedbackTask,
    OutputEvaluator,
    RewardCalculator,
    FeedbackDataCollector,
)
from feedback.evaluation import HoudiniValidator, TDValidator


def print_header(title: str):
    """Print section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def print_result(label: str, value):
    """Print labeled result."""
    if isinstance(value, bool):
        symbol = "[OK]" if value else "[FAIL]"
        print(f"  {label}: {symbol}")
    elif isinstance(value, float):
        print(f"  {label}: {value:.2f}")
    else:
        print(f"  {label}: {value}")


def demo_houdini_validation():
    """Demo Houdini output validation."""
    print_header("Houdini Output Validation Demo")

    # Create validator
    validator = HoudiniValidator()

    # Sample Houdini output (box + bevel)
    houdini_output = {
        "nodes": [
            {"name": "geo1", "type": "geo"},
            {"name": "box1", "type": "box"},
            {"name": "bevel1", "type": "polybevel"},
            {"name": "null1", "type": "null"},
        ],
        "connections": [
            {"source": "box1", "target": "bevel1"},
            {"source": "bevel1", "target": "null1"},
        ],
        "parameters": {
            "bevel1.dist": 0.1,
            "bevel1.divisions": 2,
        },
    }

    result = validator.validate(houdini_output)

    print("Validation Result:")
    print_result("Valid", result.valid)
    print_result("Node Graph Valid", result.node_graph_valid)
    print_result("Connections Valid", result.connections_valid)
    print_result("Node Count", result.node_count)
    print_result("Valid Node Types", ", ".join(result.valid_node_types[:5]))

    if result.errors:
        print(f"\n  Errors: {result.errors}")

    return result


def demo_touchdesigner_validation():
    """Demo TouchDesigner output validation."""
    print_header("TouchDesigner Output Validation Demo")

    validator = TDValidator()

    # Sample TD output (video processing chain)
    td_output = {
        "operators": [
            {"name": "moviein1", "type": "moviefilein"},
            {"name": "level1", "type": "level"},
            {"name": "blur1", "type": "blur"},
            {"name": "null1", "type": "null"},
        ],
        "connections": [
            {"source": "moviein1", "target": "level1"},
            {"source": "level1", "target": "blur1"},
            {"source": "blur1", "target": "null1"},
        ],
    }

    result = validator.validate(td_output)

    print("Validation Result:")
    print_result("Valid", result.valid)
    print_result("Operator Graph Valid", result.operator_graph_valid)
    print_result("Operator Count", result.operator_count)

    return result


def demo_feedback_loop():
    """Demo complete feedback loop."""
    print_header("Complete Feedback Loop Demo")

    # Create orchestrator
    orchestrator = FeedbackOrchestrator(domain="houdini")

    # Create sample tasks
    tasks = [
        FeedbackTask(
            task_id="houdini_box_1",
            input_text="Create a box with beveled edges",
            domain="houdini",
        ),
        FeedbackTask(
            task_id="houdini_scatter_1",
            input_text="Scatter points on a grid",
            domain="houdini",
        ),
        FeedbackTask(
            task_id="houdini_chain_1",
            input_text="Build a SOP chain: grid -> scatter -> copytopoints",
            domain="houdini",
        ),
    ]

    # Sample outputs (simulating inference results)
    outputs = [
        """
geo = hou.node('/obj').createNode('geo', 'box_bevel')
box = geo.createNode('box', 'box1')
bevel = geo.createNode('polybevel', 'bevel1')
bevel.setInput(0, box)
bevel.parm('dist').set(0.1)
geo.layoutChildren()
""",
        """
geo = hou.node('/obj').createNode('geo', 'scatter_test')
grid = geo.createNode('grid', 'grid1')
scatter = geo.createNode('scatter', 'scatter1')
scatter.setInput(0, grid)
scatter.parm('npts').set(1000)
geo.layoutChildren()
""",
        """
geo = hou.node('/obj').createNode('geo', 'point_instance')
grid = geo.createNode('grid', 'grid1')
scatter = geo.createNode('scatter', 'scatter1')
copy = geo.createNode('copytopoints', 'copy1')
box = geo.createNode('box', 'box_small')
scatter.setInput(0, grid)
copy.setInput(0, box)
copy.setInput(1, scatter)
geo.layoutChildren()
""",
    ]

    # Run feedback loop
    print("Running feedback loop on 3 tasks...\n")

    for task, output in zip(tasks, outputs):
        result = orchestrator.run_single(task, inference_output=output.strip())

        print(f"Task: {task.task_id}")
        print_result("Score", result.score)
        print_result("Quality Tier", result.quality_tier)
        print_result("Reward Type", result.reward_type)
        print_result("Example Collected", result.example_collected)
        print()

    # Get improvement report
    report = orchestrator.get_improvement_report()

    print("Improvement Report:")
    print_result("Total Iterations", report.total_iterations)
    print_result("Score Trend", report.score_trend)
    print_result("Initial Score", report.initial_score)
    print_result("Final Score", report.final_score)

    # Get status
    status = orchestrator.get_status()

    print("\nSession Status:")
    print_result("Session ID", status["session_id"])
    print_result("Data Summary", status["data_summary"])

    return orchestrator


def demo_curriculum_learning():
    """Demo curriculum learning."""
    print_header("Curriculum Learning Demo")

    from feedback.training import CurriculumLearner

    curriculum = CurriculumLearner()

    # Add examples at different difficulty levels
    examples = [
        # Level 1: Single node
        {"input": "Create a box", "output": "geo.createNode('box')"},
        {"input": "Add a sphere", "output": "geo.createNode('sphere')"},

        # Level 2: Small chain
        {"input": "Create box and transform",
         "output": "box = geo.createNode('box')\nxform = geo.createNode('transform')\nxform.setInput(0, box)"},

        # Level 3: Medium chain
        {"input": "Build scatter setup",
         "output": "grid = geo.createNode('grid')\nscatter = geo.createNode('scatter')\nscatter.setInput(0, grid)\nscatter.parm('npts').set(500)"},

        # Level 4: Complex chain
        {"input": "Create 9-step SOP chain for instancing",
         "output": "grid = geo.createNode('grid')\nscatter = geo.createNode('scatter')\ncopy = geo.createNode('copytopoints')\nbox = geo.createNode('box')\nnull = geo.createNode('null')\n... [full code]"},
    ]

    counts = curriculum.add_examples(examples)

    print("Curriculum Classification:")
    for level, count in counts.items():
        if count > 0:
            print(f"  {level}: {count} examples")

    print(f"\n{curriculum.get_summary()['total_examples']} total examples classified")


def main():
    """Main demo entry point."""
    print()
    print("=" * 61)
    print("        FEEDBACK LOOP - Kapali Cevrim Ogrenme Demo        ")
    print("=" * 61)

    # Run demos
    demo_houdini_validation()
    demo_touchdesigner_validation()
    demo_feedback_loop()
    demo_curriculum_learning()

    print_header("Demo Complete")
    print("Feedback loop sistemi başarıyla çalıştı!")
    print("\nSonraki adımlar:")
    print("  1. faster-whisper kur: pip install faster-whisper")
    print("  2. Gerçek video ile test et")
    print("  3. Training data biriktir")
    print("  4. Fine-tuning başlat")


if __name__ == "__main__":
    main()