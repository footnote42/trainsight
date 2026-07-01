#!/bin/bash
# verify_deployment.sh - Verify Reasoning Engine and Agent Registry status, and test agent endpoints.
set -e

# Detect WSL and share Windows gcloud config if available
if grep -q -i "microsoft" /proc/version 2>/dev/null; then
  if [ -d "/mnt/c/Users/kenho/AppData/Roaming/gcloud" ]; then
    echo "WSL detected. Exporting CLOUDSDK_CONFIG to share Windows credentials..."
    export CLOUDSDK_CONFIG="/mnt/c/Users/kenho/AppData/Roaming/gcloud"
  fi
fi

# Load runtime environment variables
if [ -f .env ]; then
  # Read variables from .env
  export $(grep -E "^(GOOGLE_CLOUD_PROJECT|CHALLENGER_AGENT_RUNTIME_ID|BRIEFING_AGENT_RUNTIME_ID)=" .env | xargs)
else
  echo "Error: .env file not found in root."
  exit 1
fi

if [ -z "$CHALLENGER_AGENT_RUNTIME_ID" ] || [ -z "$BRIEFING_AGENT_RUNTIME_ID" ]; then
  echo "Error: CHALLENGER_AGENT_RUNTIME_ID or BRIEFING_AGENT_RUNTIME_ID is empty in .env."
  exit 1
fi

# Retrieve GCP Project ID
PROJECT_ID="$GOOGLE_CLOUD_PROJECT"
if [ -z "$PROJECT_ID" ]; then
  PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
fi

if [ -z "$PROJECT_ID" ]; then
  echo "Error: Could not resolve Google Cloud Project ID."
  exit 1
fi

# Parse region from Challenger Agent ID
REGION=$(python -c "import sys; parts = '$CHALLENGER_AGENT_RUNTIME_ID'.split('/'); print(parts[parts.index('locations')+1])" 2>/dev/null)
if [ -z "$REGION" ]; then
  REGION="us-east1"
fi

echo "=== Verification Context ==="
echo "Project: $PROJECT_ID"
echo "Challenger Region: $REGION"
echo "Challenger ID: $CHALLENGER_AGENT_RUNTIME_ID"
echo "Briefing ID: $BRIEFING_AGENT_RUNTIME_ID"
echo ""

# Get absolute path to the run_acli.py wrapper script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_ACLI="${SCRIPT_DIR}/run_acli.py"

echo "=== Step 1: Listing Reasoning Engines ==="
echo "Running agents-cli deploy --list for Challenger..."
(cd app/challenger && uv run python "$RUN_ACLI" deploy --list)

echo ""
echo "=== Step 2: Querying Agent Registry REST API ==="
python -c "
import socket; orig = socket.getaddrinfo; socket.getaddrinfo = lambda h, p, f=0, t=0, pr=0, fl=0: orig(h, p, socket.AF_INET, t, pr, fl)
import urllib.request, json, subprocess, os, sys

project_id = '$PROJECT_ID'
regions = ['$REGION', 'us-central1']

try:
    token = subprocess.check_output('gcloud auth print-access-token', shell=True).decode().strip()
except Exception as e:
    print(f'Error getting access token: {e}')
    sys.exit(1)

found_challenger = False
found_briefing = False

for r in regions:
    url = f'https://agentregistry.googleapis.com/v1/projects/{project_id}/locations/{r}/agents'
    print(f'Querying location: {r}...')
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            data = json.loads(res.read().decode())
            agents = data.get('agents', [])
            for agent in agents:
                display_name = agent.get('displayName')
                name = agent.get('name')
                print(f'  -> Found Registered Agent: \"{display_name}\"')
                print(f'     Resource Name: {name}')
                if display_name == 'challenger':
                    found_challenger = True
                elif display_name == 'briefing':
                    found_briefing = True
    except Exception as e:
        print(f'  Note: Location {r} query skipped/unreachable: {e}')

print('')
if found_challenger and found_briefing:
    print('SUCCESS: Both challenger and briefing agents are registered in Agent Registry!')
else:
    print('WARNING: Could not confirm registration of both agents in the Agent Registry REST output.')
"

echo ""
echo "=== Step 3: Challenger Agent Smoke Test ==="
CHALLENGER_URL="https://${REGION}-aiplatform.googleapis.com/v1/${CHALLENGER_AGENT_RUNTIME_ID}"
echo "Sending off-topic message to Challenger at $CHALLENGER_URL..."
(cd app/challenger && uv run python "$RUN_ACLI" run "Test message" --url "$CHALLENGER_URL" --mode adk)

echo ""
echo "=== Step 4: Briefing Agent Smoke Test ==="
# Parse region for Briefing Agent ID
BRIEFING_REGION=$(python -c "import sys; parts = '$BRIEFING_AGENT_RUNTIME_ID'.split('/'); print(parts[parts.index('locations')+1])" 2>/dev/null)
if [ -z "$BRIEFING_REGION" ]; then
  BRIEFING_REGION="us-east1"
fi
BRIEFING_URL="https://${BRIEFING_REGION}-aiplatform.googleapis.com/v1/${BRIEFING_AGENT_RUNTIME_ID}"
echo "Sending structured query to Briefing at $BRIEFING_URL..."
(cd app/briefing && uv run python "$RUN_ACLI" run "Generate a briefing report for period: 2026-Q2" --url "$BRIEFING_URL" --mode adk)

echo ""
echo "=== Verification Completed ==="
