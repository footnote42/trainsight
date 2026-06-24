# NOW — Kaggle-Capstone

## Status
IN PROGRESS — Build plan approved; Stage 7 (mock data) ready to execute

## Next
Execute Stage 7 steps 7.1–7.5 (mock data files), then Stage 8 via Antigravity prompts.

## Context
- Obsidian: `C:/Users/kenho/Obsidian/Second Brain/Projects/Kaggle-Capstone/`
- Design phase complete and locked: PRD.md, DESIGN.md, FR.md, SAFETY.md, EVALUATION.md, TR.md v1.1
- TR.md v1.1 written 2026-06-24 — upversioned to reflect Agent Runtime + Cloud Run split architecture
- Build plan: `C:/Users/kenho/.claude/plans/i-need-to-start-agile-pike.md`
- Stack: Google ADK + Gemini/Vertex AI + FastAPI + plain HTML/JS + Agent Runtime + Cloud Run + stdio MCP (in-process)

## Architecture (locked)
- ADK agents (`app/challenger/`, `app/briefing/`) → **Agent Runtime** + Agent Registry
- Web UI + FastAPI (`src/web/app.py`, `static/`) → **Cloud Run** (`trainsight-web`, min-instances 1)
- HITL token: FastAPI-managed (TR-SEC-002 unchanged)
- Manager Briefing: `agents-cli run` against Agent Runtime

## Blocker
None

## Last session
2026-06-24 — Finalised build plan; updated TR.md v1.0→1.1, FR.md FR-022, DESIGN.md to align
with Agent Runtime deployment architecture. Step 7.1 JSON schemas dropped (no runtime consumer).
`itsdangerous` added to requirements. Cloud Run min-instances corrected to 1.
