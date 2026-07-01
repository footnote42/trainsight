# trainsight Evaluation Summary Report
- **Run ID**: `2026-07-01T19:26:54.758119+00:00`
- **Evaluation Mode**: `rules_only`
- **Timestamp**: 2026-07-01 19:26:54 UTC

## Tuned Scenarios Results
| Scenario | Description | Correctness Score | Challenges Fired | Avg Judge Score | Status |
|---|---|---|---|---|---|
| 1 | Clean individual submission — Systems Engineer, 3 role-eligible courses, no challenges expected | 1 | 0 | N/A | PASS |
| 2 | Inflated LM submission — Facilities Manager, 18 items, 14 High priority, 2 unjustified Critical/Scarce Skill reasons, quantity threshold exceeded | 4 | 4 | N/A | PASS |
| 3 | Duplicate detection — Plant Operator requests MEWP-001 already submitted by their line manager in a prior LM submission | 1 | 1 | N/A | PASS |
| 4 | Role mismatch — Business Support Officer (A2, Corporate Services) requests grade-restricted and role-restricted courses; PMFN-001 also has unjustified Critical/Scarce Skill reason | 3 | 3 | N/A | PASS |
| 5 | Clean LM submission — Senior Engineer, 9 role-eligible courses across 9 team members, balanced priority mix, no challenges expected | 1 | 0 | N/A | PASS |

## Overall Tuned Summary Metrics
- **Total Correctness**: 10 / 10
- **Scenarios Passed**: 5
- **Scenarios Failed**: 0

# HELD-OUT SCENARIOS — DO NOT USE TO ADJUST PROMPTS

| Scenario | Description | Correctness Score | Challenges Fired | Avg Judge Score | Status |
|---|---|---|---|---|---|
| H1 | HELD-OUT — Clean individual — Data Analyst (Corporate Services, B2), 2 appropriate compliance/safety courses, no challenges expected. DO NOT use to tune agent prompts. | 1 | 0 | N/A | PASS |
| H2 | HELD-OUT — Priority inflation + reason mismatch LM — Team Manager (Corporate Services, C1), 9 items across 7-person team, 6 High priority, 2 unjustified Critical/Scarce Skill reasons. DO NOT use to tune agent prompts. | 3 | 3 | N/A | PASS |
| H3 | HELD-OUT — Role eligibility — Junior Engineer (Engineering Operations, B1) requests a leadership course restricted to Leadership/HR roles at C1+. DO NOT use to tune agent prompts. | 1 | 1 | N/A | PASS |

### Held-Out Summary Metrics
- **Total Correctness**: 5 / 5
- **Scenarios Passed**: 3
- **Scenarios Failed**: 0
