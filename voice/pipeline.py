"""Voice Assistant Pipeline - Real-time Voice Receptionist with Pipecat,

Silero VAD, Faster-Whisper STT, Ollama LLM, and Piper TTS.
"""

import argparse
import asyncio
import os
import signal
import sys
import time
from pathlib import Path

# Ensure repository root is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.abspath(os.path.join(current_dir, ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.services.whisper.stt import WhisperSTTService
from pipecat.services.piper.tts import PiperTTSService
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineTask
from pipecat.pipeline.runner import PipelineRunner

from voice.receptionist.agent import ReceptionistAgent
from voice.receptionist.config import get_voice_config
from voice.receptionist.voice_processor import ReceptionistVoiceProcessor


async def run_voice_pipeline(
    business_id: str,
    model: str,
    whisper_model: str,
    whisper_device: str,
    piper_voice: str,
    backend_url: str,
    verbose: bool = True,
) -> None:
    """Build and run the real-time Pipecat voice pipeline."""
    config = get_voice_config()

    print("=" * 70)
    print(" VOICE ASSISTANT - LOCAL AI VOICE RECEPTIONIST (PHASE 3)")
    print("=" * 70)
    print(f" Business ID     : {business_id}")
    print(f" LLM Model       : {model} (via Ollama)")
    print(f" Speech-to-Text  : Faster-Whisper ({whisper_model} on {whisper_device})")
    print(f" Text-to-Speech  : Piper ({piper_voice})")
    print(f" Voice Activity  : Silero VAD (stop_secs={config.vad_stop_secs}s)")
    print(f" Backend API     : {backend_url}")
    print("=" * 70)
    print(" Press Ctrl+C at any time to end the call and view latency telemetry.\n")

    # 1. Initialize the receptionist conversation engine (from Phase 2)
    agent = ReceptionistAgent(
        business_id=business_id,
        model=model,
        backend_url=backend_url,
    )
    await agent.initialize()

    # 2. Voice Activity Detection (Silero VAD)
    vad_analyzer = SileroVADAnalyzer(
        params=VADParams(stop_secs=config.vad_stop_secs),
    )
    vad_processor = VADProcessor(vad_analyzer=vad_analyzer)

    # 3. Speech-to-Text (Faster-Whisper on CPU with int8 quantization)
    stt_service = WhisperSTTService(
        device=whisper_device,
        compute_type=config.whisper_compute_type,
        settings=WhisperSTTService.Settings(model=whisper_model),
    )

    # 4. Receptionist Bridge Processor
    greeting = f"Hello! Thank you for calling {agent.business_name}. How can I help you today?"
    voice_processor = ReceptionistVoiceProcessor(
        agent=agent,
        greeting_text=greeting,
        verbose=verbose,
    )

    # 5. Text-to-Speech (Piper Neural TTS)
    tts_service = PiperTTSService(
        settings=PiperTTSService.Settings(voice=piper_voice),
        download_dir=Path(config.piper_download_dir),
    )

    # 6. Local Audio Transport (Microphone + Speaker via PyAudio)
    transport = LocalAudioTransport(
        params=LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=16000,
            audio_out_sample_rate=22050,
        )
    )

    # 7. Assemble sequential pipeline
    pipeline = Pipeline(
        [
            transport.input(),
            vad_processor,
            stt_service,
            voice_processor,
            tts_service,
            transport.output(),
        ]
    )

    task = PipelineTask(pipeline)
    runner = PipelineRunner()

    # Schedule greeting right after pipeline starts
    async def schedule_greeting():
        await asyncio.sleep(0.8)
        await voice_processor.send_greeting()

    greeting_coro = asyncio.create_task(schedule_greeting())

    try:
        await runner.run(task)
    except (asyncio.CancelledError, KeyboardInterrupt):
        print("\nCall terminating...")
    finally:
        greeting_coro.cancel()
        await agent.end_call(outcome="completed")
        await agent.close()

        # Print session latency summary
        print("\n" + "=" * 70)
        print(" CALL SESSION LATENCY & TELEMETRY SUMMARY")
        print("=" * 70)
        turns = len(voice_processor.turn_latencies)
        print(f" Total Conversational Turns : {turns}")

        if turns > 0:
            avg_ttft = sum(t["ttft_ms"] for t in voice_processor.turn_latencies) / turns
            avg_llm = sum(t["llm_total_ms"] for t in voice_processor.turn_latencies) / turns
            avg_turn = sum(t["turn_duration_ms"] for t in voice_processor.turn_latencies) / turns
            total_tools = sum(t["tool_calls_count"] for t in voice_processor.turn_latencies)

            print(f" Average LLM TTFT           : {avg_ttft:.1f} ms")
            print(f" Average LLM Turn Latency   : {avg_llm:.1f} ms")
            print(f" Average Total Turn Latency : {avg_turn:.1f} ms")
            print(f" Total Tool Calls Executed  : {total_tools}")
        else:
            print(" No user turns were recorded in this session.")
        print("=" * 70 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Voice Assistant Pipecat Pipeline")
    parser.add_argument("--business-id", default=None, help="Business ID to load (default from .env)")
    parser.add_argument("--model", default=None, help="Ollama LLM model (default from .env)")
    parser.add_argument("--whisper-model", default=None, help="Faster-Whisper model size (default from .env)")
    parser.add_argument("--whisper-device", default=None, help="Whisper compute device ('cpu' or 'cuda')")
    parser.add_argument("--piper-voice", default=None, help="Piper TTS voice model (default from .env)")
    parser.add_argument("--backend-url", default=None, help="FastAPI backend URL")
    parser.add_argument("--verbose", action="store_true", default=True, help="Print detailed latency and turns")
    args = parser.parse_args()

    config = get_voice_config()
    business_id = args.business_id or config.default_business_id
    model = args.model or config.ollama_model
    whisper_model = args.whisper_model or config.whisper_model
    whisper_device = args.whisper_device or config.whisper_device
    piper_voice = args.piper_voice or config.piper_voice
    backend_url = args.backend_url or config.backend_url

    asyncio.run(
        run_voice_pipeline(
            business_id=business_id,
            model=model,
            whisper_model=whisper_model,
            whisper_device=whisper_device,
            piper_voice=piper_voice,
            backend_url=backend_url,
            verbose=args.verbose,
        )
    )


if __name__ == "__main__":
    main()
