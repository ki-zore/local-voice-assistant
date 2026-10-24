# Voice Assistant - AI Voice Receptionist

An English-only, 100% local and open-source AI voice receptionist for small businesses (starting with cafes and restaurants). It answers voice calls, answers customer FAQs, checks table availability, books reservations, handles cancellations, and reports all activity to an administrative dashboard.

## Highlights & Constraints
- **Zero Paid APIs**: Everything (STT, LLM, TTS, VAD, database, backend) runs locally with open-source tools.
- **Double-Booking Prevention**: Database-level unique compound indexes guarantee that concurrent or LLM race conditions cannot cause duplicate bookings.
- **Interruptible Conversational Voice**: Low-latency sentence streaming with Silero VAD, faster-whisper, Ollama (`qwen2.5:7b-instruct`), and Piper TTS orchestrated via Pipecat.
- **Multi-Tenant Architecture**: Every collection (`businesses`, `tables`, `bookings`, `calls`) carries a `business_id` from day one.

---

## Architecture & Project Structure

```text
voice-assistant/
├── backend/                  # FastAPI REST API + Motor (MongoDB)
│   ├── app/
│   │   ├── api/              # API routes (availability, bookings, calls, businesses)
│   │   ├── core/             # Database connection, config, indexes
│   │   ├── models/           # Pydantic schemas & MongoDB documents
│   │   ├── services/         # Booking logic & opening hours validation
│   │   └── main.py           # FastAPI application entrypoint
│   ├── scripts/              # Seed scripts (demo cafe with 8 tables, FAQs, hours)
│   ├── tests/                # Pytest suites (double-booking & validation tests)
│   └── requirements.txt
├── voice/                    # Pipecat voice pipeline
│   ├── prompts/
│   │   └── receptionist.md   # Dynamic system prompt with runtime business injection
│   ├── tools/                # LLM function calling definitions (backend API callers)
│   ├── models/               # Local Piper TTS voice models (.onnx)
│   ├── pipeline.py           # Pipecat pipeline (Silero VAD + STT + Ollama + Piper)
│   └── requirements.txt
├── dashboard/                # Next.js (App Router) + TypeScript + Tailwind
├── docker-compose.yml        # Local MongoDB (and mongo-express)
├── .env.example              # Configuration template
├── .env                      # Local environment configuration
└── README.md
```

---

## Windows Prerequisites

Ensure the following tools are installed on your Windows machine:
1. **Python 3.11+** (Python 3.11, 3.12, or 3.13)
2. **Node.js 18+** & npm
3. **Docker Desktop** (with WSL2 backend enabled)
4. **Ollama** for Windows ([Download Ollama](https://ollama.com/download/windows))

---

## Windows Setup Instructions

### 1. Clone & Configure Environment
In PowerShell (as non-admin or admin):
```powershell
# Navigate to project directory
cd "d:\learnings\voice assistant"

# Copy environment template if not already present
Copy-Item .env.example .env
```

### 2. Verify Ollama Model
Make sure Ollama is running and has the `qwen2.5:7b-instruct` model pulled:
```powershell
# Check available models
ollama list

# If not already present, pull the model:
ollama pull qwen2.5:7b-instruct
```

### 3. Start Database (MongoDB) via Docker
Start the Docker Desktop application if it isn't running yet. Then run:
```powershell
# Start MongoDB and Mongo Express in detached mode
docker-compose up -d

# Verify MongoDB is healthy
docker-compose ps
```
- MongoDB is accessible at: `mongodb://localhost:27017`
- Mongo-Express Web UI is accessible at: `http://localhost:8081`

> **Note on MongoDB Atlas / Local MongoDB Service**: If you prefer running MongoDB natively on Windows or using MongoDB Atlas, simply update `MONGODB_URI` in `.env`.

### 4. Setup Python Virtual Environment (Backend & Voice)
```powershell
# Create a virtual environment
python -m venv .venv

# If PowerShell script execution is restricted, temporarily bypass for current session:
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies (Backend and Voice)
pip install -r backend/requirements.txt
pip install -r voice/requirements.txt
```

---

## Execution Phases Overview

- **Phase 0 (Done)**: Scaffolding, docker-compose, environment configuration, Windows setup.
- **Phase 1 (Done)**: FastAPI backend with Motor, MongoDB compound unique indexes, booking validation, seed script, and pytest suites.
- **Phase 2 (Done)**: Text-only LLM tool-calling verification with Ollama `qwen2.5:7b-instruct` across 13 scripted scenarios.
- **Phase 3 (Current)**: Voice pipeline with Silero VAD, Faster-Whisper STT, Ollama LLM, Piper TTS, and Pipecat orchestration.
- **Phase 4**: Next.js admin dashboard with live booking updates, call transcripts, and unanswered question triage.
- **Phase 5**: Telephony planning via SIP trunk.

---

## Running Phase 3 (Voice Pipeline)

### 1. Start Prerequisites
1. **MongoDB**: `docker-compose up -d`
2. **FastAPI Backend**: `.\.venv\Scripts\uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`
3. **Ollama**: Ensure `ollama run qwen2.5:7b-instruct` or the Ollama Windows tray app is running.

### 2. Live Interactive Voice Mode (Microphone + Speaker)
Talk directly to the AI receptionist using your computer microphone and speaker:
```powershell
.\.venv\Scripts\python voice/pipeline.py --verbose
```
- The assistant greets you with: *"Hello! Thank you for calling Demo Cafe. How can I help you today?"*
- Speak into your microphone (e.g. *"What are your hours?"*, *"Do you have Wi-Fi?"*, *"I'd like to reserve a table for 2 tomorrow at 7 PM"*).
- Silero VAD detects speech start and end; Faster-Whisper transcribes speech; Ollama executes tools against the backend; Piper speaks the response aloud.
- Press `Ctrl+C` to end the call and view the session latency summary.

### 3. Automated Voice Pipeline Latency Benchmark
Run the end-to-end voice latency test suite across 4 representative phone call queries:
```powershell
.\.venv\Scripts\python voice/tests/benchmark_voice.py
```
This tests the full audio loop: Synthesizes spoken queries -> Faster-Whisper STT -> Ollama ReceptionistAgent (with backend tool execution) -> Piper TTS, reporting exact latency for every stage.
