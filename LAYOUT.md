#01 trainsight — Path Layout
2.*
TR.md paths are unchanged. This table maps TR.md references to actual scaffold locations.

| TR.md reference | Actual path |
|---|---|
| `src/agents/challenger.py` | `app/challenger/agent.py` |
| `src/agents/briefing.py` | `app/briefing/agent.py` |
| `src/mcp/catalogue_server.py` | `src/mcp/catalogue_server.py` |
| `src/mcp/workday_server.py` | `src/mcp/workday_server.py` |
| `src/mcp/submissions_server.py` | `src/mcp/submissions_server.py` |
| `src/web/app.py` | `src/web/app.py` |
| `eval/harness.py` | `eval/harness.py` |
| `config/model_config.py` | `config/model_config.py` |

## Why agents live under `app/`

`agents-cli scaffold` expects each agent in its own directory under `app/`. TR.md
uses `src/agents/` for conceptual clarity; agents-cli compatibility requires `app/`.
The divergence is intentional; TR.md is the authoritative spec and is unchanged.

## Deployment split

| Component | Path | Deploy target |
|---|---|---|
| Submission Challenger agent | `app/challenger/` | Vertex AI Agent Runtime |
| Manager Briefing agent | `app/briefing/` | Vertex AI Agent Runtime |
| FastAPI web UI + MCP servers | `src/web/app.py`, `static/` | Cloud Run (`trainsight-web`) |
| Evaluation harness | `eval/harness.py` | Local only |
