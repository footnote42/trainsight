# NOW — Kaggle Capstone (Training Requirements Agent)

## Status
IN PROGRESS — Design phase complete. FR.md written (Stage 5). Ready for implementation.

## Next
Write mock data: hand-author `catalogue.json` (~35 courses with target_roles + SME), `workday.csv` (~150 staff, grades A1–DS, management chains), and seeded submission records split into tuned set (scenarios 1–5) and held-out set (H1–H3). Nothing agentic runs until data exists; the split is what keeps evaluation defensible.

## Open actions
1. **Time-period drift** — UX-DESIGN Screen 1 says window closes "31 March 2026"; briefing/CLI use "2025-Q4". Pick one timeline across all docs before writing mock data.
2. **UX grade slip** — Screen 2 walkthrough user at C2; Screen 4 says "B2". Pick one for the example persona.

## Context
- Plans + pipeline (Obsidian): `C:/Users/kenho/Obsidian/Second Brain/Projects/Kaggle-Capstone/project-pipeline.html`
- Docs (Obsidian): PRD.md (v1.1), DESIGN.md, UX-DESIGN.md, SAFETY.md, EVALUATION.md, FR.md (new)
- Ideas log (Obsidian): IDEAS.md
- Code repo (this file's root): `C:/Users/kenho/Projects/Kaggle-Capstone/`
- Stack: Google ADK + Gemini (Vertex AI), 3 MCP servers (in-process), 2 agents, Cloud Run, mock data
- Submission deadline: 6 July 2026

## Blocker
None. Open actions should be settled before writing mock data but do not block starting the data schema.

## Last session
2026-06-23 — Wrote FR.md (22 FRs across 6 scopes: Submission Challenger, Manager Briefing, Data, Shared, Evaluation, Deployment). All EVALUATION scenarios mapped to specific ACs; all SAFETY hard boundaries have at least one AC.
