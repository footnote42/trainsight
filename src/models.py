from dataclasses import dataclass
from typing import Literal, Optional, Any

# 1. Constants and Literals
GRADE_ORDER: list[str] = ["A1", "A2", "B1", "B2", "C1", "C2", "D1", "D2", "DS"]

PD_CATEGORIES: frozenset[str] = frozenset({
    "Professional Development",
    "Leadership",
    "Management",
    "Personal Effectiveness",
})

REASON_VALUES = Literal[
    "Capability Gap",
    "Critical/Scarce Skill",
    "Maintaining Capability",
    "Resilience",
    "Professional Development",
]

PRIORITY_VALUES = Literal["High", "Medium", "Low"]

EVENT_TYPES = Literal[
    "fetch_profile",
    "fetch_prior_submissions",
    "challenge_issued",
    "user_response_received",
    "override_accepted",
    "submit_confirm_clicked",
    "submit_request_write",       # success or failure
    "pii_guard_triggered",
    "injection_attempt_detected",
    "briefing_mcp_read",
    "briefing_report_generated",
]

# 2. CourseRecord
@dataclass
class CourseRecord:
    course_id: str                    # unique identifier, e.g. "MEWP-001"
    title: str
    description: str                  # free text; sanitised before LLM context
    type: Literal["Internal", "External", "Further Education"]
    category: str                     # e.g., Safety, Compliance, Technical, etc.
    duration_hours: float             # total hours
    provider: str
    cost_per_person: float            # GBP, course fee only
    ts_cost: float                    # GBP, estimated travel and subsistence
    sme_contact: str                  # name for eligibility escalation
    target_roles: list[str]           # non-empty; Lead Technical Role or Job Family
    min_grade: Optional[str] = None   # e.g., "C1" means C1 or above; None means any grade

# 3. PersonProfile
@dataclass
class PersonProfile:
    person_id: str                    # Workday ID, e.g. "WD-001234"
    lead_technical_role: str          # e.g. "Plant Operator", "Systems Engineer"
    job_family: str                   # e.g. "Engineering Operations", "Corporate Services"
    grade: Literal["A1", "A2", "B1", "B2", "C1", "C2", "D1", "D2", "DS"]
    management_chain: list[str]       # Workday IDs from direct manager to Director (inclusive)
    direct_reports: list[str]         # Workday IDs; empty list if not a line manager
    has_direct_reports: bool          # True iff direct_reports is non-empty
    department: str                   # derived from job_family at fetch time; used for budget grouping

# 4. BasketItem
@dataclass
class BasketItem:
    person_id: str                    # Workday ID of the person the course is FOR
    course_id: str
    reason: REASON_VALUES
    priority: PRIORITY_VALUES
    challenge_types_fired: list[str]  # e.g. ["role_fit", "priority_inflation"]
    override_justification: Optional[str] = None  # non-empty if challenge was overridden

# 5. SubmissionRecord
@dataclass
class SubmissionRecord:
    submission_id: str                # assigned by submissions-mcp on write; format TRS-YYYY-NNNN
    person_id: str                    # Workday ID of the primary submitter
    submitted_by: Literal["self", "lm"]
    period: str                       # e.g. "2025-Q4"
    department: str                   # job_family of the primary submitter
    timestamp: str                    # ISO 8601
    status: Literal["draft", "submitted"]
    items: list[BasketItem]
    total_cost: float                 # sum of cost_per_person for all items
    total_ts: float                   # sum of ts_cost for all items
    resolved_flag_count: int          # challenges with override_justification set
    unresolved_flag_count: int        # challenges fired but not overridden

# 6. AuditLogEntry
@dataclass
class AuditLogEntry:
    timestamp: str                     # ISO 8601, UTC
    event_type: EVENT_TYPES
    agent_name: Literal["submission_challenger", "manager_briefing"]
    person_id: Optional[str] = None           # required for: all Submission Challenger events
    course_ids: Optional[list[str]] = None    # required for: challenge_issued, override_accepted, etc.
    submission_id: Optional[str] = None       # required for: submit_confirm_clicked, submit_request_write
    challenge_type: Optional[str] = None      # required for: challenge_issued, override_accepted
    justification: Optional[str] = None       # required for: override_accepted (full text)
    outcome: Optional[Literal["success", "failure"]] = None  # required for: submit_request_write
    detail: Optional[str] = None              # free text; required for: injection_attempt_detected

# 7. HITLToken
@dataclass
class HITLToken:
    token: str          # secrets.token_urlsafe(32); this string is sent to the client
    session_id: str     # server-side session identifier
    basket_hash: str    # SHA-256 hex of canonical basket JSON at confirm time
    issued_at: str      # ISO 8601 UTC
    expires_at: str     # issued_at + 600 seconds (10 minutes)
    used: bool          # False on issue; set True immediately after first valid use

# 8. ChallengeResult
@dataclass
class ChallengeResult:
    type: Literal["role_fit", "priority_inflation", "reason_coherence", "quantity", "duplicate"]
    course_id: str
    details: dict[str, Any]

# 9. CoherenceInput
@dataclass
class CoherenceInput:
    course_id: str
    course_title: str
    course_category: str
    course_description_sanitised: str
    reason_given: str
    basis_for_review: str

# 10. Briefing-related Dataclasses
@dataclass
class AggregatedData:
    period: str
    submissions: list[SubmissionRecord]
    total_count: int
    unique_course_ids: list[str]
    total_cost: float                        # GBP
    total_ts: float                          # GBP
    unresolved_flag_count: int               # sum of unresolved_flag_count across all records
    flagged_submission_ids: list[str]        # submission_ids with unresolved_flag_count > 0
    flagged_spend: float                     # total_cost + total_ts for flagged submissions only
    cost_by_department: dict[str, float]     # department -> total_cost + total_ts

@dataclass
class BudgetSummary:
    total_cost: float
    total_ts: float
    grand_total: float                           # total_cost + total_ts
    cost_by_department: dict[str, float]
    questionable_spend: float                    # = AggregatedData.flagged_spend
    total_spend: float                           # total_cost + total_ts across all submissions
    questionable_spend_pct: float                # questionable_spend / total_spend * 100
    per_submission_quality: dict[str, float]     # submission_id -> quality score (0.0-1.0)
    course_demand: list[dict[str, Any]]          # sorted by submission count desc

@dataclass
class AnomalyReport:
    priority_inflation: list[dict[str, Any]]     # {"person_id": str, "pct_high": float, "total": int}
    eligibility_flags: list[dict[str, Any]]      # {"person_id": str, "course_id": str, "type": str}
    unresolved_duplicates: list[dict[str, Any]]  # {"person_id": str, "course_id": str}
    reason_coherence: list[dict[str, Any]]       # {"person_id": str, "course_id": str}
    anomaly_count: int                           # sum of len() of all four lists


# --- Self-check assertions ---
_forbidden = {"age_band", "name", "email"}
_profile_fields = {f.name for f in PersonProfile.__dataclass_fields__.values()}
assert not _forbidden.intersection(_profile_fields), (
    f"PersonProfile contains forbidden fields: {_forbidden.intersection(_profile_fields)}"
)
for _field_name in _forbidden:
    assert not hasattr(PersonProfile, _field_name), f"PersonProfile has forbidden attribute: {_field_name}"
