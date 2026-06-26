"""Manager Briefing Agent.

Post-deadline batch run: aggregates submissions, calculates budget, flags
anomalies, and produces a structured report for the training manager.
"""

import sys
from pathlib import Path

# 4 parents up: app/briefing/app/agent.py -> app/briefing/app -> app/briefing -> app -> project root
sys.path.append(str(Path(__file__).parent.parent.parent.parent.resolve()))

from config.model_config import BRIEFING_GEN_CONFIG, VERTEX_AI_MODEL
from google.adk.agents import Agent
from google.adk.apps import App
from src.skills.briefing import (
    aggregate_submissions,
    calculate_budget_estimate,
    flag_anomalies,
    generate_report,
)

SYSTEM_PROMPT = """SECTION 1 — ROLE DEFINITION
You are the Manager Briefing Agent. You aggregate training submission data for
a specified period and produce a structured report for the training manager to
use in their pre-triage-meeting review. You do not make decisions about
submissions. You present data and surface patterns.

SECTION 2 — READ-ONLY CONSTRAINT
You have read access to the submissions store and training catalogue. You do
not write to any data store during your run. You do not send communications.
You do not approve, reject, or modify any submission record.

SECTION 3 — REPORT FORMAT INSTRUCTION
Your output is a single markdown document with exactly these sections in order:
## Summary, ## Course Demand, ## Anomalies, ## Budget by Department,
## Recommended Next Steps, ## Audit Trail.
Do not add sections or omit sections. The Recommended Next Steps section
contains at most five bullet points."""

root_agent = Agent(
    name="manager_briefing",
    model=VERTEX_AI_MODEL,
    instruction=SYSTEM_PROMPT,
    generate_content_config=BRIEFING_GEN_CONFIG,
    tools=[
        aggregate_submissions,
        calculate_budget_estimate,
        flag_anomalies,
        generate_report,
    ],
)

agent = root_agent
app = App(root_agent=root_agent, name="app")


if __name__ == "__main__":
    print("Testing app/briefing/app/agent.py...")
    print(f"Agent name: {root_agent.name}")
    print(f"Model: {root_agent.model}")
    print(f"Number of tools: {len(root_agent.tools)}")
    print("Agent initialization checks passed!")
