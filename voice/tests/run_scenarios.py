"""Test runner executing the Phase 2 scenario test suite against Ollama."""

import argparse
import asyncio
from datetime import datetime
import os
import sys
import time
from typing import Any, Dict, List

# Ensure repository root is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from voice.receptionist.agent import ReceptionistAgent
from voice.receptionist.backend_client import BackendClient
from voice.receptionist.config import get_voice_config
from voice.tests.scenarios import build_all_scenarios


async def run_scenario_iteration(
    scenario,
    backend: BackendClient,
    business_id: str,
    model: str,
    backend_url: str,
) -> Dict[str, Any]:
    """Execute a single scenario iteration and evaluate results."""
    context: Dict[str, Any] = {}
    if scenario.setup_fn:
        await scenario.setup_fn(backend, business_id, context)

    agent = ReceptionistAgent(
        business_id=business_id,
        model=model,
        backend_url=backend_url,
    )
    await agent.initialize()

    responses: List[str] = []
    try:
        for turn in scenario.turns:
            reply = await agent.respond(turn)
            responses.append(reply)

        if scenario.eval_fn:
            passed, failure_mode = await scenario.eval_fn(agent, responses, backend, business_id, context)
        else:
            passed, failure_mode = True, "No evaluation function"

    except Exception as exc:
        passed = False
        failure_mode = f"Unhandled Exception: {str(exc)}"

    finally:
        if scenario.teardown_fn:
            try:
                await scenario.teardown_fn(backend, business_id, context)
            except Exception:
                pass
        await agent.end_call(outcome="completed")
        await agent.close()

    # Collect telemetry
    ttft_avg = sum(agent.ttft_history_ms) / len(agent.ttft_history_ms) if agent.ttft_history_ms else 0.0
    tot_avg = sum(agent.total_duration_history_ms) / len(agent.total_duration_history_ms) if agent.total_duration_history_ms else 0.0
    tool_count = len(agent.recorded_tool_calls)

    return {
        "passed": passed,
        "failure_mode": failure_mode if not passed else "-",
        "ttft_ms": ttft_avg,
        "total_ms": tot_avg,
        "tool_count": tool_count,
        "turns_count": len(responses),
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run Receptionist Agent Scenario Suite")
    parser.add_argument("--iterations", "-n", type=int, default=5, help="Number of repetitions per scenario")
    parser.add_argument("--model", default=None, help="Ollama model to evaluate (default from .env)")
    parser.add_argument("--business-id", default=None, help="Business ID to test against")
    parser.add_argument("--backend-url", default=None, help="FastAPI backend URL")
    parser.add_argument("--scenario", default=None, help="Run only scenario matching substring/id")
    args = parser.parse_args()

    config = get_voice_config()
    business_id = args.business_id or config.default_business_id
    model = args.model or config.ollama_model
    backend_url = args.backend_url or config.backend_url

    backend = BackendClient(base_url=backend_url)

    # Verify backend is running
    try:
        await backend.get_business(business_id)
    except Exception as e:
        print(f"ERROR: Cannot reach backend at {backend_url}: {e}")
        print("Please start the backend server before running scenarios.")
        return

    all_scenarios = build_all_scenarios()
    if args.scenario:
        all_scenarios = [s for s in all_scenarios if args.scenario.lower() in s.id.lower() or args.scenario.lower() in s.title.lower()]

    print("\n" + "=" * 80)
    print(f" STARTING PHASE 2 EVALUATION: {len(all_scenarios)} Scenarios x {args.iterations} Iterations")
    print(f" Model: {model} | Business: {business_id} | Backend: {backend_url}")
    print("=" * 80 + "\n")

    scenario_results: List[Dict[str, Any]] = []
    all_ttft: List[float] = []
    all_total_lat: List[float] = []
    all_tool_counts: List[int] = []
    all_turns_counts: List[int] = []

    suite_start = time.perf_counter()

    for idx, sc in enumerate(all_scenarios, 1):
        print(f"[{idx}/{len(all_scenarios)}] Testing: {sc.title} ({sc.id})...", end="", flush=True)
        passes = 0
        failure_modes: List[str] = []

        for it in range(args.iterations):
            res = await run_scenario_iteration(sc, backend, business_id, model, backend_url)
            if res["passed"]:
                passes += 1
            else:
                failure_modes.append(res["failure_mode"])

            if res["ttft_ms"] > 0:
                all_ttft.append(res["ttft_ms"])
            if res["total_ms"] > 0:
                all_total_lat.append(res["total_ms"])
            all_tool_counts.append(res["tool_count"])
            all_turns_counts.append(res["turns_count"])
            print(".", end="", flush=True)

        pass_rate = (passes / args.iterations) * 100
        common_fail = failure_modes[0] if failure_modes else "-"
        print(f" {pass_rate:.0f}% ({passes}/{args.iterations})")

        scenario_results.append(
            {
                "id": sc.id,
                "title": sc.title,
                "passes": passes,
                "total": args.iterations,
                "pass_rate": pass_rate,
                "common_fail": common_fail,
            }
        )

    suite_dur = time.perf_counter() - suite_start
    await backend.close()

    # Print Summary Report Table
    print("\n" + "=" * 90)
    print(" PHASE 2: LLM RECEPTIONIST EVALUATION REPORT")
    print("=" * 90)
    print(f"{'Scenario':<34} | {'Pass Rate':<10} | {'Common Failure Mode':<40}")
    print("-" * 90)
    for r in scenario_results:
        print(f"{r['title']:<34} | {r['pass_rate']:>7.0f}%   | {r['common_fail'][:40]:<40}")
    print("-" * 90)

    # Print Latency & Telemetry
    avg_ttft = sum(all_ttft) / len(all_ttft) if all_ttft else 0.0
    avg_total_lat = sum(all_total_lat) / len(all_total_lat) if all_total_lat else 0.0
    total_turns = sum(all_turns_counts)
    total_tools = sum(all_tool_counts)
    avg_tools_per_reply = total_tools / total_turns if total_turns else 0.0

    print(f"Overall Pass Rate: {sum(r['passes'] for r in scenario_results) / (len(scenario_results) * args.iterations) * 100:.1f}%")
    print(f"Average Time to First Token (TTFT): {avg_ttft:.1f} ms")
    print(f"Average Total Duration per LLM Call: {avg_total_lat:.1f} ms")
    print(f"Average Tool Calls per Turn: {avg_tools_per_reply:.2f}")
    print(f"Total Evaluation Duration: {suite_dur:.1f} seconds")
    print("=" * 90 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
