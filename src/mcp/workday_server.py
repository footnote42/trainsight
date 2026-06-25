"""Workday MCP server — exposes PII-free employee profiles.

Runs as an in-process stdio MCP server consumed by the ADK agent.
"""

import csv
import sys
from pathlib import Path
from typing import Optional

# Add workspace root to sys.path to allow running as a direct script
sys.path.append(str(Path(__file__).parent.parent.parent.resolve()))

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError as FastMCPToolError
from src.models import PersonProfile
from src.security import _assert_no_pii


# ---------------------------------------------------------------------------
# Custom ToolError (matches catalogue_server convention)
# ---------------------------------------------------------------------------

class ToolError(FastMCPToolError):
    def __init__(self, message: str = "", code: str = ""):
        self.code = code
        self.message = message
        super().__init__(message if message else code)


# ---------------------------------------------------------------------------
# Bootstrap — load data/workday.csv into two lookup dicts
# ---------------------------------------------------------------------------

_WORKDAY_PATH = Path("data/workday.csv")

if not _WORKDAY_PATH.exists():
    raise FileNotFoundError(f"Workday file not found at {_WORKDAY_PATH}")

_BY_WORKDAY_ID: dict[str, PersonProfile] = {}
_BY_EMAIL: dict[str, PersonProfile] = {}

with _WORKDAY_PATH.open(encoding="utf-8") as fh:
    for row in csv.DictReader(fh):
        direct_reports = [r for r in row["direct_reports"].split("|") if r]
        profile = PersonProfile(
            person_id=row["workday_id"],
            lead_technical_role=row["lead_technical_role"],
            job_family=row["job_family"],
            grade=row["grade"],
            management_chain=row["management_chain"].split("|"),
            direct_reports=direct_reports,
            has_direct_reports=len(direct_reports) > 0,
            department=row["department"],
        )
        _BY_WORKDAY_ID[row["workday_id"]] = profile
        _BY_EMAIL[row["email"]] = profile

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("workday-server")


@mcp.tool()
def get_profile(
    email: Optional[str] = None,
    workday_id: Optional[str] = None,
) -> PersonProfile:
    """Look up an employee profile by workday_id or email.

    Exactly one parameter must be provided.  The returned profile is
    PII-free — name, email, and age_band are never included.

    Args:
        email: Corporate email address (used for lookup only, never returned).
        workday_id: Workday employee identifier (e.g. "WD-001001").
    """
    if (email is None) == (workday_id is None):
        raise ToolError(
            message="Exactly one of 'email' or 'workday_id' must be provided.",
            code="INVALID_PARAMS",
        )

    if workday_id is not None:
        profile = _BY_WORKDAY_ID.get(workday_id)
    else:
        profile = _BY_EMAIL.get(email)  # type: ignore[arg-type]

    if profile is None:
        raise ToolError(
            message=f"No profile found for '{email or workday_id}'",
            code="PROFILE_NOT_FOUND",
        )

    _assert_no_pii(profile, person_id=profile.person_id)
    return profile


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # 1. Lookup by workday_id
    p = get_profile(workday_id="WD-001001")
    assert p.grade == "B2", f"Expected grade 'B2', got '{p.grade}'"

    # 2. Lookup by email — same record
    p2 = get_profile(email="wd.000001@company.example.com")
    assert p2.person_id == "WD-001001", f"Expected 'WD-001001', got '{p2.person_id}'"

    # 3. No PII attributes on the profile
    for banned in ("age_band", "name", "email"):
        assert not hasattr(p, banned), f"Profile must not have '{banned}' attribute"

    # 4. Unknown workday_id raises ToolError
    try:
        get_profile(workday_id="WD-NONEXISTENT")
        raise AssertionError("Expected ToolError for unknown workday_id")
    except ToolError as exc:
        assert exc.code == "PROFILE_NOT_FOUND"

    print("Self-check completed successfully. Running MCP stdio server...", file=sys.stderr)
    mcp.run(transport="stdio")
