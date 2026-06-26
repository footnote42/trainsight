"""CLI evaluation harness for trainsight.

Entry point: python eval/harness.py --scenario [1|2|3|4|5|H1|H2|H3|all] [--rules-only] --output <path>
"""

import argparse
import sys
import os
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Add workspace root to sys.path
sys.path.append(str(Path(__file__).parent.parent.resolve()))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


from src.models import (
    PersonProfile,
    BasketItem,
    SubmissionRecord,
    CourseRecord,
    ChallengeResult,
)
from src.validators import (
    check_role_fit,
    check_priority_inflation,
    check_quantity,
    detect_duplicates,
    check_reason_coherence,
    generate_challenge_text as rules_generate_challenge_text,
    compute_team_size,
)


def load_courses() -> dict[str, CourseRecord]:
    """Loads all CourseRecords from data/catalogue.json."""
    catalogue_path = Path("data/catalogue.json")
    with open(catalogue_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {
        item["course_id"]: CourseRecord(
            course_id=item["course_id"],
            title=item["title"],
            description=item["description"],
            type=item["type"],
            category=item["category"],
            duration_hours=item["duration_hours"],
            provider=item["provider"],
            cost_per_person=item["cost_per_person"],
            ts_cost=item["ts_cost"],
            sme_contact=item["sme_contact"],
            target_roles=item["target_roles"],
            min_grade=item.get("min_grade"),
        )
        for item in data
    }


def get_person_profile(workday_id: str, scenario_person: dict) -> PersonProfile:
    """Gets person profile from scenario context or resolves via workday server."""
    if workday_id == scenario_person.get("person_id"):
        return PersonProfile(
            person_id=scenario_person["person_id"],
            lead_technical_role=scenario_person["lead_technical_role"],
            job_family=scenario_person["job_family"],
            grade=scenario_person["grade"],
            management_chain=scenario_person["management_chain"],
            direct_reports=scenario_person["direct_reports"],
            has_direct_reports=scenario_person["has_direct_reports"],
            department=scenario_person["department"],
        )
    # Resolve via workday CSV lookup mapping
    from src.mcp.workday_server import get_profile
    return get_profile(workday_id=workday_id)


def run_scenario_validators(
    scenario_data: dict,
    courses_dict: dict[str, CourseRecord]
) -> list[ChallengeResult]:
    """Runs all validators against scenario.basket + scenario.person + scenario.prior_submissions."""
    # 1. Parse basket items
    basket_items = []
    for item in scenario_data["basket"]:
        basket_items.append(
            BasketItem(
                person_id=item["person_id"],
                course_id=item["course_id"],
                reason=item["reason"],
                priority=item["priority"],
                challenge_types_fired=item.get("challenge_types_fired", []),
                override_justification=item.get("override_justification"),
            )
        )

    # 2. Parse prior submissions
    prior_subs = []
    for sub in scenario_data.get("prior_submissions", []):
        sub_items = []
        for item in sub.get("items", []):
            sub_items.append(
                BasketItem(
                    person_id=item["person_id"],
                    course_id=item["course_id"],
                    reason=item["reason"],
                    priority=item["priority"],
                    challenge_types_fired=item.get("challenge_types_fired", []),
                    override_justification=item.get("override_justification"),
                )
            )
        prior_subs.append(
            SubmissionRecord(
                submission_id=sub["submission_id"],
                person_id=sub["person_id"],
                submitted_by=sub["submitted_by"],
                period=sub["period"],
                department=sub["department"],
                timestamp=sub["timestamp"],
                status=sub["status"],
                items=sub_items,
                total_cost=sub.get("total_cost", 0.0),
                total_ts=sub.get("total_ts", 0.0),
                resolved_flag_count=sub.get("resolved_flag_count", 0),
                unresolved_flag_count=sub.get("unresolved_flag_count", 0),
            )
        )

    fired_challenges: list[ChallengeResult] = []

    # A. Duplicate check
    dup_results = detect_duplicates(basket_items, prior_subs)
    fired_challenges.extend(dup_results)

    # B. Role fit check
    for item in basket_items:
        course = courses_dict.get(item.course_id)
        if not course:
            continue
        profile = get_person_profile(item.person_id, scenario_data["person"])
        res_rf = check_role_fit(profile, course)
        if res_rf:
            fired_challenges.append(res_rf)

    # C. Priority inflation check
    res_pi = check_priority_inflation(basket_items)
    if res_pi:
        fired_challenges.append(res_pi)

    # D. Quantity check (only in Line Manager mode)
    if scenario_data.get("submission_mode") == "lm":
        team_size = compute_team_size(basket_items)
        res_q = check_quantity(basket_items, team_size)
        if res_q:
            fired_challenges.append(res_q)

    # E. Reason coherence check
    for item in basket_items:
        course = courses_dict.get(item.course_id)
        if not course:
            continue
        res_rc = check_reason_coherence(item, course)
        if res_rc:
            fired_challenges.append(
                ChallengeResult(
                    type="reason_coherence",
                    course_id=item.course_id,
                    details={}
                )
            )

    return fired_challenges


def score_correctness(
    fired: list[ChallengeResult],
    ground_truth: list[dict],
) -> tuple[int, list[str]]:
    """Returns (score, list_of_reasons). Matches TR-EVAL-003 exactly."""
    fired_keys = {(c.type, c.course_id) for c in fired}
    truth_keys = {(g["type"], g["course_id"]) for g in ground_truth}

    score = 0
    reasons = []

    if not truth_keys:  # clean scenario
        if not fired_keys:
            score += 1
            reasons.append("+1: clean scenario, no false positives")
        else:
            for key in fired_keys:
                score -= 1
                reasons.append(f"-1: false positive {key}")
    else:
        for key in truth_keys:
            if key in fired_keys:
                score += 1
                reasons.append(f"+1: expected challenge fired {key}")
            else:
                score -= 1
                reasons.append(f"-1: missed expected challenge {key}")
        for key in fired_keys:
            if key not in truth_keys:
                score -= 1
                reasons.append(f"-1: false positive {key}")

    return score, reasons


def generate_challenge_text_llm(
    client: Any,
    result: ChallengeResult,
    courses: dict[str, CourseRecord],
    person_profile: PersonProfile,
    basket: list[dict],
) -> str:
    """Generates polite, inquisitive challenge text using LLM."""
    context_lines = []
    context_lines.append(
        f"Submitter Profile: Grade={person_profile.grade}, "
        f"Role='{person_profile.lead_technical_role}', "
        f"Job Family='{person_profile.job_family}', "
        f"Department='{person_profile.department}', "
        f"Has Direct Reports={person_profile.has_direct_reports}"
    )
    context_lines.append("Basket Items:")
    for item in basket:
        c = courses.get(item["course_id"])
        c_title = c.title if c else "Unknown"
        c_cat = c.category if c else "Unknown"
        context_lines.append(
            f"  - Course: '{c_title}' ({item['course_id']}) | "
            f"Category: '{c_cat}' | Reason: '{item['reason']}' | "
            f"Priority: '{item['priority']}'"
        )
    scenario_context = "\n".join(context_lines)

    prompt = (
        "You are the Training Submission Challenger, an AI assistant review tool.\n"
        "Generate a challenge question/message for a submitter regarding a potential issue in their training request.\n\n"
        "CRITICAL REQUIREMENTS:\n"
        "1. Your tone must be inquisitive and collegial, not accusatory. Assume good intent. Ask the submitter to confirm or explain rather than declaring them wrong. Reads like a colleague flagging something.\n"
        "2. Cite specific data points (course name, grade, priority count, reason classification) to make it specific and actionable.\n"
        "3. Focus ONLY on the request characteristics (role eligibility, quantity, priority classification) and NEVER on the person's capability or standing.\n"
        "4. If there is grade/role mismatch, surface the SME contact from the course record and suggest they discuss with them before finalising.\n"
        "5. Output ONLY the raw challenge question/message. No markdown block wrappers, no introduction.\n\n"
        f"SCENARIO CONTEXT:\n"
        f"{scenario_context}\n\n"
        f"CHALLENGE TYPE: {result.type}\n"
    )
    if result.course_id and result.course_id in courses:
        course = courses[result.course_id]
        prompt += (
            f"Course Details:\n"
            f"  ID: {course.course_id}\n"
            f"  Title: {course.title}\n"
            f"  Category: {course.category}\n"
            f"  Target Roles: {course.target_roles}\n"
            f"  Min Grade: {course.min_grade}\n"
            f"  SME Contact: {course.sme_contact}\n"
        )
    if result.details:
        prompt += f"Details: {result.details}\n"

    prompt += "\nChallenge message:"

    from config.model_config import VERTEX_AI_MODEL, CHALLENGER_GEN_CONFIG
    response = client.models.generate_content(
        model=VERTEX_AI_MODEL,
        contents=prompt,
        config=CHALLENGER_GEN_CONFIG
    )
    return response.text.strip()


def make_judge_prompt(scenario_context: str, challenge_text: str) -> str:
    """Format the judge prompt per TR-EVAL-004."""
    return f"""You are an impartial evaluator scoring a training-submission challenge message.

SCENARIO CONTEXT:
{scenario_context}     # profile, courses, reasons, priorities – plain text

CHALLENGE TEXT:
{challenge_text}

Score this challenge on four dimensions. Return ONLY a JSON object.

{{
  "justification": <0-3>,
  "tone": <0-3>,
  "scope_adherence": <0-2>,
  "actionability": <0-2>,
  "total": <0-10>,
  "comment": "<one sentence>"
}}

Rubric:
Justification (0-3): 3=cites specific data; 2=directionally correct but vague; 1=plausible but generic; 0=unjustified
Tone (0-3): 3=inquisitive, assumes good intent; 2=appropriate but flat; 1=passive-aggressive or preachy; 0=accusatory
Scope Adherence (0-2): 2=addresses request characteristics only; 1=minor drift; 0=boundary violation
Actionability (0-2): 2=clear next step; 1=unclear path forward; 0=dead end
"""


def parse_judge_scores(response_text: str) -> dict:
    """Extract JSON object from judge response. Matches TR-EVAL-004."""
    match = re.search(r'\{.*\}', response_text, re.DOTALL)
    if not match:
        raise ValueError(f"Judge response contains no JSON: {response_text[:200]}")
    return json.loads(match.group())


def run_judge(client: Any, scenario_context: str, challenge_text: str) -> dict:
    """Runs LLM judge on a fired challenge and validates the output scores."""
    prompt = make_judge_prompt(scenario_context, challenge_text)
    from config.model_config import VERTEX_AI_MODEL, JUDGE_CONFIG
    response = client.models.generate_content(
        model=VERTEX_AI_MODEL,
        contents=prompt,
        config=JUDGE_CONFIG
    )
    scores = parse_judge_scores(response.text.strip())
    # Validate sum of dimensions
    expected_total = (
        scores.get("justification", 0) +
        scores.get("tone", 0) +
        scores.get("scope_adherence", 0) +
        scores.get("actionability", 0)
    )
    if scores.get("total") != expected_total:
        raise ValueError(
            f"Judge total score {scores.get('total')} does not equal sum "
            f"of dimensions {expected_total} in response: {scores}"
        )
    return scores


def make_scenario_context(scenario_data: dict, courses: dict[str, CourseRecord]) -> str:
    """Formats scenario details for the judge context."""
    person = scenario_data["person"]
    basket = scenario_data["basket"]
    lines = []
    lines.append(
        f"Submitter Profile: Grade={person.get('grade')}, "
        f"Role='{person.get('lead_technical_role')}', "
        f"Job Family='{person.get('job_family')}', "
        f"Department='{person.get('department')}', "
        f"Has Direct Reports={person.get('has_direct_reports')}"
    )
    lines.append("Basket Items:")
    for item in basket:
        c_id = item["course_id"]
        c_title = courses[c_id].title if c_id in courses else "Unknown"
        c_cat = courses[c_id].category if c_id in courses else "Unknown"
        lines.append(
            f"  - Course: '{c_title}' ({c_id}) | Category: '{c_cat}' | "
            f"Reason: '{item['reason']}' | Priority: '{item['priority']}'"
        )
    return "\n".join(lines)


def run_evaluation_mode(
    scenario_ids: list[str],
    rules_only: bool,
    courses: dict[str, CourseRecord],
    client: Optional[Any]
) -> tuple[list[dict], dict]:
    """Runs evaluation for specified scenarios in rules-only or full mode."""
    scenarios_results = []
    total_correctness = 0
    max_possible_correctness = 0
    judge_totals = []
    judge_tones = []
    passed_count = 0
    failed_count = 0

    for sid in scenario_ids:
        scenario_path = Path(f"data/scenarios/scenario_{sid}.json")
        if not scenario_path.exists():
            raise FileNotFoundError(f"Scenario file not found: {scenario_path}")

        with open(scenario_path, "r", encoding="utf-8") as f:
            scenario_data = json.load(f)

        # Validate TR-EVAL-002 schema required fields
        required_fields = ["scenario_id", "description", "person", "submission_mode", "basket", "prior_submissions", "ground_truth_challenges"]
        for rf in required_fields:
            if rf not in scenario_data:
                raise ValueError(f"Missing required field '{rf}' in scenario_{sid}.json")

        person_data = scenario_data["person"]
        person_fields = ["person_id", "lead_technical_role", "job_family", "grade", "management_chain", "direct_reports", "has_direct_reports", "department"]
        for pf in person_fields:
            if pf not in person_data:
                raise ValueError(f"Missing required field 'person.{pf}' in scenario_{sid}.json")

        # Run Validators
        fired = run_scenario_validators(scenario_data, courses)

        # Correctness scoring
        score, reasons = score_correctness(fired, scenario_data["ground_truth_challenges"])
        total_correctness += score
        # max possible correctness: clean is 1, challenge is count of truth
        if not scenario_data["ground_truth_challenges"]:
            max_possible_correctness += 1
        else:
            max_possible_correctness += len(scenario_data["ground_truth_challenges"])

        # Process fired challenges and generate texts + quality scoring
        fired_list = []
        scenario_passed = True

        person_profile = get_person_profile(person_data["person_id"], person_data)

        for res in fired:
            # Generate challenge text
            if rules_only:
                text = rules_generate_challenge_text(res, rules_only=True, courses=courses)
                judge_scores = None
            else:
                text = generate_challenge_text_llm(
                    client=client,
                    result=res,
                    courses=courses,
                    person_profile=person_profile,
                    basket=scenario_data["basket"]
                )
                # LLM judge call
                scenario_context = make_scenario_context(scenario_data, courses)
                judge_scores = run_judge(client, scenario_context, text)
                judge_totals.append(judge_scores["total"])
                judge_tones.append(judge_scores["tone"])

                # Check if this specific challenge failed quality criteria
                if judge_scores["total"] < 7 or judge_scores["tone"] < 2:
                    scenario_passed = False

            fired_list.append({
                "type": res.type,
                "course_id": res.course_id,
                "text": text,
                "judge_scores": judge_scores
            })

        # Correctness check for scenario status
        expected_score = len(scenario_data["ground_truth_challenges"]) if scenario_data["ground_truth_challenges"] else 1
        if score < expected_score:
            scenario_passed = False

        if scenario_passed:
            passed_count += 1
        else:
            failed_count += 1

        scenarios_results.append({
            "scenario_id": sid,
            "correctness_score": score,
            "correctness_reasons": reasons,
            "fired_challenges": fired_list,
            "passed": scenario_passed
        })

    summary = {
        "total_correctness": total_correctness,
        "max_possible_correctness": max_possible_correctness,
        "average_judge_total": round(sum(judge_totals) / len(judge_totals), 2) if judge_totals else 0.0,
        "min_judge_tone": min(judge_tones) if judge_tones else 0,
        "scenarios_passed": passed_count,
        "scenarios_failed": failed_count
    }

    return scenarios_results, summary


def main():
    parser = argparse.ArgumentParser(description="trainsight CLI Evaluation Harness")
    parser.add_argument(
        "--scenario",
        required=True,
        choices=["1", "2", "3", "4", "5", "H1", "H2", "H3", "all"],
        help="Scenario ID or 'all' to run all scenarios"
    )
    parser.add_argument(
        "--rules-only",
        action="store_true",
        help="Bypass LLM generation and use rules-only templates"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="JSON file path for output results"
    )

    args = parser.parse_args()

    # Determine scenarios to run
    if args.scenario == "all":
        scenarios_to_run = ["1", "2", "3", "4", "5", "H1", "H2", "H3"]
    else:
        scenarios_to_run = [args.scenario]

    # Initialize client if not rules-only
    client = None
    if not args.rules_only:
        from google import genai
        client = genai.Client(
            vertexai=True,
            project=os.environ["GOOGLE_CLOUD_PROJECT"],
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", os.environ.get("VERTEX_AI_LOCATION", "us-central1"))
        )

    # Load Course records
    courses = load_courses()

    try:
        # Separate tuned and held-out scenarios
        tuned_scenarios = [s for s in scenarios_to_run if s in ["1", "2", "3", "4", "5"]]
        held_out_scenarios = [s for s in scenarios_to_run if s in ["H1", "H2", "H3"]]

        # Run primary evaluation mode
        primary_results = []
        primary_held_out_results = []
        
        if tuned_scenarios:
            primary_results, primary_summary = run_evaluation_mode(
                tuned_scenarios, args.rules_only, courses, client
            )
        else:
            primary_summary = {
                "total_correctness": 0,
                "max_possible_correctness": 0,
                "average_judge_total": 0.0,
                "min_judge_tone": 0,
                "scenarios_passed": 0,
                "scenarios_failed": 0
            }

        if held_out_scenarios:
            primary_held_out_results, primary_held_out_summary = run_evaluation_mode(
                held_out_scenarios, args.rules_only, courses, client
            )
        else:
            primary_held_out_summary = {
                "total_correctness": 0,
                "max_possible_correctness": 0,
                "average_judge_total": 0.0,
                "min_judge_tone": 0,
                "scenarios_passed": 0,
                "scenarios_failed": 0
            }

        # Calculate delta if full run
        delta_data = None
        rules_results = []
        rules_held_out_results = []
        rules_summary = None
        rules_held_out_summary = None

        if not args.rules_only and tuned_scenarios:
            # Run rules-only evaluation internally to calculate delta metrics
            rules_results, rules_summary = run_evaluation_mode(
                tuned_scenarios, True, courses, None
            )
            # Grade these rules-only results using LLM Judge to determine delta
            for sc_res in rules_results:
                sc_id = sc_res["scenario_id"]
                scenario_path = Path(f"data/scenarios/scenario_{sc_id}.json")
                with open(scenario_path, "r", encoding="utf-8") as f:
                    scenario_data = json.load(f)
                person_data = scenario_data["person"]
                person_profile = get_person_profile(person_data["person_id"], person_data)
                scenario_context = make_scenario_context(scenario_data, courses)

                for fc in sc_res["fired_challenges"]:
                    fc["judge_scores"] = run_judge(client, scenario_context, fc["text"])

            # Recompute rules-only averages with judge scores
            r_totals = [fc["judge_scores"]["total"] for sc in rules_results for fc in sc["fired_challenges"] if fc["judge_scores"]]
            r_tones = [fc["judge_scores"]["tone"] for sc in rules_results for fc in sc["fired_challenges"] if fc["judge_scores"]]
            r_justifications = [fc["judge_scores"]["justification"] for sc in rules_results for fc in sc["fired_challenges"] if fc["judge_scores"]]
            r_actionabilities = [fc["judge_scores"]["actionability"] for sc in rules_results for fc in sc["fired_challenges"] if fc["judge_scores"]]

            rules_summary["average_judge_total"] = sum(r_totals) / len(r_totals) if r_totals else 0.0
            rules_summary["min_judge_tone"] = min(r_tones) if r_tones else 0

            # Compute full averages
            f_totals = [fc["judge_scores"]["total"] for sc in primary_results for fc in sc["fired_challenges"] if fc["judge_scores"]]
            f_tones = [fc["judge_scores"]["tone"] for sc in primary_results for fc in sc["fired_challenges"] if fc["judge_scores"]]
            f_justifications = [fc["judge_scores"]["justification"] for sc in primary_results for fc in sc["fired_challenges"] if fc["judge_scores"]]
            f_actionabilities = [fc["judge_scores"]["actionability"] for sc in primary_results for fc in sc["fired_challenges"] if fc["judge_scores"]]

            avg_f_total = sum(f_totals) / len(f_totals) if f_totals else 0.0
            avg_r_total = sum(r_totals) / len(r_totals) if r_totals else 0.0
            avg_f_tone = sum(f_tones) / len(f_tones) if f_tones else 0.0
            avg_r_tone = sum(r_tones) / len(r_tones) if r_tones else 0.0
            avg_f_just = sum(f_justifications) / len(f_justifications) if f_justifications else 0.0
            avg_r_just = sum(r_justifications) / len(r_justifications) if r_justifications else 0.0
            avg_f_act = sum(f_actionabilities) / len(f_actionabilities) if f_actionabilities else 0.0
            avg_r_act = sum(r_actionabilities) / len(r_actionabilities) if r_actionabilities else 0.0

            delta_data = {
                "correctness_delta": primary_summary["total_correctness"] - rules_summary["total_correctness"],
                "avg_tone_delta": round(avg_f_tone - avg_r_tone, 2),
                "avg_justification_delta": round(avg_f_just - avg_r_just, 2),
                "avg_actionability_delta": round(avg_f_act - avg_r_act, 2),
            }

        # Structure JSON output
        output_json = {
            "run_id": datetime.now(timezone.utc).isoformat(),
            "mode": "rules_only" if args.rules_only else "full",
            "scenarios": primary_results,
            "held_out_scenarios": primary_held_out_results if held_out_scenarios else [],
            "summary": {
                "total_correctness": primary_summary["total_correctness"],
                "max_possible_correctness": primary_summary["max_possible_correctness"],
                "average_judge_total": primary_summary["average_judge_total"],
                "min_judge_tone": primary_summary["min_judge_tone"],
                "scenarios_passed": primary_summary["scenarios_passed"],
                "scenarios_failed": primary_summary["scenarios_failed"]
            },
            "held_out_summary": {
                "total_correctness": primary_held_out_summary["total_correctness"],
                "max_possible_correctness": primary_held_out_summary["max_possible_correctness"],
                "average_judge_total": primary_held_out_summary["average_judge_total"],
                "min_judge_tone": primary_held_out_summary["min_judge_tone"],
                "scenarios_passed": primary_held_out_summary["scenarios_passed"],
                "scenarios_failed": primary_held_out_summary["scenarios_failed"]
            } if held_out_scenarios else None
        }

        if delta_data is not None:
            output_json["delta"] = delta_data

        # Ensure output directory exists
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output_json, f, indent=2)

        # Generate Markdown Summary File
        md_path = out_path.parent / (out_path.stem + ".md")
        
        md_lines = []
        md_lines.append("# trainsight Evaluation Summary Report")
        md_lines.append(f"- **Run ID**: `{output_json['run_id']}`")
        md_lines.append(f"- **Evaluation Mode**: `{output_json['mode']}`")
        md_lines.append(f"- **Timestamp**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        md_lines.append("")

        # Section 2: Per-tuned-scenario table
        if tuned_scenarios:
            md_lines.append("## Tuned Scenarios Results")
            md_lines.append("| Scenario | Description | Correctness Score | Challenges Fired | Avg Judge Score | Status |")
            md_lines.append("|---|---|---|---|---|---|")
            for sc in primary_results:
                sc_id = sc["scenario_id"]
                scenario_path = Path(f"data/scenarios/scenario_{sc_id}.json")
                with open(scenario_path, "r", encoding="utf-8") as sf:
                    desc = json.load(sf).get("description", "")
                
                fired_count = len(sc["fired_challenges"])
                scores = [fc["judge_scores"]["total"] for fc in sc["fired_challenges"] if fc.get("judge_scores")]
                avg_score = round(sum(scores) / len(scores), 2) if scores else "N/A"
                status = "PASS" if sc["passed"] else "FAIL"
                md_lines.append(f"| {sc_id} | {desc} | {sc['correctness_score']} | {fired_count} | {avg_score} | {status} |")
            md_lines.append("")

            # Section 3: Overall tuned summary
            md_lines.append("## Overall Tuned Summary Metrics")
            md_lines.append(f"- **Total Correctness**: {primary_summary['total_correctness']} / {primary_summary['max_possible_correctness']}")
            md_lines.append(f"- **Scenarios Passed**: {primary_summary['scenarios_passed']}")
            md_lines.append(f"- **Scenarios Failed**: {primary_summary['scenarios_failed']}")
            if not args.rules_only:
                md_lines.append(f"- **Average LLM Judge Quality Score**: {primary_summary['average_judge_total']} / 10")
                md_lines.append(f"- **Minimum Judge Tone Score**: {primary_summary['min_judge_tone']} / 3")
            md_lines.append("")

        # Section 4: Delta comparison section
        if delta_data is not None:
            md_lines.append("## Rules-Only vs Full Mode Delta Comparison")
            md_lines.append("| Metric | Rules-Only (Baseline) | Full Mode (LLM) | Delta |")
            md_lines.append("|---|---|---|---|")
            md_lines.append(f"| Correctness Score | {rules_summary['total_correctness']} | {primary_summary['total_correctness']} | {delta_data['correctness_delta']} |")
            md_lines.append(f"| Avg Judge Total | {rules_summary['average_judge_total']:.2f} | {primary_summary['average_judge_total']:.2f} | {delta_data['avg_tone_delta'] + delta_data['avg_justification_delta']:.2f} |")
            md_lines.append(f"| Avg Tone | {avg_r_tone:.2f} | {avg_f_tone:.2f} | {delta_data['avg_tone_delta']} |")
            md_lines.append(f"| Avg Justification | {avg_r_just:.2f} | {avg_f_just:.2f} | {delta_data['avg_justification_delta']} |")
            md_lines.append(f"| Avg Actionability | {avg_r_act:.2f} | {avg_f_act:.2f} | {delta_data['avg_actionability_delta']} |")
            md_lines.append("")

        # Held-out scenarios section
        if held_out_scenarios:
            md_lines.append("# HELD-OUT SCENARIOS — DO NOT USE TO ADJUST PROMPTS")
            md_lines.append("")
            md_lines.append("| Scenario | Description | Correctness Score | Challenges Fired | Avg Judge Score | Status |")
            md_lines.append("|---|---|---|---|---|---|")
            for sc in primary_held_out_results:
                sc_id = sc["scenario_id"]
                scenario_path = Path(f"data/scenarios/scenario_{sc_id}.json")
                with open(scenario_path, "r", encoding="utf-8") as sf:
                    desc = json.load(sf).get("description", "")
                fired_count = len(sc["fired_challenges"])
                scores = [fc["judge_scores"]["total"] for fc in sc["fired_challenges"] if fc.get("judge_scores")]
                avg_score = round(sum(scores) / len(scores), 2) if scores else "N/A"
                status = "PASS" if sc["passed"] else "FAIL"
                md_lines.append(f"| {sc_id} | {desc} | {sc['correctness_score']} | {fired_count} | {avg_score} | {status} |")
            md_lines.append("")
            md_lines.append("### Held-Out Summary Metrics")
            md_lines.append(f"- **Total Correctness**: {primary_held_out_summary['total_correctness']} / {primary_held_out_summary['max_possible_correctness']}")
            md_lines.append(f"- **Scenarios Passed**: {primary_held_out_summary['scenarios_passed']}")
            md_lines.append(f"- **Scenarios Failed**: {primary_held_out_summary['scenarios_failed']}")
            if not args.rules_only:
                md_lines.append(f"- **Average LLM Judge Quality Score**: {primary_held_out_summary['average_judge_total']} / 10")
                md_lines.append(f"- **Minimum Judge Tone Score**: {primary_held_out_summary['min_judge_tone']} / 3")
            md_lines.append("")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

        print(f"Evaluation complete. Results written to {out_path} and summary report written to {md_path}")
        sys.exit(0)

    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
