"""Model configuration for trainsight agents."""

import os
from google.genai import types

# Model name is loaded from the environment, defaulting to gemini-2.5-flash-lite
VERTEX_AI_MODEL = os.environ.get("VERTEX_AI_MODEL", "gemini-2.5-flash-lite")

# LLM generation parameters
CHALLENGER_GEN_CONFIG = types.GenerateContentConfig(
    temperature=0.2,
)

BRIEFING_GEN_CONFIG = types.GenerateContentConfig(
    temperature=0.1,
)

# LLM judge (evaluation harness) — temperature=0.0 for deterministic scoring
JUDGE_CONFIG = types.GenerateContentConfig(
    temperature=0.0,
    max_output_tokens=512,
)

# Custom RegionalGemini model to handle regional endpoint overrides inside Reasoning Engines
try:
    from functools import cached_property
    from google.adk.models import Gemini
    from google.genai import Client

    class RegionalGemini(Gemini):
        @cached_property
        def api_client(self) -> Client:
            base_url, api_version = self._base_url_and_api_version
            kwargs_for_http_options = {
                'headers': self._tracking_headers(),
                'retry_options': self.retry_options,
                'base_url': base_url,
            }
            if api_version:
                kwargs_for_http_options['api_version'] = api_version

            location = os.environ.get("VERTEX_AI_LOCATION", "us-central1")
            kwargs = {
                'http_options': types.HttpOptions(**kwargs_for_http_options),
                'location': location,
            }
            if self.model.startswith('projects/'):
                kwargs['enterprise'] = True

            return Client(**kwargs)
except ImportError:
    # Fallback if google-adk is not installed in the importing environment
    class RegionalGemini:
        def __init__(self, model):
            self.model = model
