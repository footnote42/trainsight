"""Startup validation for trainsight environment variables."""

import os
import sys

def validate_environment():
    required_vars = [
        "CHALLENGER_AGENT_RUNTIME_ID",
        "BRIEFING_AGENT_RUNTIME_ID",
        "GOOGLE_CLOUD_PROJECT"
    ]
    missing = []
    for var in required_vars:
        if not os.environ.get(var):
            missing.append(var)
            
    if missing:
        error_msg = f"Startup failed: Missing required environment variables: {', '.join(missing)}"
        print(error_msg, file=sys.stderr)
        raise RuntimeError(error_msg)
        
    # Check optional VERTEX_AI_LOCATION and default to us-central1
    if not os.environ.get("VERTEX_AI_LOCATION"):
        os.environ["VERTEX_AI_LOCATION"] = "us-central1"

validate_environment()
