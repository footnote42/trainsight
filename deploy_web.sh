#!/bin/bash
# deploy_web.sh - Deploy trainsight web UI to Google Cloud Run.
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
  echo "Loading environment variables from .env..."
  while IFS= read -r line || [ -n "$line" ]; do
    # Skip comments and empty lines
    if [[ ! "$line" =~ ^# ]] && [[ "$line" =~ = ]]; then
      key=$(echo "$line" | cut -d'=' -f1 | tr -d ' ')
      val=$(echo "$line" | cut -d'=' -f2- | sed -e 's/^["'\'' ]*//' -e 's/["'\'' ]*$//')
      export "$key"="$val"
    fi
  done < .env
fi

# Validate project ID
PROJECT_ID="$GOOGLE_CLOUD_PROJECT"
if [ -z "$PROJECT_ID" ]; then
  PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
fi

if [ -z "$PROJECT_ID" ]; then
  echo "Error: Could not resolve Google Cloud Project ID. Set GOOGLE_CLOUD_PROJECT in .env"
  exit 1
fi

# Validate Agent IDs
if [ -z "$CHALLENGER_AGENT_RUNTIME_ID" ]; then
  echo "Error: CHALLENGER_AGENT_RUNTIME_ID is not set in .env."
  exit 1
fi

if [ -z "$BRIEFING_AGENT_RUNTIME_ID" ]; then
  echo "Error: BRIEFING_AGENT_RUNTIME_ID is not set in .env."
  exit 1
fi

# Setup defaults for optional variables
VERTEX_AI_LOCATION="${VERTEX_AI_LOCATION:-us-central1}"
VERTEX_AI_MODEL="${VERTEX_AI_MODEL:-gemini-2.5-flash-lite}"
GOOGLE_GENAI_USE_VERTEXAI="${GOOGLE_GENAI_USE_VERTEXAI:-true}"

# Ensure session secret is set, otherwise generate one
if [ -z "$SESSION_SECRET_KEY" ]; then
  echo "SESSION_SECRET_KEY is empty. Generating a cryptographically secure key..."
  SESSION_SECRET_KEY=$(openssl rand -hex 32 2>/dev/null || python -c "import secrets; print(secrets.token_hex(32))")
  
  if [ -f .env ]; then
    if grep -q "^SESSION_SECRET_KEY=" .env; then
      python -c "
with open('.env', 'r') as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if line.startswith('SESSION_SECRET_KEY='):
        lines[i] = f'SESSION_SECRET_KEY=$SESSION_SECRET_KEY\n'
with open('.env', 'w') as f:
    f.writelines(lines)
"
    else
      echo -e "\nSESSION_SECRET_KEY=$SESSION_SECRET_KEY" >> .env
    fi
    echo "Saved generated SESSION_SECRET_KEY to .env"
  else
    echo "Warning: .env file not found. Key generated but not saved locally."
  fi
fi

# Prepare environment variables block for Cloud Run
ENV_VARS="GOOGLE_CLOUD_PROJECT=${PROJECT_ID}"
ENV_VARS="${ENV_VARS},CHALLENGER_AGENT_RUNTIME_ID=${CHALLENGER_AGENT_RUNTIME_ID}"
ENV_VARS="${ENV_VARS},BRIEFING_AGENT_RUNTIME_ID=${BRIEFING_AGENT_RUNTIME_ID}"
ENV_VARS="${ENV_VARS},VERTEX_AI_LOCATION=${VERTEX_AI_LOCATION}"
ENV_VARS="${ENV_VARS},VERTEX_AI_MODEL=${VERTEX_AI_MODEL}"
ENV_VARS="${ENV_VARS},SESSION_SECRET_KEY=${SESSION_SECRET_KEY}"
ENV_VARS="${ENV_VARS},GOOGLE_GENAI_USE_VERTEXAI=${GOOGLE_GENAI_USE_VERTEXAI}"

echo "=== Deploying trainsight-web to Cloud Run ==="
echo "Targeting GCP Project: $PROJECT_ID"
echo "Location/Region: $VERTEX_AI_LOCATION"
echo "Challenger Runtime ID: $CHALLENGER_AGENT_RUNTIME_ID"
echo "Briefing Runtime ID: $BRIEFING_AGENT_RUNTIME_ID"
echo "Model: $VERTEX_AI_MODEL"
echo "Google GenAI VertexAI mode: $GOOGLE_GENAI_USE_VERTEXAI"

gcloud run deploy trainsight-web \
  --source . \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 1 \
  --max-instances 2 \
  --timeout 300 \
  --allow-unauthenticated \
  --set-env-vars "$ENV_VARS" \
  --project="$PROJECT_ID" \
  --region="$VERTEX_AI_LOCATION"

echo "SUCCESS: trainsight-web deployed to Cloud Run."
