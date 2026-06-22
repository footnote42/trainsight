# NOW — Kaggle Capstone (Training Requirements Agent)

## Status
IN PROGRESS — Design phase. Pipeline Stage 4 (PRD) complete and council-reviewed. Stage 5 (FR.md) not started.

## Next
Write Stage 5 — `FR.md` (Functional Requirements): testable statements with pass/fail conditions, use cases mapped from UX-DESIGN.md, acceptance criteria linked to EVALUATION.md scenarios (including the new held-out set).

## Open actions (carried from council review, 2026-06-22)
1. **Verify Kaggle rubric** — confirm actual "Agents for Business" scoring weights before locking scope. Council flagged nobody has checked what judges actually grade.
2. **Define cut-line** — explicit minimum demoable slice that still wins the rubric if week 2 slips. Needed before build starts.
3. **Mock data first action (Monday)** — hand-author `catalogue.json`, `workday.csv`, and seeded submission records; split at creation into a tuned set and a held-out set. Nothing agentic runs until data exists; the split is what keeps evaluation defensible.
4. **Resolve time-period drift** — UX-DESIGN Screen 1 says window closes "31 March 2026"; briefing/CLI use "2025-Q4" (31 Oct–31 Dec 2025). Pick one timeline across all docs.
5. **Resolve UX grade slip** — Screen 2 shows the walkthrough user at grade C2; Screen 4 narrative says "your current grade is B2". Pick one for the example.

## Context
- Plans + pipeline (Obsidian): `C:/Users/kenho/Obsidian/Second Brain/Projects/Kaggle-Capstone/project-pipeline.html`
- Docs (Obsidian): PRD.md (v1.1), DESIGN.md, UX-DESIGN.md, SAFETY.md, EVALUATION.md, COUNCIL-REVIEW.md
- Ideas log (Obsidian): IDEAS.md
- Code repo (this file's root): `C:/Users/kenho/Projects/Kaggle-Capstone/`
- Stack: Google ADK + Gemini (Vertex AI), 3 MCP servers (in-process), 2 agents, Cloud Run, mock data
- Submission deadline: 6 July 2026

## Blocker
None. Open actions 1–2 should be settled before implementation but do not block Stage 5 (FR.md).

## Last session
2026-06-22 — Completed PRD (Stage 4). Ran LLM Council review (PRD focus): folded four fixes into PRD v1.1 (held-out scenario set, deterministic-validators + single-LLM architecture with rules-vs-LLM delta, named the Kaggle-vs-data-quality split, glossary). Added briefing value-recovered metric. Fixed UX email contradiction. Saved COUNCIL-REVIEW.md.
