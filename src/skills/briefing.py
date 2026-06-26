"""Manager Briefing skills for trainsight agent."""

import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent.resolve()))

from src.models import (
    AggregatedData,
    AnomalyReport,
    AuditLogEntry,
    BudgetSummary,
    SubmissionRecord,
)
from src.security import write_audit_entry
from src.mcp.submissions_server import get_submissions


def aggregate_submissions(period: str) -> AggregatedData:
    """Aggregate all submissions for a period from the submissions store."""
    submissions: list[SubmissionRecord] = get_submissions(period=period)

    write_audit_entry(
        AuditLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type="briefing_mcp_read",
            agent_name="manager_briefing",
            detail=f"period={period}, count={len(submissions)}",
        )
    )

    seen_courses: dict[str, None] = {}
    for r in submissions:
        for item in r.items:
            seen_courses.setdefault(item.course_id, None)
    unique_course_ids = list(seen_courses)

    cost_by_dept: dict[str, float] = defaultdict(float)
    for r in submissions:
        cost_by_dept[r.department] += r.total_cost + r.total_ts

    return AggregatedData(
        period=period,
        submissions=submissions,
        total_count=len(submissions),
        unique_course_ids=unique_course_ids,
        total_cost=sum(r.total_cost for r in submissions),
        total_ts=sum(r.total_ts for r in submissions),
        unresolved_flag_count=sum(r.unresolved_flag_count for r in submissions),
        flagged_submission_ids=[
            r.submission_id for r in submissions if r.unresolved_flag_count > 0
        ],
        flagged_spend=sum(
            r.total_cost + r.total_ts
            for r in submissions
            if r.unresolved_flag_count > 0
        ),
        cost_by_department=dict(cost_by_dept),
    )


def calculate_budget_estimate(data: AggregatedData) -> BudgetSummary:
    """Compute budget summary from aggregated submission data. No MCP calls."""
    grand_total = data.total_cost + data.total_ts
    total_spend = grand_total

    per_submission_quality: dict[str, float] = {}
    for r in data.submissions:
        total_flags = r.resolved_flag_count + r.unresolved_flag_count
        quality = 1.0 if total_flags == 0 else r.resolved_flag_count / total_flags
        per_submission_quality[r.submission_id] = quality

    course_counts: dict[str, dict] = {}
    for r in data.submissions:
        for item in r.items:
            if item.course_id not in course_counts:
                course_counts[item.course_id] = {
                    "course_id": item.course_id,
                    "count": 0,
                    "flag_count": 0,
                }
            course_counts[item.course_id]["count"] += 1
            if item.challenge_types_fired:
                course_counts[item.course_id]["flag_count"] += 1
    course_demand = sorted(
        course_counts.values(), key=lambda d: d["count"], reverse=True
    )

    return BudgetSummary(
        total_cost=data.total_cost,
        total_ts=data.total_ts,
        grand_total=grand_total,
        cost_by_department=data.cost_by_department,
        questionable_spend=data.flagged_spend,
        total_spend=total_spend,
        questionable_spend_pct=data.flagged_spend / total_spend if total_spend else 0.0,
        per_submission_quality=per_submission_quality,
        course_demand=course_demand,
    )


def flag_anomalies(data: AggregatedData) -> AnomalyReport:
    """Identify anomalies in aggregated submission data. No MCP calls."""
    priority_inflation: list[dict] = []
    for r in data.submissions:
        if r.submitted_by != "lm" or not r.items:
            continue
        high_count = sum(1 for item in r.items if item.priority == "High")
        pct_high = high_count / len(r.items)
        if pct_high > 0.60:
            priority_inflation.append(
                {
                    "person_id": r.person_id,
                    "pct_high": round(pct_high, 2),
                    "total": len(r.items),
                }
            )

    eligibility_flags: list[dict] = []
    unresolved_duplicates: list[dict] = []
    reason_coherence: list[dict] = []

    for r in data.submissions:
        for item in r.items:
            if (
                "role_fit" in item.challenge_types_fired
                and not item.override_justification
            ):
                eligibility_flags.append(
                    {
                        "person_id": item.person_id,
                        "course_id": item.course_id,
                        "type": "role_fit",
                    }
                )
            if (
                "duplicate" in item.challenge_types_fired
                and not item.override_justification
            ):
                unresolved_duplicates.append(
                    {"person_id": item.person_id, "course_id": item.course_id}
                )
            if (
                "reason_coherence" in item.challenge_types_fired
                and not item.override_justification
            ):
                reason_coherence.append(
                    {"person_id": item.person_id, "course_id": item.course_id}
                )

    return AnomalyReport(
        priority_inflation=priority_inflation,
        eligibility_flags=eligibility_flags,
        unresolved_duplicates=unresolved_duplicates,
        reason_coherence=reason_coherence,
        anomaly_count=(
            len(priority_inflation)
            + len(eligibility_flags)
            + len(unresolved_duplicates)
            + len(reason_coherence)
        ),
    )


def _derive_next_steps(anomalies: AnomalyReport) -> list[str]:
    # ponytail: algorithmic; upgrade to agent-supplied list if LLM-generated steps needed
    steps = []
    if anomalies.priority_inflation:
        steps.append(
            f"Review priority classifications: {len(anomalies.priority_inflation)} LM submission(s) with >60% High-priority items."
        )
    if anomalies.eligibility_flags:
        steps.append(
            f"Check role eligibility: {len(anomalies.eligibility_flags)} flagged selection(s) without override justification."
        )
    if anomalies.unresolved_duplicates:
        steps.append(
            f"Resolve {len(anomalies.unresolved_duplicates)} duplicate(s) between individual and LM requests."
        )
    if anomalies.reason_coherence:
        steps.append(
            f"Clarify {len(anomalies.reason_coherence)} reason coherence flag(s) (PD course marked Critical/Scarce)."
        )
    if not steps:
        steps.append(
            "No anomalies detected — submissions appear clean for this period."
        )
    return steps[:5]


def generate_report(summary: BudgetSummary, anomalies: AnomalyReport) -> str:
    """Produce a structured markdown briefing report. Writes briefing_report_generated audit entry."""
    lines: list[str] = []

    # --- Summary ---
    lines += [
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Total submissions | {len(summary.per_submission_quality)} |",
        f"| Unique courses | {len(summary.course_demand)} |",
        f"| Total cost | £{summary.total_cost:,.0f} |",
        f"| Total T&S | £{summary.total_ts:,.0f} |",
        f"| Unresolved flags | {anomalies.anomaly_count} |",
        f"| Questionable spend | £{summary.questionable_spend:,.0f} of £{summary.total_spend:,.0f} surfaced for review |",
        "",
    ]

    # --- Course Demand ---
    lines += [
        "## Course Demand",
        "",
        "| Course ID | Count | Flag Count |",
        "| --- | --- | --- |",
    ]
    for d in summary.course_demand:
        lines.append(f"| {d['course_id']} | {d['count']} | {d['flag_count']} |")
    lines.append("")

    # --- Anomalies ---
    def _fmt_list(items: list[dict], keys: list[str]) -> list[str]:
        if not items:
            return ["None"]
        return [" | ".join(str(d.get(k, "")) for k in keys) for d in items]

    lines += ["## Anomalies", ""]

    lines += ["### Priority Inflation", ""]
    lines += _fmt_list(anomalies.priority_inflation, ["person_id", "pct_high", "total"])
    lines.append("")

    lines += ["### Eligibility Flags", ""]
    lines += _fmt_list(anomalies.eligibility_flags, ["person_id", "course_id", "type"])
    lines.append("")

    lines += ["### Unresolved Duplicates", ""]
    lines += _fmt_list(anomalies.unresolved_duplicates, ["person_id", "course_id"])
    lines.append("")

    lines += ["### Reason Coherence", ""]
    lines += _fmt_list(anomalies.reason_coherence, ["person_id", "course_id"])
    lines.append("")

    # --- Budget by Department ---
    lines += [
        "## Budget by Department",
        "",
        "| Department | Total (£) |",
        "| --- | --- |",
    ]
    for dept, total in sorted(
        summary.cost_by_department.items(), key=lambda x: x[1], reverse=True
    ):
        lines.append(f"| {dept} | £{total:,.0f} |")
    lines.append("")

    # --- Recommended Next Steps ---
    lines += ["## Recommended Next Steps", ""]
    for step in _derive_next_steps(anomalies):
        lines.append(f"- {step}")
    lines.append("")

    # --- Audit Trail ---
    lines += [
        "## Audit Trail",
        "",
        "Full session audit log available at data/audit.log",
    ]

    report = "\n".join(lines)

    write_audit_entry(
        AuditLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type="briefing_report_generated",
            agent_name="manager_briefing",
            detail=f"anomaly_count={anomalies.anomaly_count}",
        )
    )

    return report


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from src.models import BasketItem, SubmissionRecord

    REQUIRED_SECTIONS = [
        "## Summary",
        "## Course Demand",
        "## Anomalies",
        "## Budget by Department",
        "## Recommended Next Steps",
        "## Audit Trail",
    ]

    # Build two synthetic submissions without touching MCP
    item_a = BasketItem(
        person_id="P001",
        course_id="C001",
        reason="skill_gap",
        priority="High",
        challenge_types_fired=["role_fit"],
        override_justification=None,
    )
    item_b = BasketItem(
        person_id="P001",
        course_id="C002",
        reason="mandatory",
        priority="Low",
        challenge_types_fired=[],
        override_justification=None,
    )
    sub1 = SubmissionRecord(
        submission_id="TRS-2025-0001",
        person_id="P001",
        submitted_by="lm",
        period="2025-Q4",
        department="Engineering",
        timestamp="2025-10-01T10:00:00+00:00",
        status="submitted",
        items=[item_a, item_b],
        total_cost=500.0,
        total_ts=100.0,
        resolved_flag_count=0,
        unresolved_flag_count=1,
    )
    sub2 = SubmissionRecord(
        submission_id="TRS-2025-0002",
        person_id="P002",
        submitted_by="self",
        period="2025-Q4",
        department="Finance",
        timestamp="2025-10-02T09:00:00+00:00",
        status="submitted",
        items=[item_b],
        total_cost=250.0,
        total_ts=50.0,
        resolved_flag_count=0,
        unresolved_flag_count=0,
    )

    # Bypass MCP for self-check — patch local binding in __main__ globals
    fake_submissions = [sub1, sub2]
    _orig = globals()["get_submissions"]
    globals()["get_submissions"] = lambda **_kw: fake_submissions

    data = aggregate_submissions(period="2025-Q4")
    assert data.total_count == 2
    assert data.total_cost == 750.0
    assert data.flagged_spend == 600.0  # sub1 only (unresolved_flag_count > 0)

    summary = calculate_budget_estimate(data)
    assert summary.grand_total == 900.0
    assert 0.0 < summary.questionable_spend_pct < 1.0

    anomalies = flag_anomalies(data)
    assert anomalies.anomaly_count == len(anomalies.priority_inflation) + len(
        anomalies.eligibility_flags
    ) + len(anomalies.unresolved_duplicates) + len(anomalies.reason_coherence)

    report = generate_report(summary, anomalies)
    for section in REQUIRED_SECTIONS:
        assert section in report, f"Missing section: {section}"

    globals()["get_submissions"] = _orig
    print("ok")
