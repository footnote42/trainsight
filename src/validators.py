import sys
from pathlib import Path
from typing import Optional, Any

# Add workspace root to sys.path to allow running as a direct script
sys.path.append(str(Path(__file__).parent.parent.resolve()))

from src.models import (
    PersonProfile,
    CourseRecord,
    BasketItem,
    SubmissionRecord,
    ChallengeResult,
    CoherenceInput,
    GRADE_ORDER,
    PD_CATEGORIES,
)

# Constants
VACANCY_PERSON_ID_PREFIX = "VACANCY-"

# ---------------------------------------------------------------------------
# RULES_ONLY_TEMPLATES (TR-EVAL-005 exact strings)
# ---------------------------------------------------------------------------
RULES_ONLY_TEMPLATES: dict[str, str] = {
    "role_fit": (
        "Role eligibility check: {role_mismatch_msg}{grade_mismatch_msg}. "
        "Please review with {sme_contact} before submitting."
    ),
    "priority_inflation": (
        "Priority inflation: {high_count} of {total} items ({pct}%) are marked High priority, "
        "which exceeds the 60% threshold."
    ),
    "reason_coherence": (
        "Reason coherence: '{course_title}' is categorised as '{course_category}', "
        "which is a professional development course. "
        "The reason 'Critical/Scarce Skill' is typically reserved for genuine operational gaps. "
        "Can you confirm why this classification applies?"
    ),
    "quantity": (
        "Quantity check: {total_courses} courses for {team_size} team members "
        "({ratio} per person). This is above the typical ratio of 1.5. "
        "Please review whether all selections are required."
    ),
    "duplicate": (
        "Duplicate detected: '{course_id}' has already been submitted for this person. "
        "Please confirm whether both entries are required."
    ),
}


# ---------------------------------------------------------------------------
# 1. Role Fit Validator (TR-VALIDATOR-001)
# ---------------------------------------------------------------------------
def check_role_fit(
    profile: PersonProfile,
    course: CourseRecord,
) -> Optional[ChallengeResult]:
    """Checks role and grade eligibility.

    Returns:
        ChallengeResult if either check fails, else None.
    """
    role_match = (
        "all" in course.target_roles
        or profile.lead_technical_role in course.target_roles
        or profile.job_family in course.target_roles
    )
    grade_match = (
        course.min_grade is None
        or GRADE_ORDER.index(profile.grade) >= GRADE_ORDER.index(course.min_grade)
    )

    if role_match and grade_match:
        return None

    details: dict[str, Any] = {}
    if not role_match:
        details["role_mismatch"] = {
            "submitter_role": profile.lead_technical_role,
            "submitter_family": profile.job_family,
            "course_target_roles": course.target_roles,
        }
    if not grade_match:
        details["grade_mismatch"] = {
            "submitter_grade": profile.grade,
            "required_min_grade": course.min_grade,
        }
    if course.sme_contact:
        details["sme_contact"] = course.sme_contact

    return ChallengeResult(
        type="role_fit",
        course_id=course.course_id,
        details=details,
    )


# ---------------------------------------------------------------------------
# 2. Priority Inflation Validator (TR-VALIDATOR-002)
# ---------------------------------------------------------------------------
def check_priority_inflation(
    basket: list[BasketItem],
) -> Optional[ChallengeResult]:
    """Checks if the proportion of High priority items in the basket strictly exceeds 60%."""
    if not basket:
        return None

    high_count = sum(1 for i in basket if i.priority == "High")
    ratio = high_count / len(basket)

    if ratio > 0.60:
        return ChallengeResult(
            type="priority_inflation",
            course_id="basket",
            details={
                "high_count": high_count,
                "total": len(basket),
                "pct": round(ratio * 100, 1),
            },
        )
    return None


# ---------------------------------------------------------------------------
# 3. Reason Coherence Validator (TR-VALIDATOR-003)
# ---------------------------------------------------------------------------
def check_reason_coherence(
    item: BasketItem,
    course: CourseRecord,
) -> Optional[CoherenceInput]:
    """Pure Python pre-filter to check if LLM reason coherence check is needed."""
    if item.reason == "Critical/Scarce Skill" and course.category in PD_CATEGORIES:
        return CoherenceInput(
            course_id=course.course_id,
            course_title=course.title,
            course_category=course.category,
            course_description_sanitised=course.description,
            reason_given="Critical/Scarce Skill",
            basis_for_review="Course category is PD-type; reason requires LLM review",
        )
    return None


# ---------------------------------------------------------------------------
# 4. Quantity Validator (TR-VALIDATOR-004)
# ---------------------------------------------------------------------------
def check_quantity(
    basket: list[BasketItem],
    team_size: int,
) -> Optional[ChallengeResult]:
    """Checks if the quantity of courses per team member meets/exceeds 1.5."""
    if team_size == 0:
        return None

    ratio = len(basket) / team_size
    if ratio >= 1.5:
        return ChallengeResult(
            type="quantity",
            course_id="basket",
            details={
                "total_courses": len(basket),
                "team_size": team_size,
                "ratio": round(ratio, 2),
            },
        )
    return None


def compute_team_size(basket: list[BasketItem]) -> int:
    """Computes distinct team size excluding vacancy placeholders."""
    return len({
        item.person_id for item in basket
        if not item.person_id.startswith(VACANCY_PERSON_ID_PREFIX)
    })


# ---------------------------------------------------------------------------
# 5. Duplicate Validator (TR-VALIDATOR-005)
# ---------------------------------------------------------------------------
def detect_duplicates(
    basket: list[BasketItem],
    prior: list[SubmissionRecord],
) -> list[ChallengeResult]:
    """Checks for exact (person_id, course_id) matches in prior submissions."""
    prior_pairs = {
        (item.person_id, item.course_id)
        for record in prior
        for item in record.items
    }

    results = []
    for item in basket:
        if (item.person_id, item.course_id) in prior_pairs:
            results.append(
                ChallengeResult(
                    type="duplicate",
                    course_id=item.course_id,
                    details={
                        "person_id": item.person_id,
                        "course_id": item.course_id,
                    },
                )
            )
    return results


# ---------------------------------------------------------------------------
# 7. Generate Challenge Text (TR-EVAL-005)
# ---------------------------------------------------------------------------
def generate_challenge_text(
    result: ChallengeResult,
    rules_only: bool,
    courses: dict[str, CourseRecord],
) -> str:
    """Formats the challenge text depending on the mode."""
    if not rules_only:
        raise NotImplementedError("LLM generation path not implemented in validators module")

    template = RULES_ONLY_TEMPLATES.get(result.type)
    if not template:
        raise ValueError(f"Unknown challenge type: {result.type}")

    # Build formatting arguments dictionary
    fmt_args = {}
    if result.details:
        fmt_args.update(result.details)

    # Inject course fields if found
    course = courses.get(result.course_id)
    if course:
        fmt_args["course_title"] = course.title
        fmt_args["course_category"] = course.category
        fmt_args["course_id"] = course.course_id
    else:
        fmt_args["course_title"] = ""
        fmt_args["course_category"] = ""
        fmt_args["course_id"] = result.course_id or ""

    if result.type == "role_fit":
        # Formulate role_mismatch_msg
        role_mismatch = result.details.get("role_mismatch")
        if role_mismatch:
            fmt_args["role_mismatch_msg"] = (
                f"role mismatch (submitter role '{role_mismatch['submitter_role']}', "
                f"family '{role_mismatch['submitter_family']}' not in {role_mismatch['course_target_roles']})"
            )
        else:
            fmt_args["role_mismatch_msg"] = ""

        # Formulate grade_mismatch_msg
        grade_mismatch = result.details.get("grade_mismatch")
        if grade_mismatch:
            prefix = " and " if role_mismatch else ""
            fmt_args["grade_mismatch_msg"] = (
                f"{prefix}grade mismatch (submitter grade '{grade_mismatch['submitter_grade']}' "
                f"requires minimum '{grade_mismatch['required_min_grade']}')"
            )
        else:
            fmt_args["grade_mismatch_msg"] = ""

        # Default sme_contact if missing
        if "sme_contact" not in fmt_args:
            fmt_args["sme_contact"] = "SME"

    return template.format(**fmt_args)


# ---------------------------------------------------------------------------
# Self-checks
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Running validators.py self-checks...")

    # 1. empty basket returns None for priority inflation
    assert check_priority_inflation([]) is None, "Empty basket should return None"
    print("  [PASS] check_priority_inflation([]) is None")

    # Helper to build basket items
    def make_item(person_id: str, course_id: str, priority: str, reason: str = "Capability Gap") -> BasketItem:
        return BasketItem(
            person_id=person_id,
            course_id=course_id,
            priority=priority,
            reason=reason,
            challenge_types_fired=[],
        )

    # 2. basket with 3 High, 1 Medium (75% -> >60%) fires
    basket_75 = [
        make_item("WD-1", "C1", "High"),
        make_item("WD-2", "C2", "High"),
        make_item("WD-3", "C3", "High"),
        make_item("WD-4", "C4", "Medium"),
    ]
    res_75 = check_priority_inflation(basket_75)
    assert res_75 is not None, "75% High should fire priority inflation"
    assert res_75.details["high_count"] == 3
    assert res_75.details["total"] == 4
    assert res_75.details["pct"] == 75.0
    print("  [PASS] check_priority_inflation with 75% High fires")

    # 3. basket with exactly 60% (3 High, 2 Medium -> 60%) returns None
    basket_60 = [
        make_item("WD-1", "C1", "High"),
        make_item("WD-2", "C2", "High"),
        make_item("WD-3", "C3", "High"),
        make_item("WD-4", "C4", "Medium"),
        make_item("WD-5", "C5", "Medium"),
    ]
    assert check_priority_inflation(basket_60) is None, "Exactly 60% should not fire"
    print("  [PASS] check_priority_inflation with 60% High returns None")

    # 4. compute_team_size excludes vacancies
    basket_team = [
        make_item("WD-1", "C1", "High"),
        make_item("WD-1", "C2", "High"),
        make_item("VACANCY-1", "C3", "High"),
        make_item("VACANCY-2", "C4", "High"),
    ]
    assert compute_team_size(basket_team) == 1, f"Expected team size 1, got {compute_team_size(basket_team)}"
    print("  [PASS] compute_team_size excludes vacancies")

    # 5. check_quantity validator
    assert check_quantity(basket_team, 1) is not None, "Ratio 4/1 = 4 >= 1.5 should fire"
    assert check_quantity(basket_team, 3) is None, "Ratio 4/3 = 1.33 < 1.5 should not fire"
    assert check_quantity(basket_team, 0) is None, "Team size 0 should return None"
    print("  [PASS] check_quantity fires correctly")

    # 6. check_reason_coherence
    course_pd = CourseRecord(
        course_id="C1",
        title="Leadership 101",
        description="Lead things",
        type="Internal",
        category="Leadership",
        duration_hours=10,
        provider="Internal",
        cost_per_person=0.0,
        ts_cost=0.0,
        sme_contact="Jane Doe",
        target_roles=["all"],
    )
    course_tech = CourseRecord(
        course_id="C2",
        title="Welding",
        description="Weld things",
        type="Internal",
        category="Technical",
        duration_hours=10,
        provider="Internal",
        cost_per_person=100.0,
        ts_cost=0.0,
        sme_contact="Jane Doe",
        target_roles=["all"],
    )
    # Critical reason + PD category -> fires pre-filter
    assert check_reason_coherence(make_item("WD-1", "C1", "High", "Critical/Scarce Skill"), course_pd) is not None
    # Critical reason + Technical category -> does not fire
    assert check_reason_coherence(make_item("WD-1", "C2", "High", "Critical/Scarce Skill"), course_tech) is None
    # Professional Development reason + PD category -> does not fire
    assert check_reason_coherence(make_item("WD-1", "C1", "High", "Professional Development"), course_pd) is None
    print("  [PASS] check_reason_coherence pre-filter works")

    # 7. detect_duplicates
    prior = [
        SubmissionRecord(
            submission_id="TRS-1",
            person_id="WD-1",
            submitted_by="self",
            period="2025-Q1",
            department="Engineering",
            timestamp="",
            status="submitted",
            items=[make_item("WD-1", "C1", "High")],
            total_cost=0.0,
            total_ts=0.0,
            resolved_flag_count=0,
            unresolved_flag_count=0,
        )
    ]
    basket_dup = [make_item("WD-1", "C1", "High"), make_item("WD-1", "C2", "High")]
    dups = detect_duplicates(basket_dup, prior)
    assert len(dups) == 1
    assert dups[0].course_id == "C1"
    print("  [PASS] detect_duplicates works")

    # 8. check_role_fit
    profile = PersonProfile(
        person_id="WD-1",
        lead_technical_role="Welder",
        job_family="Engineering",
        grade="B1",
        management_chain=[],
        direct_reports=[],
        has_direct_reports=False,
        department="Engineering",
    )
    course_eligible = CourseRecord(
        course_id="C1",
        title="Welding 102",
        description="",
        type="Internal",
        category="Technical",
        duration_hours=10,
        provider="",
        cost_per_person=0,
        ts_cost=0,
        sme_contact="Welding Lead",
        target_roles=["Welder"],
        min_grade="A2",
    )
    course_wrong_role = CourseRecord(
        course_id="C2",
        title="Accounting",
        description="",
        type="Internal",
        category="Corporate",
        duration_hours=10,
        provider="",
        cost_per_person=0,
        ts_cost=0,
        sme_contact="Finance Lead",
        target_roles=["Accountant"],
        min_grade="A2",
    )
    course_wrong_grade = CourseRecord(
        course_id="C3",
        title="Advanced Welding",
        description="",
        type="Internal",
        category="Technical",
        duration_hours=10,
        provider="",
        cost_per_person=0,
        ts_cost=0,
        sme_contact="Welding Lead",
        target_roles=["Welder"],
        min_grade="C1",  # Welder is B1, C1 requires higher grade (A1, A2, B1, B2, C1 -> C1 is higher index)
    )
    # Check A2 vs B1: GRADE_ORDER = ["A1", "A2", "B1", "B2", "C1", "C2", "D1", "D2", "DS"]
    # index of B1 is 2, index of A2 is 1. B1 (2) >= A2 (1) is True.
    # index of C1 is 4. B1 (2) >= C1 (4) is False.
    assert check_role_fit(profile, course_eligible) is None
    
    wrong_role_res = check_role_fit(profile, course_wrong_role)
    assert wrong_role_res is not None
    assert "role_mismatch" in wrong_role_res.details
    assert "grade_mismatch" not in wrong_role_res.details
    
    wrong_grade_res = check_role_fit(profile, course_wrong_grade)
    assert wrong_grade_res is not None
    assert "role_mismatch" not in wrong_grade_res.details
    assert "grade_mismatch" in wrong_grade_res.details
    print("  [PASS] check_role_fit checks role and grade correctly")

    # 9. generate_challenge_text formatting
    courses_dict = {"C1": course_pd, "C2": course_tech}
    
    # Priority inflation text check
    res_pi = check_priority_inflation(basket_75)
    assert res_pi is not None
    pi_text = generate_challenge_text(res_pi, rules_only=True, courses=courses_dict)
    assert "Priority inflation: 3 of 4 items (75.0%)" in pi_text
    
    # Role fit text check
    role_fit_text = generate_challenge_text(wrong_role_res, rules_only=True, courses=courses_dict)
    assert "Role eligibility check: role mismatch (submitter role 'Welder', family 'Engineering' not in ['Accountant'])" in role_fit_text
    assert "Please review with Finance Lead before submitting." in role_fit_text

    print("All validators.py self-checks passed!")
