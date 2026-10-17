"""Interactive terminal chat interface for testing the Receptionist Agent."""

import argparse
import asyncio
import os
import sys

# Ensure repository root is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.abspath(os.path.join(current_dir, ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from voice.receptionist.agent import ReceptionistAgent
from voice.receptionist.config import get_voice_config


async def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive Voice Assistant Receptionist CLI")
    parser.add_argument("--business-id", default=None, help="Business ID to load (default from .env)")
    parser.add_argument("--model", default=None, help="Ollama model name (default from .env)")
    parser.add_argument("--backend-url", default=None, help="FastAPI backend URL (default from .env)")
    parser.add_argument("--verbose", action="store_true", help="Print tool calls and latency metrics")
    args = parser.parse_args()

    config = get_voice_config()
    business_id = args.business_id or config.default_business_id
    model = args.model or config.ollama_model

    print("=" * 70)
    print(" Voice Assistant Receptionist - Text Test Harness (Phase 2)")
    print(f" Business: {business_id} | Model: {model} | Verbose: {args.verbose}")
    print(" Commands: /reset to clear history, /quit to exit")
    print("=" * 70)

    agent = ReceptionistAgent(
        business_id=business_id,
        model=model,
        backend_url=args.backend_url,
    )
    await agent.initialize()

    # Initial greeting
    print("\nAssistant: Hello! Welcome to Demo Cafe. How can I help you today?\n")

    try:
        while True:
            try:
                user_input = input("Caller: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nExiting chat...")
                break

            if not user_input:
                continue

            if user_input == "/quit":
                print("Ending call...")
                await agent.end_call(outcome="caller_hung_up")
                break

            if user_input == "/reset":
                print("\n[Resetting conversation session...]\n")
                await agent.end_call(outcome="reset")
                await agent.close()
                agent = ReceptionistAgent(
                    business_id=business_id,
                    model=model,
                    backend_url=args.backend_url,
                )
                await agent.initialize()
                print("Assistant: Hello! Welcome to Demo Cafe. How can I help you today?\n")
                continue

            prev_tool_count = len(agent.recorded_tool_calls)
            reply = await agent.respond(user_input)

            if args.verbose:
                # Print newly executed tool calls
                new_tools = agent.recorded_tool_calls[prev_tool_count:]
                for t in new_tools:
                    print(f"  [Tool Call] {t['name']}({t['args']}) -> {t['result']} ({t['duration_ms']:.1f}ms)")

                if agent.ttft_history_ms:
                    last_ttft = agent.ttft_history_ms[-1]
                    last_tot = agent.total_duration_history_ms[-1]
                    print(f"  [Latency] TTFT: {last_ttft:.1f}ms | Total: {last_tot:.1f}ms")

            print(f"\nAssistant: {reply}\n")

    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(main())
