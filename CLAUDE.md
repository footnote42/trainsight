# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Kaggle Capstone — a competition/learning project built with Antigravity design methodology and Claude Code assistance. Project planning lives in Obsidian at `C:\Users\kenho\Obsidian\Second Brain\Projects\Kaggle-Capstone\`.

## Environment

- Windows 11, bash shell (Unix syntax — forward slashes in paths)
- Python environment managed via `venv` or `conda` (confirm once established)
- Jupyter notebooks for exploration; `.py` scripts for production pipeline steps

## Commands

> Update these once the project stack is confirmed.

```bash
# activate env (venv)
source .venv/Scripts/activate

# install deps
pip install -r requirements.txt

# run a notebook (headless)
jupyter nbconvert --to notebook --execute notebooks/<name>.ipynb

# run a specific script
python src/<module>.py

# lint
ruff check .

# format
ruff format .
```

## Architecture

Structure follows a standard ML project layout:

- `notebooks/` — exploratory analysis, EDA, prototyping
- `src/` — cleaned-up pipeline code imported by notebooks and scripts
- `data/` — raw and processed data (gitignored except samples)
- `models/` — serialized model artifacts (gitignored)
- `submissions/` — Kaggle submission CSVs
- `docs/` — planning docs, logs, design notes

Data flows: `data/raw/` → preprocessing in `src/` → `data/processed/` → model training → `models/` → inference → `submissions/`.

## Key Files

- `NOW.md` — current sprint focus and immediate next steps
- `.env` — API keys and paths (never committed)
- `requirements.txt` — pinned deps (add `requirements-dev.txt` for tooling if needed)
