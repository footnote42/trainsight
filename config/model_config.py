"""Model configuration for trainsight agents."""

import os
from google.genai import types

# Model name is loaded from the environment, defaulting to gemini-1.5-pro
VERTEX_AI_MODEL = os.environ.get("VERTEX_AI_MODEL", "gemini-1.5-pro")

# LLM generation parameters
CHALLENGER_GEN_CONFIG = types.GenerateContentConfig(
    temperature=0.2,
)
