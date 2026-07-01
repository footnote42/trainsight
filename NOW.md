# NOW — trainsight

## Status
Step 8.13 DONE. Step 8.14 config generated (Dockerfile.web, .dockerignore, deploy_web.sh, cloud_run_reference.yaml) — actual Cloud Run deploy not yet run.

## Next
1. Run `./deploy_web.sh` to deploy `trainsight-web` to Cloud Run.
2. Note the Cloud Run URL from output; `curl <url>/api/health` should return `{"status":"ok",...}`.
3. Run `python eval/harness.py --scenario all --output eval/results/smoke.json` for a full local confirmation once web layer is up.

## Context
- Obsidian: `C:/Users/kenho/Obsidian/Second Brain/Projects/Kaggle-Capstone/`
- Build plan: `C:/Users/kenho/.claude/plans/confirm-progress-of-the-purring-pillow.md`
- Submission tracker: `C:/Users/kenho/Obsidian/Second Brain/Projects/Kaggle-Capstone/submission-stage.html`
- Deadline: 6 July 2026

## Root cause (resolved 2026-07-01)
Direct REST calls to `https://us-central1-aiplatform.googleapis.com/.../publishers/google/models/{MODEL}:generateContent`
using live `gcloud auth print-access-token` credentials for `kaggle-day-five` showed:
- `gemini-3.1-flash-lite`, `gemini-3.1-pro`, `gemini-3.1-flash`, `gemini-3-pro`, `gemini-3-flash`, `gemini-3-pro-preview`, `gemini-1.5-pro`, `gemini-2.0-flash-001` → all 404.
- `gemini-2.5-flash`, `gemini-2.5-flash-lite` → both 200.

Gemini publisher-model access was already enabled in this project (ToS accepted) — the 3.x model name simply
doesn't exist here. Do not re-chase Model Garden "Enable" steps for gemini-3.x; switched to `gemini-2.5-flash-lite`
in `config/model_config.py`, `.env`, `.env.example`, `deploy_agents.sh`.

## Last session
2026-07-01 (cont.) — Antigravity generated Step 8.14 deployment config: Dockerfile.web, .dockerignore, deploy_web.sh,
cloud_run_reference.yaml. Plan review caught two real gaps before generation (both fixed in the plan): SessionMiddleware
falls back to a hardcoded secret key if SESSION_SECRET_KEY is unset (src/web/app.py:80); the in-process reason-coherence
Gemini call (src/web/app.py:278) needs GOOGLE_GENAI_USE_VERTEXAI=true or it silently falls back to canned challenge text.
Post-generation review found a real bug in the generated deploy_web.sh: line 74 used Python-style `else:` instead of
bash `else` — bash -n doesn't flag it (not a parse error, just an unrecognized command), but at runtime it silently
skipped persisting the generated SESSION_SECRET_KEY to .env, so every deploy would've regenerated a new key and
invalidated all sessions. Fixed directly (`else:` → `else`), repro-verified the fix. Not yet deployed — `./deploy_web.sh`
still pending.

2026-07-01 — Diagnosed the recurring gemini-3.1-flash-lite 404 as a nonexistent model name (confirmed via direct
Vertex REST calls), not a ToS blocker. Switched default model to `gemini-2.5-flash-lite` across config/model_config.py,
.env, .env.example, deploy_agents.sh. Ran `./deploy_agents.sh` — both agents redeployed in place (same runtime IDs:
Challenger `reasoningEngines/1448857258246012928`, Briefing `reasoningEngines/4730855486692261888`). Antigravity ran
smoke tests: both agents returned live 200 responses on `gemini-2.5-flash-lite` (Challenger: "I'm focused on reviewing
your current training submission..."; Briefing: "Four"). Step 8.13 complete.

2026-06-30 — Migrated model from gemini-1.5-pro (unavailable) to gemini-3.1-flash-lite (Kaggle codelab model);
updated deploy_agents.sh, config/model_config.py, .env, .env.example; both agents redeployed via Antigravity
with new runtime IDs (Challenger: reasoningEngines/1448857258246012928, Briefing: reasoningEngines/4730855486692261888);
smoke tests blocked on ToS acceptance (later disproven — see root cause above).
