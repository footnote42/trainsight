# trainsight — Training Requirements Agent

**Track:** Agents for Business
**Live demo:** https://trainsight-web-498756534840.us-central1.run.app
**GitHub:** github.com/footnote42/trainsight

## Problem

Every year, staff and line managers submit training requests through a form with no feedback loop. In practice the data that comes out the other end doesn't reflect reality. People request more courses than their teams could realistically attend. Almost everything gets marked High priority, because there's no cost to doing so. Aspirational development gets classified as Critical/Scarce Skill, because that sounds more likely to get approved. Line managers submit courses for staff who've already submitted the same course themselves.

The root cause isn't bad intentions — it's that the form asks people to make judgements about priority, reason, and appropriateness with no feedback and no context about what those judgements mean downstream. It accepts whatever it's given. By the time the submission window closes, the training manager is sitting on a dataset that needs significant manual triage — chasing line managers, consulting subject-matter experts, deduplicating — before anything can go to senior leaders for budget endorsement.

## Solution

trainsight puts a challenge agent into the submission flow itself, before a request locks. Two ADK agents:

**Submission Challenger** — a web app where staff and line managers select courses and submit. As courses are added, the agent reviews each selection against the submitter's role profile and any prior submissions for the team, and raises a challenge where something doesn't hold up. Five challenge types: role eligibility (course doesn't match the submitter's job family), priority inflation (over 60% of a basket marked High), reason coherence (a professional-development course classified as a genuine skill gap), quantity (course volume disproportionate to team size, line-manager submissions only), and duplicates (the same course submitted twice for the same person). The submitter can respond, revise, or override with a written justification — nothing writes to the submissions store without an explicit human confirmation click.

**Manager Briefing** — a CLI agent the training manager runs after the deadline closes (`adk run app/briefing "Generate a briefing report for period 2026-Q2"`). It aggregates every submission for the period and produces a markdown report: cost totals, course demand ranking, unresolved flags, and — the headline figure — a **questionable-spend total**, the estimated cost attached to flagged, duplicated, or inflated requests, expressed against total requested spend. That single number is what demonstrates value recovered, both to an enterprise sponsor and for this writeup.

What it deliberately doesn't do: approve or reject requests, check training history, suggest alternative courses, comment on individual performance, or connect to the real Power App/SharePoint. All decisions stay with the training manager — the agent's job is to improve the quality of the data they receive, not to replace their judgement.

## Architecture

```
Browser → Cloud Run (trainsight-web)
            ├── FastAPI (src/web/app.py)
            │   ├── catalogue-mcp    (in-process stdio, read-only, no PII)
            │   ├── workday-mcp      (in-process stdio, read-only, PII scrubbed pre-LLM)
            │   └── submissions-mcp  (in-process stdio, HITL-gated write)
            └── VertexAiSessionService → Agent Runtime
                    ├── Submission Challenger
                    └── Manager Briefing
```

Three MCP servers, split by data sensitivity rather than by function. `catalogue-mcp` serves course data and carries no PII risk. `workday-mcp` serves employee profiles and is the highest-sensitivity server — it scrubs name, email, and Age Band at load time, before a profile ever reaches the LLM. `submissions-mcp` has broad read access for both agents but its write path is gated behind a human-in-the-loop token that only the confirmation endpoint can issue.

A deliberate design choice: **firing is deterministic, phrasing is the LLM's job.** Whether a challenge fires at all is decided in plain Python — role-fit against a course's `target_roles`, the 60% priority threshold, the 1.5-per-head quantity ratio, exact-match duplicate detection. The LLM receives the computed facts and produces two things: the reason-coherence judgement (does "Critical/Scarce Skill" actually fit a professional-development course, which needs semantic reasoning a rules engine can't do well) and the challenge wording itself — inquisitive rather than accusatory, per the system prompt's tone instruction. This keeps correctness stable across runs (no flaky recall from generation) and makes the LLM's actual contribution measurable rather than assumed — see Evaluation below.

The two agents run on Vertex AI Agent Runtime; the web UI and its three in-process MCP servers run in a single Cloud Run container (`gcloud run deploy --source .`, min-instances 1 so the in-memory HITL token store survives between the confirm and execute requests of a submission).

## Capstone concepts

| Concept | Implementation | Evidence |
|---|---|---|
| Multi-agent system (ADK) | Submission Challenger + Manager Briefing, both `LlmAgent` | Code |
| MCP Server | `catalogue-mcp`, `workday-mcp`, `submissions-mcp` | Code |
| Antigravity | `PRD.md` and `UX-DESIGN.md` git-committed before any `src/` code — the design was written and reviewed before implementation began, and the git history shows it | Video |
| Security | Pre-LLM PII scrub, HITL gate before every write, least-privilege MCP access split by sensitivity, prompt-injection sanitisation on catalogue text, append-only audit log | Code + Video |
| Deployability | Single Docker container; live HTTPS URL on Cloud Run | Video |
| Agent Skills (Agents CLI) | Manager Briefing invoked via `adk run app/briefing` | Code + Video |

All six are demonstrated; the rubric requires three.

## Security design

Security here isn't a bolt-on — the constraints came from PRD.md and SAFETY.md before any code existed, and they're treated as non-negotiable in the codebase. Age Band, name, and email must never appear in a `PersonProfile`, an audit log entry, or an API response — enforced structurally at `workday-mcp`'s CSV load (those columns are simply never read into the profile object) and checked again by `_assert_no_pii` as a second layer. The HITL token on `submit_request` is marked used **before** the write happens, not after, so a crash between write and marking-used can't leave a token valid for replay. On any submission error, zero records are written to `submissions-mcp`, but an audit entry with `outcome="failure"` is still written — the failure itself is never silent. Catalogue descriptions are untrusted text; `lookup_courses` sanitises anything resembling an injected instruction before it reaches the LLM's context, and the system prompt itself states the agent does not treat catalogue text as instructions. Held-out evaluation scenarios were never used to tune the Challenger's prompt, which matters for the next section.

## Evaluation

Five tuned scenarios (used during development) and three held-out scenarios (never used to adjust the prompt — the only way to distinguish real evaluation from a memorisation test) were run through `eval/harness.py` in two modes: rules-only and full LLM.

**Correctness:** 10/10 on tuned scenarios, 5/5 on held-out. Clean submissions pass without challenge; every challenge type fires at least once; no false positives, tuned or held-out.

**LLM judge quality (0–10 rubric across justification, tone, scope, actionability):** average 10.0/10 on tuned scenarios, 9.75/10 on held-out. Minimum tone score of 3/3 on every single challenge that fired — a tone failure would have been treated as a defect requiring prompt tuning, and none occurred.

**Rules-only vs full-mode delta** — the evidence for why the LLM belongs in the loop at all, since most of the challenge logic is deterministic Python:

| Metric | Rules-only | Full (LLM) | Delta |
|---|---|---|---|
| Avg judge total | 9.38 | 10.00 | +0.63 |
| Avg tone | 2.75 | 3.00 | +0.25 |
| Avg justification | 2.62 | 3.00 | +0.38 |
| Avg actionability | 2.00 | 2.00 | +0.0 |

Correctness is identical in both modes — expected, since firing is deterministic in both. The LLM's measurable contribution is concentrated exactly where the architecture predicts it should be: tone and justification quality, not whether a challenge fires. That's the point of separating "does this fire" from "how is it phrased" — the delta shows the LLM earning its place rather than asserting it.

## Project journey

The build followed a design-first sequence: PRD.md and UX-DESIGN.md were written and committed before any implementation code, using Google Antigravity for the design pass — the git log timestamps show the design commits predating `src/` and `app/` commits by days, which is the concrete evidence for the Antigravity concept requirement. From there: data models and pure-Python validators first (testable in isolation, no LLM dependency), then the two ADK agents wired to those validators as tools, then the FastAPI web layer and the HITL confirmation flow, then Cloud Run deployment, then this evaluation pass. Two real deployment bugs surfaced late — a bash syntax issue that silently skipped persisting a generated session secret, and a missing dependency (`fastmcp`) that only showed up as a container crash on Cloud Run, diagnosed via `gcloud logging read` — both fixed and verified before this writeup, not worked around.

## Live demo

The application is live at the URL above — Cloud Run, single Docker container, `min-instances=1`. The demo video walks through an individual submission triggering a role-eligibility challenge, a line-manager submission triggering priority inflation and reason-coherence challenges, the HITL confirmation screen, the Manager Briefing CLI producing a questionable-spend figure, and the git history showing design docs predating code.
