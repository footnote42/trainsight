import re
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Add workspace root to sys.path to allow running as a direct script
sys.path.append(str(Path(__file__).parent.parent.parent.resolve()))

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError as FastMCPToolError
from src.models import SubmissionRecord, BasketItem, AuditLogEntry
from src.security import write_audit_entry


# Custom ToolError (same pattern as catalogue_server.py)
class ToolError(FastMCPToolError):
    def __init__(self, message: str = "", code: str = ""):
        self.code = code
        self.message = message
        super().__init__(message if message else code)


# Initialize FastMCP server
mcp = FastMCP("submissions-server")

# In-memory store, keyed by submission_id
_submissions: dict[str, SubmissionRecord] = {}

# Regex to extract a 4-digit year from a period string like "2025-Q4"
_YEAR_RE = re.compile(r"(\d{4})")


def _extract_year(period: str) -> int:
    """Extract the 4-digit year from a period string, falling back to current UTC year."""
    m = _YEAR_RE.search(period)
    return int(m.group(1)) if m else datetime.now(timezone.utc).year


def _next_sequence(period: str) -> int:
    """Count existing submissions for the given period and return the next sequence number."""
    count = sum(1 for r in _submissions.values() if r.period == period)
    return count + 1


# ---------------------------------------------------------------------------
# Tool 1: get_submissions (read-only)
# ---------------------------------------------------------------------------
@mcp.tool()
def get_submissions(
    period: Optional[str] = None,
    person_id: Optional[str] = None,
    course_id: Optional[str] = None,
) -> list[SubmissionRecord]:
    """Get submission records, optionally filtered.

    Args:
        period: Optional period prefix to match (e.g. "2025" matches "2025-Q4").
        person_id: Optional exact Workday ID of the submitter.
        course_id: Optional course ID; matches if any basket item has this course.
    """
    results = list(_submissions.values())

    if period is not None:
        results = [r for r in results if r.period.startswith(period)]

    if person_id is not None:
        results = [r for r in results if r.person_id == person_id]

    if course_id is not None:
        results = [
            r for r in results
            if any(item.course_id == course_id for item in r.items)
        ]

    return results


# ---------------------------------------------------------------------------
# Tool 2: create_submission (write, audit-logged)
# ---------------------------------------------------------------------------
@mcp.tool()
def create_submission(
    record: SubmissionRecord,
    hitl_token: str,
) -> SubmissionRecord:
    """Write a submission record to the store.

    Token validation happens upstream in submit_request (src/skills/fetch.py).
    The hitl_token is logged in the audit entry but NOT re-validated here.

    Args:
        record: The SubmissionRecord to persist.
        hitl_token: HITL token string (audit-only, not validated).
    """
    now = datetime.now(timezone.utc).isoformat()
    submission_id = None

    try:
        # Generate submission_id: TRS-{year}-{sequence:04d}
        year = _extract_year(record.period)
        seq = _next_sequence(record.period)
        submission_id = f"TRS-{year}-{seq:04d}"

        # Deep-copy to avoid caller mutation, assign generated ID
        stored = deepcopy(record)
        stored.submission_id = submission_id

        # Persist
        _submissions[submission_id] = stored

        # Audit: success
        write_audit_entry(AuditLogEntry(
            timestamp=now,
            event_type="submit_request_write",
            agent_name="submission_challenger",
            person_id=stored.person_id,
            submission_id=submission_id,
            course_ids=[item.course_id for item in stored.items],
            outcome="success",
            detail=f"hitl_token={hitl_token}",
        ))

        return stored

    except Exception as exc:
        # Guarantee: zero records written on error
        if submission_id is not None:
            _submissions.pop(submission_id, None)

        # Audit: failure (always written)
        write_audit_entry(AuditLogEntry(
            timestamp=now,
            event_type="submit_request_write",
            agent_name="submission_challenger",
            person_id=getattr(record, "person_id", None),
            submission_id=submission_id,
            outcome="failure",
            detail=f"hitl_token={hitl_token}; error={exc}",
        ))

        if isinstance(exc, ToolError):
            raise
        raise ToolError(code="SUBMISSION_WRITE_FAILED", message=str(exc)) from exc


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Running submissions_server.py self-checks...")

    # 1. Empty store returns []
    assert get_submissions() == [], "Expected empty list from empty store"
    print("  [PASS] Empty store returns []")

    # 2. Create a dummy record
    dummy_item = BasketItem(
        person_id="WD-001234",
        course_id="MEWP-001",
        reason="Capability Gap",
        priority="Medium",
        challenge_types_fired=[],
    )
    dummy_record = SubmissionRecord(
        submission_id="",  # will be generated
        person_id="WD-001234",
        submitted_by="self",
        period="2025-Q4",
        department="Engineering Operations",
        timestamp=datetime.now(timezone.utc).isoformat(),
        status="submitted",
        items=[dummy_item],
        total_cost=350.0,
        total_ts=50.0,
        resolved_flag_count=0,
        unresolved_flag_count=0,
    )

    # 3. Write with audit-only token (no validation -- should succeed)
    result = create_submission(dummy_record, hitl_token="dummy-token-for-test")
    assert result.submission_id == "TRS-2025-0001", (
        f"Expected TRS-2025-0001, got {result.submission_id}"
    )
    print(f"  [PASS] create_submission returned {result.submission_id}")

    # 4. get_submissions() returns the record
    all_subs = get_submissions()
    assert len(all_subs) == 1, f"Expected 1 record, got {len(all_subs)}"
    print("  [PASS] get_submissions() returns 1 record")

    # 5. Period prefix filter
    assert len(get_submissions(period="2025")) == 1, "Period prefix '2025' should match"
    assert len(get_submissions(period="2025-Q4")) == 1, "Period prefix '2025-Q4' should match"
    assert len(get_submissions(period="2024")) == 0, "Period prefix '2024' should not match"
    print("  [PASS] Period prefix filtering works")

    # 6. person_id exact filter
    assert len(get_submissions(person_id="WD-001234")) == 1, "person_id match failed"
    assert len(get_submissions(person_id="WD-999999")) == 0, "person_id non-match should return []"
    print("  [PASS] person_id exact filtering works")

    # 7. course_id any-item filter
    assert len(get_submissions(course_id="MEWP-001")) == 1, "course_id match failed"
    assert len(get_submissions(course_id="NONEXIST")) == 0, "course_id non-match should return []"
    print("  [PASS] course_id any-item filtering works")

    # 8. Combined filters
    assert len(get_submissions(period="2025", person_id="WD-001234")) == 1
    assert len(get_submissions(period="2025", person_id="WD-999999")) == 0
    print("  [PASS] Combined filtering works")

    # 9. Second submission increments sequence
    result2 = create_submission(dummy_record, hitl_token="dummy-token-2")
    assert result2.submission_id == "TRS-2025-0002", (
        f"Expected TRS-2025-0002, got {result2.submission_id}"
    )
    assert len(get_submissions()) == 2
    print(f"  [PASS] Second submission got {result2.submission_id}")

    print("All submissions_server.py self-checks passed!")
    print("Running MCP stdio server...", file=sys.stderr)
    mcp.run(transport="stdio")
