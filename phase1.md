You are a senior full-stack engineer. Build "Voice Assistant", an English-only AI voice receptionist for small businesses (first use case: a cafe). It answers calls, responds to FAQs, books tables, and sends everything to an admin dashboard.

## HARD CONSTRAINTS
- English only.
- NO paid AI models or paid AI APIs. Everything for STT, LLM, TTS, and orchestration must be open source and run locally.
- Dev machine: Windows. Use Windows-compatible commands and paths.
- Python 3.11+ for backend and voice pipeline. TypeScript (Next.js) for the dashboard.
- Before using any library API (especially Pipecat), check its current official docs/examples. Do not guess method names or class signatures.

## TECH STACK
- Orchestration: Pipecat (open source)
- VAD: Silero VAD
- STT: faster-whisper (start with "small.en" or "base.en", configurable)
- LLM: Ollama running `qwen2.5:7b-instruct` (already pulled), with tool/function calling
- TTS: Piper (local), configurable voice
- Backend API: FastAPI + Motor (async MongoDB driver) + Pydantic
- Database: MongoDB (local via Docker Compose; connection string in .env so Atlas also works)
- Dashboard: Next.js (App Router) + TypeScript + Tailwind
- Telephony (LATER phase, not now): SIP trunk bridged into the Pipecat pipeline

## PROJECT STRUCTURE
voice-assistant/
  backend/        FastAPI app, models, routes, booking logic, tests
  voice/          Pipecat pipeline, prompts, tool definitions
  dashboard/      Next.js admin app
  docker-compose.yml   (MongoDB, optionally mongo-express)
  .env.example
  README.md       (setup + run instructions for Windows)

## DATA MODEL (MongoDB collections)
- businesses: name, phone_number, timezone, opening_hours (per weekday), faqs[], menu summary, slot_minutes, booking_policy
- tables: business_id, table_number, capacity
- bookings: business_id, table_id, customer_name, customer_phone, party_size, slot_start, slot_end, status (confirmed/cancelled), call_id, created_at
- calls: business_id, started_at, ended_at, transcript[], outcome, unanswered_questions[]
Every document carries business_id (multi-tenant from day one).

DOUBLE-BOOKING PREVENTION: use fixed time slots and a UNIQUE compound index on (business_id, table_id, slot_start) for confirmed bookings, so the database itself rejects conflicts. Never rely on the LLM to prevent double bookings. Handle the duplicate-key error gracefully and return alternative available slots.

## BACKEND API (FastAPI)
- POST /availability  -> given business_id, date/time, party_size, return open slots
- POST /bookings      -> create booking (handles duplicate-key conflicts)
- PATCH /bookings/{id}/cancel
- GET /bookings       -> filter by business_id, date, status
- POST /calls, GET /calls, GET /calls/{id}
- GET /businesses/{id} -> config + FAQs used to build the LLM prompt
- Validate everything with Pydantic. Validate that requested times fall within opening hours and in the future.
- Include a seed script that creates one demo cafe with 8 tables, hours, and ~10 FAQs.

## VOICE PIPELINE (voice/)
Pipeline: audio in -> Silero VAD -> faster-whisper STT -> Ollama LLM (with tools) -> Piper TTS -> audio out. Support interruptions (caller can talk over the bot).

Phase-1 transport: local microphone and speakers only (no phone yet). Keep the transport layer swappable so a telephony transport can be added later without touching the rest.

LLM tools (function calling), each calling the FastAPI backend:
1. check_availability(date, time, party_size)
2. book_table(customer_name, customer_phone, party_size, date, time)
3. cancel_booking(customer_phone, date, time)
4. log_unanswered_question(question)

SYSTEM PROMPT requirements (store in voice/prompts/receptionist.md, inject business config + FAQs at runtime):
- Persona: friendly, concise cafe receptionist.
- Replies must be SHORT and spoken-style: 1-2 sentences, no lists, no markdown, no emojis.
- Ask for exactly one missing detail at a time (name, phone, party size, date, time).
- ALWAYS read back booking details and get a clear "yes" before calling book_table.
- Never invent menu items, prices, or policies. If unknown, say so and call log_unanswered_question, then offer to take a message.
- Convert relative dates ("tomorrow at 7") using the business timezone and current date provided in the prompt.
- Greet on call start; end politely when done.

Also: stream TTS sentence-by-sentence to reduce latency, keep the Ollama model warm (keep_alive), and log per-stage latency (STT, LLM first token, TTS first audio) to the console.

## DASHBOARD (dashboard/)
- Pages: Bookings (today/upcoming, filter, cancel), Calls (list + transcript view), Unanswered Questions, Business Settings (edit hours, FAQs, tables).
- Live updates for new bookings (polling every few seconds is fine for MVP).
- Clean, simple, responsive UI.

## WORKFLOW — IMPORTANT
Work in phases. After each phase: run it, show me how to verify it, and STOP for my confirmation before the next phase.

Phase 0: Scaffold repo, docker-compose for MongoDB, .env.example, README with Windows setup steps.
Phase 1: Backend: models, indexes (incl. the unique booking index), routes, seed script, and pytest tests (especially double-booking and opening-hours validation).
Phase 2: Text-only LLM test: a CLI chat with Ollama qwen2.5:7b-instruct using the real tools against the backend. Include ~10 scripted test conversations (FAQ, clean booking, missing details, unavailable slot, cancellation, unknown question). Report whether tool-calling is reliable.
Phase 3: Add voice with mic/speaker: VAD + faster-whisper + Piper + Pipecat pipeline using the working text logic. Report latency numbers.
Phase 4: Dashboard.
Phase 5: Telephony via SIP trunk (plan only at first; ask me which provider).

## QUALITY RULES
- Type hints, docstrings on public functions, clear error handling, structured logging.
- All secrets/config via .env, nothing hardcoded.
- Keep dependencies minimal and pinned in requirements.txt / package.json.
- If something I asked for is not feasible or a library works differently than assumed, tell me and propose an alternative rather than silently changing the plan.

Start with Phase 0 now. First, show me a short plan of the files you will create, then create them.