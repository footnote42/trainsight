# trainsight — Training Requirements Agent

Kaggle Capstone 2026 — Track: **Agents for Business**

## Problem

Staff and line managers submit training requests through a form with no feedback loop. They over-request, mark almost everything High priority because there's no cost to doing so, and misclassify aspirational development as Critical/Scarce Skill because it sounds more likely to get approved. By the time the submission window closes, the training manager is sitting on noisy data and has to manually chase, verify, and deduplicate before presenting a budget case.

## Solution

Two ADK agents:

- **Submission Challenger** (web app) — reviews each course request in real time against the submitter's role profile and prior team submissions. Fires five challenge types: role eligibility, priority inflation, reason coherence, quantity (line-manager mode), duplicates. Nothing writes to the submissions store without explicit human confirmation (HITL).
- **Manager Briefing** (CLI) — post-deadline batch run. Aggregates all submissions for a period and produces a markdown report: cost totals, course demand ranking, unresolved flags, and a **questionable-spend total** (the estimated cost attached to flagged/duplicated/inflated requests).

**What it does not do:** approve or reject requests, check training history, suggest alternative courses, comment on individual performance, or integrate with the real Power App/SharePoint. All decisions stay with the training manager. Full detail in `PRD.md` §4 (Obsidian).

## Architecture

```
Browser → Cloud Run (trainsight-web)
            ├── FastAPI (src/web/app.py)
            │   ├── catalogue-mcp    (in-process stdio, read-only, no PII)
            │   ├── workday-mcp      (in-process stdio, read-only, PII scrubbed pre-LLM)
            │   └── submissions-mcp  (in-process stdio, HITL-gated write)
            └── VertexAiSessionService → Agent Runtime
                    ├── app/challenger/  (Submission Challenger)
                    └── app/briefing/    (Manager Briefing)
```

Challenge firing is deterministic Python (`src/validators.py`); the LLM's job is reason-coherence judgement and challenge phrasing/tone. This keeps correctness stable and isolates what the LLM is actually for — see the evaluation delta below.

## Capstone concept coverage

| Concept | Implementation | Evidence |
|---------|---------------|---------|
| Multi-agent system (ADK) | Submission Challenger + Manager Briefing | Code |
| MCP Server | `catalogue-mcp`, `workday-mcp`, `submissions-mcp` | Code |
| Antigravity | `UX-DESIGN.md` / `PRD.md` git-dated before any `src/` commit | Video |
| Security | Pre-LLM PII scrub, HITL gate, least-privilege MCP access, injection sanitisation, audit log | Code + Video |
| Deployability | Docker container on Cloud Run, live HTTPS URL | Video |
| Agent Skills (Agents CLI) | `adk run app/briefing` | Code + Video |

## Setup

### Local development

```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env   # fill in GOOGLE_CLOUD_PROJECT, agent runtime IDs
uvicorn src.web.app:app --reload --port 8080
```

Required env vars: `GOOGLE_CLOUD_PROJECT`, `CHALLENGER_AGENT_RUNTIME_ID`, `BRIEFING_AGENT_RUNTIME_ID`. See `.env.example` for the full list and defaults.

### Cloud Run deployment

```bash
./deploy_agents.sh   # deploys both ADK agents to Vertex AI Agent Runtime
./deploy_web.sh       # builds + deploys trainsight-web via gcloud run deploy --source .
```

Manager Briefing CLI:

```bash
adk run app/briefing "Generate a briefing report for period 2026-Q2" > briefing-2026-Q2.md
```

## Demo

- **Live URL:** https://trainsight-web-498756534840.us-central1.run.app
- **Video:** [YOUTUBE_URL]

## Evaluation results

Full run: `eval/results/full_001.md` · Rules-only baseline: `eval/results/rules_001.md`

| Metric | Tuned (1–5) | Held-out (H1–H3) |
|---|---|---|
| Correctness | 10 / 10 | 5 / 5 |
| Avg LLM judge score | 10.0 / 10 | 9.75 / 10 |
| Min tone score | 3 / 3 | 3 / 3 |

Held-out scenarios were never used to tune the Challenger prompt — they exist to distinguish real evaluation from a memorisation test.

**Rules-only vs full-mode delta** (evidence the LLM earns its place — correctness is identical either way, the LLM's contribution is tone and justification quality):

| Metric | Rules-only | Full (LLM) | Delta |
|---|---|---|---|
| Avg judge total | 9.38 | 10.00 | +0.63 |
| Avg tone | 2.75 | 3.00 | +0.25 |
| Avg justification | 2.62 | 3.00 | +0.38 |
| Avg actionability | 2.00 | 2.00 | +0.0 |

## Repo layout

```
app/
  challenger/   Submission Challenger ADK agent
  briefing/     Manager Briefing ADK agent
src/
  mcp/          catalogue, workday, submissions MCP servers
  skills/       fetch.py (shared), briefing.py (briefing-only)
  validators.py pure Python challenge validators
  security.py   HITL token, audit, PII guard, injection sanitiser
  web/app.py    FastAPI app
config/
  model_config.py
static/
  index.html    single-file web UI
eval/
  harness.py    CLI evaluation harness
data/
  catalogue.json  35 mock courses
  workday.csv     150 mock staff, no PII beyond role/grade/chain
```

Mock data throughout — no real employee data, no real SharePoint/Workday connections. See `PRD.md` §11 (Obsidian) for the enterprise transfer path.
