#!/bin/bash
# deploy_agents.sh - Deploy trainsight agents and update environment file.
set -e

# Detect WSL and share Windows gcloud config if available
if grep -q -i "microsoft" /proc/version 2>/dev/null; then
  if [ -d "/mnt/c/Workspace/gcloud" ] || [ -d "/mnt/c/Workspace/gcloud" ]; then
    echo "WSL detected. Exporting CLOUDSDK_CONFIG to share Windows credentials..."
    export CLOUDSDK_CONFIG="/mnt/c/Users/kenho/AppData/Roaming/gcloud"
  fi
fi

# Share Windows gcloud credentials for Git Bash if needed
if [ -d "$USERPROFILE/AppData/Roaming/gcloud" ]; then
  export CLOUDSDK_CONFIG="$(cygpath -u "$USERPROFILE/AppData/Roaming/gcloud" 2>/dev/null || echo "$USERPROFILE/AppData/Roaming/gcloud")"
fi

# Retrieve configuration from .env
if [ -f .env ]; then
  export $(grep -E "^(GOOGLE_CLOUD_PROJECT|VERTEX_AI_LOCATION|VERTEX_AI_MODEL)=" .env | xargs)
fi

PROJECT_ID="$GOOGLE_CLOUD_PROJECT"
if [ -z "$PROJECT_ID" ]; then
  PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
fi

if [ -z "$PROJECT_ID" ]; then
  echo "Error: Could not resolve Google Cloud Project ID. Set GOOGLE_CLOUD_PROJECT in .env"
  exit 1
fi

VERTEX_AI_LOCATION="${VERTEX_AI_LOCATION:-us-central1}"
VERTEX_AI_MODEL="${VERTEX_AI_MODEL:-gemini-2.5-flash-lite}"

echo "Targeting GCP Project: $PROJECT_ID"
echo "Configuring deployed agents to use Vertex AI model: $VERTEX_AI_MODEL in location: $VERTEX_AI_LOCATION"

# Get absolute path to the run_acli.py wrapper script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_ACLI="${SCRIPT_DIR}/run_acli.py"

echo "=== Step 1: Enable required GCP APIs if not already enabled ==="
echo "APIs already enabled in previous step. Skipping active check to prevent terminal hanging..."

echo "=== Step 2: Validate configs via dry-run ==="
echo "Validating Challenger configuration..."
(cd app/challenger && uv run python "$RUN_ACLI" deploy --project="$PROJECT_ID" --dry-run)

echo "Validating Briefing configuration..."
(cd app/briefing && uv run python "$RUN_ACLI" deploy --project="$PROJECT_ID" --dry-run)

echo "Dry-run configuration checks completed successfully."

echo "=== Step 2.5: Syncing shared directories (src, config, data) into agent folders ==="
python copy_shared.py

echo "=== Step 3: Deploy agents to Vertex AI Agent Runtime ==="
echo "Deploying Challenger Agent (this may take several minutes)..."
(cd app/challenger && uv run python "$RUN_ACLI" deploy --project="$PROJECT_ID" --no-confirm-project --update-env-vars "VERTEX_AI_LOCATION=${VERTEX_AI_LOCATION},VERTEX_AI_MODEL=${VERTEX_AI_MODEL}")

echo "Deploying Briefing Agent (this may take several minutes)..."
(cd app/briefing && uv run python "$RUN_ACLI" deploy --project="$PROJECT_ID" --no-confirm-project --update-env-vars "VERTEX_AI_LOCATION=${VERTEX_AI_LOCATION},VERTEX_AI_MODEL=${VERTEX_AI_MODEL}")

echo "=== Step 4: Extract runtime IDs and update .env ==="
# remote_agent_runtime_id is the full resource path (projects/.../locations/.../reasoningEngines/<id>).
# VertexAiSessionService.agent_engine_id must be the bare numeric ID - it uses the value
# verbatim to build "reasoningEngines/{id}" and does not parse a full path out of it.
CHALLENGER_ID=$(python -c "import json; print(json.load(open('app/challenger/deployment_metadata.json'))['remote_agent_runtime_id'].rsplit('/', 1)[-1])" 2>/dev/null)
BRIEFING_ID=$(python -c "import json; print(json.load(open('app/briefing/deployment_metadata.json'))['remote_agent_runtime_id'].rsplit('/', 1)[-1])" 2>/dev/null)

if [ -z "$CHALLENGER_ID" ] || [ "$CHALLENGER_ID" = "None" ]; then
  echo "Error: Challenger Agent Runtime ID is empty or 'None'."
  exit 1
fi

if [ -z "$BRIEFING_ID" ] || [ "$BRIEFING_ID" = "None" ]; then
  echo "Error: Briefing Agent Runtime ID is empty or 'None'."
  exit 1
fi

echo "Extracted Challenger ID: $CHALLENGER_ID"
echo "Extracted Briefing ID: $BRIEFING_ID"

echo "Updating root .env file..."
python -c "
import sys, os
env_path = '.env'
if not os.path.exists(env_path):
    print('Error: .env file does not exist in root.')
    sys.exit(1)

with open(env_path, 'r') as f:
    lines = f.readlines()

challenger_id = sys.argv[1]
briefing_id = sys.argv[2]

updated_challenger = False
updated_briefing = False

for i, line in enumerate(lines):
    if line.startswith('CHALLENGER_AGENT_RUNTIME_ID='):
        lines[i] = f'CHALLENGER_AGENT_RUNTIME_ID={challenger_id}\n'
        updated_challenger = True
    elif line.startswith('BRIEFING_AGENT_RUNTIME_ID='):
        lines[i] = f'BRIEFING_AGENT_RUNTIME_ID={briefing_id}\n'
        updated_briefing = True

if not updated_challenger:
    lines.append(f'CHALLENGER_AGENT_RUNTIME_ID={challenger_id}\n')
if not updated_briefing:
    lines.append(f'BRIEFING_AGENT_RUNTIME_ID={briefing_id}\n')

with open(env_path, 'w') as f:
    f.writelines(lines)
" "$CHALLENGER_ID" "$BRIEFING_ID"

echo "SUCCESS: Deployment completed and root .env updated."
