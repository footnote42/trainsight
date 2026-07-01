# Playtest script — Training Manager (Manager Briefing CLI)

This tests the Manager Briefing agent, which runs locally via `adk run` — it is a standalone CLI tool, not part of the web app. Unlike the Submission Challenger, there's no login: the training manager just runs a command from the terminal after the submission window closes.

## Prerequisites

```bash
cd C:/Users/kenho/Projects/Kaggle-Capstone
source .venv/Scripts/activate
```

`.env` must have `GOOGLE_CLOUD_PROJECT` and `GOOGLE_GENAI_USE_VERTEXAI=true` set (already the case in this repo's `.env`).

## The command

```bash
adk run app/briefing "Generate a briefing report for period 2026-Q2"
```

- `app/briefing` is the agent folder path — this is what actually loads the Manager Briefing agent. (README/writeup earlier drafts had this wrong as `adk run manager-briefing --period ... --output ...` — that flag interface doesn't exist on `adk run`; fixed 2026-07-01.)
- The quoted string is a natural-language query, not a flag. You can phrase it differently ("What does the Q2 briefing look like?", "Summarise submissions for 2026-Q2") — the agent extracts the period itself.
- To save the report to a file instead of just printing it: redirect stdout —
  ```bash
  adk run app/briefing "Generate a briefing report for period 2026-Q2" > briefing-2026-Q2.md
  ```

## What to expect

The agent calls four tools in sequence (aggregate_submissions → calculate_budget_estimate + flag_anomalies → generate_report) and its final response should be the full markdown report, not a summary of it. Sections in order:

```
## Summary
## Course Demand
## Anomalies
## Budget by Department
## Recommended Next Steps
## Audit Trail
```

The headline number to check is in the Summary table: **"Questionable spend | £X of £Y surfaced for review"** — this is the value-recovered figure for the writeup/video (estimated cost attached to flagged, duplicated, or inflated requests).

If you've run through PLAYTEST-SUBMITTER.md's scenarios first (especially #2 and #4, which leave unresolved challenges if you don't override them), the Anomalies section should show non-empty Priority Inflation / Eligibility Flags / Reason Coherence entries and a non-zero questionable-spend figure. If you ran nothing first, or everything was clean/overridden, expect a mostly-empty report ("No anomalies detected") — that's correct behavior, not a bug.

## Known quirks

- **Occasional malformed function call**: gemini-2.5-flash-lite's experimental structured function-calling occasionally emits a malformed call and the run errors out with `MALFORMED_FUNCTION_CALL`. This is model flakiness, not a code bug — just retry the same command.
- **£ symbol may render as `�` in Windows terminals**: cosmetic encoding display issue in some terminal configs, not a data problem — the underlying report text is correct UTF-8. If it bothers you on camera, try `chcp 65001` first or use Windows Terminal instead of the default console host.
- **Verbose output**: `adk run` prints ADK's own experimental-feature warnings and a session ID before the report — trim those in post if recording, or pipe through `grep -v "UserWarning\|credential_service\|build_function_declaration"` to strip them live.

## If it crashes instead of quirking

A real crash (not the malformed-function-call retry case) most likely means the fix from 2026-07-01 didn't make it into the packaged agent copy. Run this first and retry:

```bash
python copy_shared.py
```

This re-syncs `src/`, `config/`, `data/` into `app/briefing/src/` and `app/briefing/app/src/` — `adk run` loads the packaged copy, not the repo root directly, so any root-level fix needs this sync step before it takes effect locally.
