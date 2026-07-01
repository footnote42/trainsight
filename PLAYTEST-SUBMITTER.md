# Playtest script — Staff / Line Manager submitter

For anyone testing the Submission Challenger web app. Mock data throughout — no real people, safe to screen-record.

**Live URL:** https://trainsight-web-498756534840.us-central1.run.app

## How to log in

1. Open the live URL.
2. Enter the work email for the scenario you're running (see below) in "WORK EMAIL ADDRESS".
3. Click "Verify Identity & Continue" — you'll see your name/grade/department confirmed, then "Proceed to Catalogue".

If verification fails, it's a real backend error (check `gcloud logging read` against `trainsight-web`), not a typo — these emails are correct as of 2026-07-01.

## Scenarios to run

Run these in order for a full pass. Each entry: who to log in as, what to add to the basket, and what you should see happen.

### 1. Clean individual — no challenges expected
**Login:** `wd.000001@company.example.com` (Systems Engineer, self-submit)
**Add:** MEWP-001 (Maintaining Capability, Medium), HSAW-001 (Resilience, Low), FAID-001 (Resilience, Medium)
**Expect:** Training Advisor panel stays quiet — no challenges. This is the baseline "everything's fine" case.

### 2. Inflated line-manager submission — heaviest challenge case
**Login:** `wd.000014@company.example.com` (Facilities Manager, LM mode)
**Add:** 10+ courses, most marked **High** priority. Include at least two courses from a Professional-Development-type category (e.g. MBAF-001 "MBA Foundation", PRES-001 "Presentation Skills") with reason **Critical/Scarce Skill**.
**Expect:** three challenges fire —
- Priority inflation (once High-priority items exceed 60% of the basket)
- Reason coherence (LLM asks you to justify Critical/Scarce Skill on a PD-category course — wording is LLM-generated, changes each run)
- Quantity (once course count / team size ratio hits 1.5)

### 3. Duplicate detection
**Login:** `wd.000033@company.example.com` (Plant Operator, self-submit)
**Add:** MEWP-001
**Expect:** duplicate challenge fires immediately — this course was already submitted for this person by their line manager in a prior submission.

### 4. Role/grade mismatch
**Login:** `wd.000047@company.example.com` (Business Support Officer, A2, Corporate Services, self-submit)
**Add:** PMFN-001 (Project Management Fundamentals), reason **Critical/Scarce Skill**, priority **High**
**Expect:** all three challenge types at once — role fit (grade A2 vs required C1, SME contact shown), priority inflation (single item, 100% High), reason coherence (LLM question). Fastest scenario to reach the confirmation screen (below).

### 5. Clean line-manager submission — no challenges expected
**Login:** `wd.000065@company.example.com` (Senior Engineer, LM mode)
**Add:** 6–9 role-eligible courses across the team, balanced Medium/Low priority (a couple High is fine, stay under 60%)
**Expect:** no challenges — second baseline case, this time at team scale.

## Confirmation screen (HITL gate)

After any basket has items, use "Review & Submit". You should see:
- Resolved vs unresolved challenge counts
- The exact data boundary statement (three sources: catalogue, Workday profile, submissions store — nothing else)
- A confirm action that actually writes the submission

Nothing is written to the submissions store until this final confirm click — that's the human-in-the-loop gate. If you want to test what happens when it's declined, just navigate away instead of confirming; check `data/audit.log` afterward for a `submit_confirm_clicked` entry with no matching `submit_request_write` entry.

## Ideas for your own test baskets

Beyond the 5 above, any combination like this will reliably trigger something:
- A course with `min_grade` above your logged-in person's grade → role fit (grade)
- A course whose `target_roles` doesn't include your `lead_technical_role` or `job_family` → role fit (role)
- A PD-type category course (see `data/catalogue.json` for categories) + reason "Critical/Scarce Skill" → reason coherence, LLM-worded each time
- 4+ items, majority High priority, otherwise clean → priority inflation in isolation
- The same (person, course) pair added twice, or a course already in a prior submission → duplicate

## Known quirks

- None currently — the live app was fixed for a session/agent-runtime bug on 2026-07-01 (see `NOW.md`/git log if curious). All 5 scenarios above were verified working after the fix.
