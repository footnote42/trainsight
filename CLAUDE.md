# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**trainsight** — a Training Requirements Agent built as a Kaggle Capstone project using Google ADK 2.0 + Gemini via Vertex AI. GitHub: `github.com/footnote42/trainsight`. Project planning lives in Obsidian at `C:\Users\kenho\Obsidian\Second Brain\Projects\Kaggle-Capstone\`.

## Environment

- Windows 11, bash shell (Unix syntax — forward slashes in paths)
- Python 3.11, `venv` at `.venv/`
- No Jupyter notebooks — production pipeline only (`.py` scripts)

## Commands

```bash
# activate env
source .venv/Scripts/activate

# install deps
pip install -r requirements.txt

# run FastAPI dev server
uvicorn src.web.app:app --reload --port 8080

# run eval harness (rules-only, no LLM calls)
python eval/harness.py --scenario all --rules-only --output eval/results/smoke.json

# run eval harness (full LLM)
python eval/harness.py --scenario all --output eval/results/full.json

# MCP server self-checks
python src/mcp/catalogue_server.py
python src/mcp/workday_server.py
python src/mcp/submissions_server.py

# validators self-check
python src/validators.py

# lint / format
ruff check .
ruff format .
```

## Stack (confirmed, locked)

| Layer | Technology |
|---|---|
| Agents | Google ADK 2.0 — `LlmAgent` |
| LLM | Gemini 1.5 Pro via Vertex AI |
| Agent hosting | Vertex AI Agent Runtime (Agent Registry) |
| Web UI / API | FastAPI + plain HTML/JS (`static/index.html`) |
| Web hosting | Google Cloud Run (`trainsight-web`, min-instances 1) |
| MCP servers | stdio in-process within Cloud Run web container |
| Session mgmt | `VertexAiSessionService` (Cloud Run → Agent Runtime) |
| HITL token | FastAPI-managed (`itsdangerous`, TR-SEC-002) |
| Audit log | `data/audit.log` (append-only JSON lines) |

## Architecture

```
Browser → Cloud Run (trainsight-web)
            ├── FastAPI (src/web/app.py)
            │   ├── catalogue-mcp  (in-process stdio)
            │   ├── workday-mcp    (in-process stdio)
            │   └── submissions-mcp (in-process stdio, HITL-gated write)
            └── VertexAiSessionService → Agent Runtime
                    ├── app/challenger/  (Submission Challenger)
                    └── app/briefing/    (Manager Briefing)
```

## Layout

See `LAYOUT.md` for TR.md path → scaffold path mapping. Agents live under `app/` (agents-cli requirement); all other TR.md paths are literal.

```
app/
  challenger/   — Submission Challenger ADK agent
  briefing/     — Manager Briefing ADK agent
src/
  mcp/          — catalogue, workday, submissions MCP servers
  skills/       — fetch.py (shared), briefing.py (briefing-only)
  validators.py — pure Python challenge validators
  security.py   — HITL token, audit, PII guard, injection sanitiser
  models.py     — all shared dataclasses
  web/app.py    — FastAPI app
  startup.py    — env validation
config/
  model_config.py
static/
  index.html    — single-file web UI
eval/
  harness.py    — CLI eval harness
data/
  catalogue.json   — 35 courses (mock, committed)
  workday.csv      — 150 staff (mock, committed, no PII)
  scenarios/       — 5 tuned + 3 held-out scenario JSON files
```

## Key Files

- `NOW.md` — current sprint focus and immediate next steps
- `LAYOUT.md` — TR.md path → scaffold path mapping
- `LAYOUT.md` — deployment split table
- `.env` — API keys and runtime IDs (never committed)
- `.env.example` — template for all required env vars
- `requirements.txt` — runtime deps (google-adk, google-cloud-aiplatform, fastapi, uvicorn, python-dotenv, pydantic, itsdangerous)
- `C:/Users/kenho/.claude/plans/i-need-to-start-agile-pike.md` — build coordination plan (authority)
- Obsidian docs: `TR.md` (v1.1), `FR.md`, `DESIGN.md`, `SAFETY.md`, `EVALUATION.md`, `PRD.md`

## Security Constraints (never relax)

- `age_band`, `name`, `email` must never appear in PersonProfile, AuditLogEntry values, or API responses
- Held-out scenarios H1, H2, H3 must never be used to tune agent prompts
- HITL token marked `used=True` BEFORE any MCP write — not after
- On submissions-mcp error: zero records written; audit entry with `outcome='failure'` still written
- Verbatim system prompt strings from SAFETY.md must not be softened or paraphrased

## Build Coordination

Steps 8.1–8.12 are Antigravity prompts — copy from plan file and execute in Google Antigravity.
Claude Code's next contribution: Step 8.13 (deploy_agents.sh) and Step 8.14 (Dockerfile.web + deploy_web.sh).
