# NOW — trainsight

## Status

IN PROGRESS — Stage 8 steps 8.1–8.10 complete.

## Next

Step 8.11 (Antigravity) — copy prompt from build-stage.html, execute in Google Antigravity:
→ generates `src/skills/briefing.py` + `app/briefing/agent.py` + agents-cli enhance

Then continue 8.11 → 8.12 sequentially via Antigravity prompts.
Claude Code resumes at Step 8.13 (deploy_agents.sh) and 8.14 (Dockerfile.web + deploy_web.sh).

## Context

- GitHub: `github.com/footnote42/trainsight` (public, pushed 2026-06-25)
- Obsidian: `C:/Users/kenho/Obsidian/Second Brain/Projects/Kaggle-Capstone/`
- Design phase locked: PRD.md, DESIGN.md, FR.md, SAFETY.md, EVALUATION.md, TR.md v1.1
- Build plan (authority): `C:/Users/kenho/.claude/plans/i-need-to-start-agile-pike.md`

## Architecture (locked)

- ADK agents (`app/challenger/`, `app/briefing/`) → Agent Runtime + Agent Registry
- Web UI + FastAPI (`src/web/app.py`, `static/`) → Cloud Run (`trainsight-web`, min-instances 1)
- MCP servers: stdio in-process within Cloud Run container
- HITL token: FastAPI-managed (`itsdangerous`, TR-SEC-002)
- Manager Briefing: `agents-cli run` against Agent Runtime

## Stage 8 Checklist

- [x] 8.1 Antigravity → `src/models.py`
- [x] 8.2 Antigravity → `src/security.py`
- [x] 8.3 Antigravity → `src/mcp/catalogue_server.py`
- [x] 8.4 Antigravity → `src/mcp/workday_server.py`
- [x] 8.5 Antigravity → `src/mcp/submissions_server.py`
- [x] 8.6 Antigravity → `src/validators.py`
- [x] 8.7 Antigravity → `src/skills/fetch.py`
- [x] 8.8 Antigravity → `app/challenger/agent.py` + agents-cli enhance
- [x] 8.9 Antigravity → `src/web/app.py` + `src/startup.py`
- [x] 8.10 Antigravity → `static/index.html` (+ app.py: DirectReportInfo, /api/session/mode, GET /api/session/basket, basket_overrides)
- [ ] 8.11 Antigravity → `src/skills/briefing.py` + `app/briefing/agent.py` + agents-cli enhance
- [ ] 8.12 Antigravity → `eval/harness.py`
- [ ] 8.13 Claude Code → `deploy_agents.sh`, `verify_deployment.sh`
- [ ] 8.14 Claude Code → `Dockerfile.web`, `.dockerignore`, `deploy_web.sh`

## Blocker

None.

## Design Decision — PII Demo

workday.csv now includes name/email/age_band columns (added 2026-06-24). These are
intentional mock PII. workday_server.py (Step 8.4) must explicitly exclude them when
constructing PersonProfile — the exclusion IS the demonstration. security.py (Step 8.2)
adds _pii_guard() as defence-in-depth text scanner. TR.md updated with pii_guard_triggered
event type and _assert_no_pii audit logging spec.

## Last session

2026-06-25 — UI preview validated via offline stub (index.dev.html); all 3 screens rendered correctly; no regressions found.
