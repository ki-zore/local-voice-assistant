"""Automated Voice Latency Benchmark Suite.

Benchmarks the entire audio pipeline:
Audio Query -> Faster-Whisper STT -> Ollama ReceptionistAgent (with Backend Tools) -> Piper TTS.
Measures component-by-component latency and overall End-to-End voice response time.
"""

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Ensure repository root is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from pipecat.frames.frames import AudioRawFrame, TranscriptionFrame
from pipecat.services.piper.tts import PiperTTSService
from pipecat.services.whisper.stt import WhisperSTTService

from voice.receptionist.agent import ReceptionistAgent
from voice.receptionist.backend_client import BackendClient
from voice.receptionist.config import get_voice_config
from voice.receptionist.tools import clean_spoken_text


BENCHMARK_PROMPTS = [
    {
        "id": "faq_hours",
        "category": "FAQ - Hours",
        "query": "What are your opening hours on weekdays?",
    },
    {
        "id": "faq_amenities",
        "category": "FAQ - Amenities",
        "query": "Do you have free Wi-Fi and parking available for customers?",
    },
    {
        "id": "availability_check",
        "category": "Table Availability (Tool Call)",
        "query": "I would like to check availability for 2 people tomorrow at 7 PM.",
    },
    {
        "id": "unknown_question",
        "category": "Unknown Inquiry (Fallback Tool)",
        "query": "Can we bring our own external DJ for a private birthday party?",
    },
]


async def run_voice_benchmark(
    business_id: str,
    model: str,
    whisper_model: str,
    whisper_device: str,
    piper_voice: str,
    backend_url: str,
) -> List[Dict[str, Any]]:
    """Run end-to-end voice latency benchmark across representative test queries."""
    config = get_voice_config()

    print("=" * 80)
    print(" STARTING PHASE 3 VOICE PIPELINE LATENCY BENCHMARK")
    print("=" * 80)
    print(f" LLM Model       : {model} (via Ollama)")
    print(f" STT Engine      : Faster-Whisper ({whisper_model} on {whisper_device})")
    print(f" TTS Engine      : Piper Neural TTS ({piper_voice})")
    print(f" Backend URL     : {backend_url}")
    print("=" * 80)

    # 1. Initialize Components
    print("\n[1/3] Loading Piper TTS and Faster-Whisper models...")
    tts = PiperTTSService(
        settings=PiperTTSService.Settings(voice=piper_voice),
        download_dir=Path(config.piper_download_dir),
    )
    tts._sample_rate = 22050

    stt = WhisperSTTService(
        device=whisper_device,
        compute_type=config.whisper_compute_type,
        settings=WhisperSTTService.Settings(model=whisper_model),
    )

    print("[2/3] Connecting to Receptionist Agent and FastAPI backend...")
    agent = ReceptionistAgent(
        business_id=business_id,
        model=model,
        backend_url=backend_url,
    )
    await agent.initialize()

    results: List[Dict[str, Any]] = []

    print("[3/3] Running benchmark queries through Voice Pipeline...\n")

    for idx, item in enumerate(BENCHMARK_PROMPTS, 1):
        prompt_text = item["query"]
        category = item["category"]
        print(f"[{idx}/{len(BENCHMARK_PROMPTS)}] Testing: {category}")
        print(f"      Spoken Input: \"{prompt_text}\"")

        # Step A: Synthesize query audio to simulate caller voice input
        t_synth_start = time.perf_counter()
        caller_audio_bytes = bytearray()
        async for f in tts.run_tts(prompt_text, context_id=f"synth_{idx}"):
            if isinstance(f, AudioRawFrame):
                caller_audio_bytes.extend(f.audio)
        audio_duration_sec = len(caller_audio_bytes) / (22050 * 2)  # 16-bit mono

        # Step B: Faster-Whisper Speech-to-Text
        t_stt_start = time.perf_counter()
        transcribed_text = ""
        async for f in stt.run_stt(bytes(caller_audio_bytes)):
            if isinstance(f, TranscriptionFrame):
                transcribed_text += f.text.strip() + " "
        stt_latency_ms = (time.perf_counter() - t_stt_start) * 1000
        transcribed_text = transcribed_text.strip()

        print(f"      -> STT Transcribed: \"{transcribed_text}\" (took {stt_latency_ms:.1f}ms)")

        # Step C: Receptionist Agent (Ollama LLM + Tools + Backend)
        t_llm_start = time.perf_counter()
        agent_reply = await agent.respond(transcribed_text or prompt_text)
        llm_latency_ms = (time.perf_counter() - t_llm_start) * 1000

        ttft_ms = agent.ttft_history_ms[-1] if agent.ttft_history_ms else llm_latency_ms
        tools_called = [t["name"] for t in agent.recorded_tool_calls[-1:]] if agent.recorded_tool_calls else []

        print(f"      -> Agent Reply: \"{agent_reply}\" (took {llm_latency_ms:.1f}ms, TTFT: {ttft_ms:.1f}ms)")
        if tools_called:
            print(f"      -> Tools Used: {tools_called}")

        # Step D: Piper TTS (First Audio Frame & Total Synthesis)
        t_tts_start = time.perf_counter()
        tts_first_chunk_ms = None
        assistant_audio_bytes = bytearray()

        clean_text = clean_spoken_text(agent_reply)
        async for f in tts.run_tts(clean_text, context_id=f"reply_{idx}"):
            if isinstance(f, AudioRawFrame):
                if tts_first_chunk_ms is None:
                    tts_first_chunk_ms = (time.perf_counter() - t_tts_start) * 1000
                assistant_audio_bytes.extend(f.audio)

        tts_total_ms = (time.perf_counter() - t_tts_start) * 1000
        tts_first_chunk_ms = tts_first_chunk_ms or tts_total_ms

        print(f"      -> TTS Synthesis: {tts_total_ms:.1f}ms (First audio frame: {tts_first_chunk_ms:.1f}ms)")

        # End-to-End Latency: From speech segment end -> First audible sound from bot
        e2e_latency_ms = stt_latency_ms + llm_latency_ms + tts_first_chunk_ms
        print(f"      ==> Total Turn Latency: {e2e_latency_ms:.1f} ms\n")

        results.append(
            {
                "id": item["id"],
                "category": category,
                "input_query": prompt_text,
                "transcription": transcribed_text,
                "assistant_reply": agent_reply,
                "audio_duration_sec": audio_duration_sec,
                "stt_ms": stt_latency_ms,
                "llm_ttft_ms": ttft_ms,
                "llm_total_ms": llm_latency_ms,
                "tts_first_ms": tts_first_chunk_ms,
                "tts_total_ms": tts_total_ms,
                "e2e_ms": e2e_latency_ms,
                "tools": ", ".join(tools_called) if tools_called else "None",
            }
        )

    await agent.end_call(outcome="completed")
    await agent.close()

    return results


def print_benchmark_report(results: List[Dict[str, Any]]) -> None:
    """Print markdown and terminal formatted latency table."""
    print("=" * 115)
    print(" PHASE 3: VOICE PIPELINE LATENCY REPORT")
    print("=" * 115)
    header = (
        f"{'Category':<28} | {'STT (ms)':<9} | {'LLM TTFT':<9} | "
        f"{'LLM Total':<10} | {'TTS First':<10} | {'E2E Turn':<9} | {'Tools'}"
    )
    print(header)
    print("-" * 115)

    for r in results:
        print(
            f"{r['category'][:28]:<28} | "
            f"{r['stt_ms']:>8.1f} | "
            f"{r['llm_ttft_ms']:>8.1f} | "
            f"{r['llm_total_ms']:>9.1f} | "
            f"{r['tts_first_ms']:>9.1f} | "
            f"{r['e2e_ms']:>8.1f} | "
            f"{r['tools']}"
        )

    print("-" * 115)

    n = len(results)
    avg_stt = sum(r["stt_ms"] for r in results) / n
    avg_ttft = sum(r["llm_ttft_ms"] for r in results) / n
    avg_llm = sum(r["llm_total_ms"] for r in results) / n
    avg_tts = sum(r["tts_first_ms"] for r in results) / n
    avg_e2e = sum(r["e2e_ms"] for r in results) / n

    print(
        f"{'AVERAGE':<28} | "
        f"{avg_stt:>8.1f} | "
        f"{avg_ttft:>8.1f} | "
        f"{avg_llm:>9.1f} | "
        f"{avg_tts:>9.1f} | "
        f"{avg_e2e:>8.1f} | -"
    )
    print("=" * 115)
    print("\nLatency Breakdown Analysis:")
    print(f"  • STT (Faster-Whisper base.en CPU) : ~{avg_stt:.1f} ms")
    print(f"  • LLM TTFT (Ollama qwen2.5:7b)    : ~{avg_ttft:.1f} ms")
    print(f"  • LLM Total (incl. tool calls)    : ~{avg_llm:.1f} ms")
    print(f"  • TTS Time to First Chunk (Piper) : ~{avg_tts:.1f} ms")
    print(f"  • Total End-to-End Voice Latency  : ~{avg_e2e:.1f} ms ({avg_e2e/1000:.2f} seconds)")
    print("=" * 115 + "\n")


async def main():
    config = get_voice_config()
    results = await run_voice_benchmark(
        business_id=config.default_business_id,
        model=config.ollama_model,
        whisper_model=config.whisper_model,
        whisper_device=config.whisper_device,
        piper_voice=config.piper_voice,
        backend_url=config.backend_url,
    )
    print_benchmark_report(results)


if __name__ == "__main__":
    asyncio.run(main())
