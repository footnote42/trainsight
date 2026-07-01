# NOW — trainsight

## Status
IN PROGRESS — demo video (10.5). README/writeup/comments (10.1-10.3) done. Live app had a real bug, now fixed.

## Next
Record the actual narrated 5-min video yourself (mic, screen recorder, YouTube upload — outside what I can execute). Reference material below has exact login emails, baskets, and expected challenges per scenario so you don't have to reconstruct them. Then fill [YOUTUBE_URL] in README.md and writeup.md.

## Context
- Obsidian: `C:/Users/kenho/Obsidian/Second Brain/Projects/Kaggle-Capstone/`
- Build plan: `C:/Users/kenho/.claude/plans/confirm-progress-of-the-purring-pillow.md`
- Submission tracker: `C:/Users/kenho/Obsidian/Second Brain/Projects/Kaggle-Capstone/submission-stage.html`
- Live URL: https://trainsight-web-498756534840.us-central1.run.app
- Eval results: `eval/results/full_001.md`, `eval/results/rules_001.md`
- Writeup: `writeup.md` (1,500 / 2,500 words, [YOUTUBE_URL] placeholder pending)
- Video script (5-min beat sheet): `submission-stage.html` stage 10.5
- Reference GIF from browser walkthrough: `scenario4-role-eligibility-challenge.gif` (Downloads)
- Deadline: 6 July 2026

## Scenario reference (for demo video — login emails, baskets, expected results)

All logins use the "WORK EMAIL ADDRESS" field on the portal homepage. Data is mock, safe to show on screen. Only use Scenarios 1-5 below — H1/H2/H3 are held-out and shouldn't appear in the video (not a secrecy issue, just no reason to show them).

**Scenario 1 — clean individual, no challenges expected**
Login: `wd.000001@company.example.com` (Systems Engineer, self-submit mode)
Add: MEWP-001 (MEWP Operator Refresher, Maintaining Capability, Medium), HSAW-001 (Health & Safety Awareness, Resilience, Low), FAID-001 (First Aid at Work, Resilience, Medium)
Expected: no challenges fire — good "here's what a clean submission looks like" contrast shot before showing a flagged one.

**Scenario 2 — inflated LM submission, heaviest challenge scenario (use for 1:30-2:30 LM demo beat)**
Login: `wd.000014@company.example.com` (Facilities Manager, LM mode — team WD-002002..WD-002011, emails wd.000015 through wd.000024@company.example.com)
Add 14+ items marked High priority (basket is 18 items total in the seeded scenario — for video purposes, adding 10-12 High-priority items is enough to cross the 60% threshold and get the same challenge without replaying the full basket) including MBAF-001 (MBA Foundation) and PRES-001 (Presentation Skills) both with reason Critical/Scarce Skill — these are PD-category courses, so this is what fires reason-coherence.
Expected: priority inflation challenge (>60% High) + reason coherence challenge on MBAF-001/PRES-001 + quantity challenge (18 courses / 11 team members > 1.5 ratio).

**Scenario 3 — duplicate detection**
Login: `wd.000033@company.example.com` (Plant Operator, self-submit)
Add: MEWP-001 — this course was already submitted for this person by their line manager in a prior LM submission (pre-seeded in the mock submissions store).
Expected: duplicate challenge fires immediately on add.

**Scenario 4 — role/grade mismatch (used in the browser walkthrough already captured)**
Login: `wd.000047@company.example.com` (Business Support Officer, A2, Corporate Services, self-submit)
Add: PMFN-001 (Project Management Fundamentals) with reason Critical/Scarce Skill, priority High.
Expected: role fit challenge (grade A2 vs required C1, SME contact surfaced), priority inflation (single item, 100% High), reason coherence (LLM asks to justify Critical/Scarce Skill on a PD-category course). All three fired live when tested this session — see `scenario4-role-eligibility-challenge.gif`.

**Scenario 5 — clean LM submission, no challenges expected**
Login: `wd.000065@company.example.com` (Senior Engineer, LM mode, team WD-005002..WD-005009)
Add: 9 role-eligible courses across the team, balanced priority mix (mostly Medium/Low, a couple High) — e.g. STMG-001, HSAW-001, ELEC-001, WRTK-001 with varied Medium/Low priorities.
Expected: no challenges — second "clean" contrast case, this time at LM/team scale.

**For the HITL confirmation screen beat (2:30-3:00):** any scenario with unresolved challenges works — Scenario 4 is smallest/fastest to get there. After challenges appear, look for a "Review & Submit" or confirm action; the review screen should show resolved/unresolved challenge counts before the final submit click writes to the audit log.

**Course selection ideas for varied results, if you want additional footage beyond the 5 seeded scenarios:**
- Any course with `min_grade` above the logged-in person's grade → role fit (grade) challenge
- Any course whose `target_roles` doesn't include the person's `lead_technical_role` or `job_family` → role fit (role) challenge
- Category = a PD-type category (Leadership, Management, etc. — check `data/catalogue.json`) + reason "Critical/Scarce Skill" → reason coherence challenge, LLM-generated question each time (not deterministic wording, good for showing the LLM actually reasoning rather than templating)
- 4+ items in one basket, majority High → priority inflation on its own without other challenges, if reasons/roles are otherwise clean
- Submitting the same (person, course) pair twice in one basket, or a course already in a prior submission → duplicate

## Blocker
None currently — see Last session for a real bug found and fixed today.

## Last session
2026-07-01 — Ran Stage 9 eval (all thresholds pass). Stage 10.1-10.3 done: README.md rewrite, WHY-only comments on 6 rubric files, writeup.md drafted (1,500w). Started 10.5 video prep: found the live app was 500'ing on every /api/profile call since the 8.14 deploy — VertexAiSessionService.agent_engine_id was set to the full resource path instead of the bare numeric ID, and VERTEX_AI_LOCATION was overloaded across three unrelated concerns (Cloud Run region, agent Gemini-call region, Agent Runtime API location). Fixed with a new AGENT_RUNTIME_LOCATION env var, corrected the runtime IDs, patched deploy_agents.sh's extraction so it can't regress, redeployed, verified live. Then did a browser walkthrough of Scenario 4 (role/grade mismatch, all three challenge types fired), captured as a GIF — not a substitute for the real narrated video, just reference footage. Full scenario/login reference for finishing the recording is above.
