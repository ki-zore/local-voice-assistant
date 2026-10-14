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

# Install backend dependencies
pip install -r backend/requirements.txt
```

---

## Execution Phases Overview

- **Phase 0 (Current)**: Scaffolding, docker-compose, environment configuration, Windows setup.
- **Phase 1**: FastAPI backend with Motor, MongoDB compound unique indexes, booking validation, seed script, and pytest suites.
- **Phase 2**: Text-only LLM tool-calling verification with Ollama `qwen2.5:7b-instruct` across 10 scripted scenarios.
- **Phase 3**: Voice pipeline with Silero VAD, faster-whisper STT, Ollama LLM, Piper TTS, and Pipecat orchestration.
- **Phase 4**: Next.js admin dashboard with live booking updates, call transcripts, and unanswered question triage.
- **Phase 5**: Telephony planning via SIP trunk.

---

## Phase 0 Verification

To verify Phase 0 setup:
1. Check that `.env`, `docker-compose.yml`, `backend/requirements.txt`, `voice/requirements.txt`, and `voice/prompts/receptionist.md` exist.
2. Confirm Ollama is running and `qwen2.5:7b-instruct` is available (`ollama list`).
3. Verify Docker Desktop can be started to launch `docker-compose up -d`.
