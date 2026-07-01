"""FastAPI application for trainsight web service."""

import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pathlib import Path

from fastapi import FastAPI, Request, HTTPException, Depends, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware
from dataclasses import asdict

# 1. Import startup validation first to check environment
import src.startup

# 2. Project imports
from src.models import (
    PersonProfile,
    CourseRecord,
    BasketItem,
    SubmissionRecord,
    AuditLogEntry,
    HITLToken,
    ChallengeResult,
    CoherenceInput
)
from src.security import (
    write_audit_entry,
    _sanitise,
    _assert_no_pii,
    _token_store,
    issue_token,
    validate_and_consume_token,
    _INJECTION_PATTERNS
)
from src.validators import (
    check_role_fit,
    check_priority_inflation,
    detect_duplicates,
    check_reason_coherence,
    check_quantity,
    compute_team_size,
    generate_challenge_text
)
from src.skills.fetch import (
    fetch_profile,
    lookup_courses,
    fetch_prior_submissions,
    submit_request
)
from src.mcp.catalogue_server import get_courses
from src.mcp.workday_server import get_profile

from google.adk.sessions import VertexAiSessionService
from google import genai
from google.genai import types
from config.model_config import VERTEX_AI_MODEL

# 3. Environment setup
CHALLENGER_AGENT_RUNTIME_ID = os.environ["CHALLENGER_AGENT_RUNTIME_ID"]
GOOGLE_CLOUD_PROJECT = os.environ["GOOGLE_CLOUD_PROJECT"]
VERTEX_AI_LOCATION = os.environ.get("VERTEX_AI_LOCATION", "us-central1")

# Instantiate remote session service
session_service = VertexAiSessionService(
    project=GOOGLE_CLOUD_PROJECT,
    location=VERTEX_AI_LOCATION,
    agent_engine_id=CHALLENGER_AGENT_RUNTIME_ID
)

# 4. FastAPI Setup
app = FastAPI(title="trainsight-web", version="1.0.0")

app.add_middleware(
    SessionMiddleware,
    # Fallback string exists only so the app boots without a .env for local smoke-testing;
    # deploy_web.sh always generates and injects a real SESSION_SECRET_KEY before deploy
    # (see deploy_web.sh), so the hardcoded value below is never the one used in Cloud Run.
    secret_key=os.environ.get("SESSION_SECRET_KEY", "trainsight-secret-key-12345")
)

# 5. Pydantic Models for API
class ProfileRequest(BaseModel):
    email: str

class DirectReportInfo(BaseModel):
    workday_id: str
    lead_technical_role: str
    grade: str

class ProfileResponse(BaseModel):
    person_id: str
    lead_technical_role: str
    job_family: str
    grade: str
    has_direct_reports: bool
    department: str
    direct_reports: Optional[List[DirectReportInfo]] = None

class ModeRequest(BaseModel):
    submission_mode: str

class BasketItemRequest(BaseModel):
    person_id: Optional[str] = None
    course_id: str
    reason: str
    priority: str

class Totals(BaseModel):
    total_cost: float
    total_ts: float
    grand_total: float

class ChallengeInfo(BaseModel):
    challenge_id: str
    course_id: str
    type: str
    text: str

class BasketResponse(BaseModel):
    items: List[Dict[str, Any]]
    challenges: List[ChallengeInfo]
    totals: Totals
    basket_overrides: Optional[Dict[str, str]] = None

class ChallengeRespondRequest(BaseModel):
    message: str

class ChallengeRespondResponse(BaseModel):
    reply: str
    updated_challenges: List[ChallengeInfo]

class ChallengeOverrideRequest(BaseModel):
    challenge_id: str
    justification: str

class SubmitConfirmResponse(BaseModel):
    items: List[Dict[str, Any]]
    totals: Totals
    hitl_token: str
    data_statement: str
    resolved_challenge_count: int
    unresolved_challenge_count: int

class SubmitExecuteRequest(BaseModel):
    hitl_token: str

class SubmitExecuteResponse(BaseModel):
    reference: str
    message: str

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str

# 6. Session & Security helpers
def get_session_info(request: Request) -> Dict[str, Any]:
    session_id = request.session.get("agent_session_id")
    person_id = request.session.get("person_id")
    email = request.session.get("email")
    if not session_id or not person_id or not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session not found or expired. Please authenticate via POST /api/profile."
        )
    return {
        "agent_session_id": session_id,
        "person_id": person_id,
        "email": email,
        "submission_mode": request.session.get("submission_mode", "self")
    }

async def run_basket_evaluation(request: Request, basket: List[Dict[str, Any]], session_info: Dict[str, Any]) -> BasketResponse:
    # 1. Convert basket dicts to BasketItem models
    basket_items = [
        BasketItem(
            person_id=item["person_id"],
            course_id=item["course_id"],
            reason=item["reason"],
            priority=item["priority"],
            challenge_types_fired=item.get("challenge_types_fired", []),
            override_justification=item.get("override_justification")
        )
        for item in basket
    ]

    # 2. Pre-fetch CourseRecords for all courses in basket
    course_ids = list({item.course_id for item in basket_items})
    courses_dict = {}
    if course_ids:
        try:
            records = lookup_courses(course_ids=course_ids)
            courses_dict = {c.course_id: c for c in records}
        except Exception:
            pass

    # 3. Pre-fetch prior submissions for duplicate checks
    person_ids = list({item.person_id for item in basket_items})
    prior_subs = []
    for pid in person_ids:
        try:
            prior_subs.extend(fetch_prior_submissions(person_id=pid))
        except Exception:
            pass

    challenges: List[ChallengeInfo] = []

    # Run in-process validators:
    # A. Duplicate check
    dup_results = detect_duplicates(basket_items, prior_subs)
    for res in dup_results:
        text = generate_challenge_text(res, rules_only=True, courses=courses_dict)
        challenges.append(ChallengeInfo(
            challenge_id=f"duplicate:{res.course_id}",
            course_id=res.course_id,
            type="duplicate",
            text=text
        ))

    # B. Role fit check
    for item in basket_items:
        course = courses_dict.get(item.course_id)
        if not course:
            continue
        try:
            target_profile = get_profile(workday_id=item.person_id)
            res_rf = check_role_fit(target_profile, course)
            if res_rf:
                text = generate_challenge_text(res_rf, rules_only=True, courses=courses_dict)
                challenges.append(ChallengeInfo(
                    challenge_id=f"role_fit:{item.course_id}",
                    course_id=item.course_id,
                    type="role_fit",
                    text=text
                ))
        except Exception:
            pass

    # C. Priority inflation check
    res_pi = check_priority_inflation(basket_items)
    if res_pi:
        text = generate_challenge_text(res_pi, rules_only=True, courses=courses_dict)
        challenges.append(ChallengeInfo(
            challenge_id="priority_inflation:basket",
            course_id="basket",
            type="priority_inflation",
            text=text
        ))

    # D. Quantity check (only in Line Manager mode)
    if session_info["submission_mode"] == "lm":
        team_size = compute_team_size(basket_items)
        res_q = check_quantity(basket_items, team_size)
        if res_q:
            text = generate_challenge_text(res_q, rules_only=True, courses=courses_dict)
            challenges.append(ChallengeInfo(
                challenge_id="quantity:basket",
                course_id="basket",
                type="quantity",
                text=text
            ))

    # E. Reason coherence (pre-filter + direct in-process Gemini call)
    coherence_cache = request.session.setdefault("coherence_cache", {})
    for item in basket_items:
        course = courses_dict.get(item.course_id)
        if not course:
            continue
        coherence_input = check_reason_coherence(item, course)
        if coherence_input:
            cache_key = f"{item.course_id}:{item.reason}"
            if cache_key in coherence_cache:
                challenge_text = coherence_cache[cache_key]
            else:
                try:
                    client = genai.Client()
                    prompt = (
                        "You are the Training Submission Challenger, an AI assistant review tool.\n"
                        f"Review this course selection:\n"
                        f"Course: {coherence_input.course_title} (Category: {coherence_input.course_category})\n"
                        f"Description: {coherence_input.course_description_sanitised}\n"
                        f"Reason Given: {coherence_input.reason_given}\n\n"
                        "The reason 'Critical/Scarce Skill' is typically reserved for genuine operational gaps, "
                        "but this course is categorized under professional development. Please raise a challenge "
                        "question. Ask the user in a polite, professional, and inquisitive tone to explain why this "
                        "course is critical for their role. Do not output anything else, only the challenge question text."
                    )
                    response = client.models.generate_content(
                        model=VERTEX_AI_MODEL,
                        contents=prompt,
                        config=types.GenerateContentConfig(temperature=0.2)
                    )
                    challenge_text = response.text.strip()
                    coherence_cache[cache_key] = challenge_text
                except Exception:
                    challenge_text = (
                        f"Reason coherence: '{course.title}' is categorised as '{course.category}', "
                        "which is a professional development course. The reason 'Critical/Scarce Skill' "
                        "is typically reserved for genuine operational gaps. Can you confirm why this classification applies?"
                    )
            challenges.append(ChallengeInfo(
                challenge_id=f"reason_coherence:{item.course_id}",
                course_id=item.course_id,
                type="reason_coherence",
                text=challenge_text
            ))

    request.session["coherence_cache"] = coherence_cache

    # 4. Calculate cost totals
    total_cost = 0.0
    total_ts = 0.0
    for item in basket_items:
        course = courses_dict.get(item.course_id)
        if course:
            total_cost += course.cost_per_person
            total_ts += course.ts_cost

    return BasketResponse(
        items=basket,
        challenges=challenges,
        totals=Totals(
            total_cost=total_cost,
            total_ts=total_ts,
            grand_total=total_cost + total_ts
        ),
        basket_overrides=request.session.get("basket_overrides", {})
    )

# 7. Endpoint Implementations
@app.post("/api/profile", response_model=ProfileResponse)
async def post_profile(body: ProfileRequest, request: Request):
    if os.environ.get("SUBMISSION_WINDOW_OPEN", "true").lower() == "false":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WINDOW_CLOSED"
        )
        
    try:
        profile = fetch_profile(email=body.email)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PROFILE_NOT_FOUND"
        )

    try:
        # Create remote Agent Runtime session
        session = await session_service.create_session(
            app_name="app",
            user_id=body.email
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create Agent Runtime session: {exc}"
        )

    # Store state keys server-side in Starlette session cookie
    request.session["profile"] = asdict(profile)
    request.session["basket"] = []
    request.session["submission_mode"] = "lm" if profile.has_direct_reports else "self"
    request.session["agent_session_id"] = session.id
    request.session["person_id"] = profile.person_id
    request.session["email"] = body.email
    request.session["basket_overrides"] = {}
    request.session["coherence_cache"] = {}

    direct_reports_list = []
    if profile.has_direct_reports:
        for dr_id in profile.direct_reports:
            try:
                dr_profile = get_profile(workday_id=dr_id)
                direct_reports_list.append(DirectReportInfo(
                    workday_id=dr_profile.person_id,
                    lead_technical_role=dr_profile.lead_technical_role,
                    grade=dr_profile.grade
                ))
            except Exception:
                pass

    return ProfileResponse(
        person_id=profile.person_id,
        lead_technical_role=profile.lead_technical_role,
        job_family=profile.job_family,
        grade=profile.grade,
        has_direct_reports=profile.has_direct_reports,
        department=profile.department,
        direct_reports=direct_reports_list or None
    )

@app.get("/api/catalogue", response_model=List[CourseRecord])
async def get_catalogue():
    return get_courses()

@app.post("/api/session/basket", response_model=BasketResponse)
async def post_basket(body: BasketItemRequest, request: Request, session_info: Dict[str, Any] = Depends(get_session_info)):
    basket = request.session.setdefault("basket", [])
    
    # Verify course exists
    try:
        courses = get_courses(course_id=body.course_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="COURSE_NOT_FOUND"
        )
        
    target_person_id = body.person_id or session_info["person_id"]
    
    # Update item if duplicate in current basket, otherwise append
    existing_item = next(
        (i for i in basket if i["person_id"] == target_person_id and i["course_id"] == body.course_id),
        None
    )
    if existing_item:
        existing_item["reason"] = body.reason
        existing_item["priority"] = body.priority
        existing_item["override_justification"] = None
    else:
        basket.append({
            "person_id": target_person_id,
            "course_id": body.course_id,
            "reason": body.reason,
            "priority": body.priority,
            "challenge_types_fired": [],
            "override_justification": None
        })
        
    request.session["basket"] = basket
    
    return await run_basket_evaluation(request, basket, session_info)

@app.post("/api/session/mode", response_model=BasketResponse)
async def post_session_mode(body: ModeRequest, request: Request, session_info: Dict[str, Any] = Depends(get_session_info)):
    mode = body.submission_mode
    if mode not in ("self", "lm"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid submission mode"
        )
    request.session["submission_mode"] = mode
    basket = request.session.get("basket", [])
    session_info_copy = dict(session_info)
    session_info_copy["submission_mode"] = mode
    return await run_basket_evaluation(request, basket, session_info_copy)

@app.get("/api/session/basket", response_model=BasketResponse)
async def get_basket(request: Request, session_info: Dict[str, Any] = Depends(get_session_info)):
    basket = request.session.get("basket", [])
    return await run_basket_evaluation(request, basket, session_info)

@app.delete("/api/session/basket/{course_id}", response_model=BasketResponse)
async def delete_basket(course_id: str, person_id: str, request: Request, session_info: Dict[str, Any] = Depends(get_session_info)):
    basket = request.session.get("basket", [])
    
    # Filter out target course for target person
    new_basket = [
        item for item in basket
        if not (item["course_id"] == course_id and item["person_id"] == person_id)
    ]
    request.session["basket"] = new_basket
    
    # Remove from coherence cache if present
    coherence_cache = request.session.get("coherence_cache", {})
    keys_to_remove = [k for k in coherence_cache.keys() if k.startswith(f"{course_id}:")]
    for k in keys_to_remove:
        coherence_cache.pop(k, None)
    request.session["coherence_cache"] = coherence_cache

    return await run_basket_evaluation(request, new_basket, session_info)

@app.post("/api/session/challenge/respond", response_model=ChallengeRespondResponse)
async def challenge_respond(body: ChallengeRespondRequest, request: Request, session_info: Dict[str, Any] = Depends(get_session_info)):
    message = body.message
    if not message or len(message) > 2000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid message content or length"
        )

    person_id = session_info["person_id"]
    agent_session_id = session_info["agent_session_id"]

    # 1. Audit user_response_received FIRST (always, prior to injection checks)
    write_audit_entry(AuditLogEntry(
        timestamp=datetime.now(timezone.utc).isoformat(),
        event_type="user_response_received",
        agent_name="submission_challenger",
        person_id=person_id,
        detail=message
    ))

    # 2. Check for Prompt Injection
    is_injection = any(pattern.search(message) for pattern in _INJECTION_PATTERNS)
    if is_injection:
        write_audit_entry(AuditLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type="injection_attempt_detected",
            agent_name="submission_challenger",
            person_id=person_id,
            detail=message[:200]
        ))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="INJECTION_DETECTED"
        )

    # 3. Forward clean message to Agent Runtime Session
    from vertexai.preview.reasoning_engines import ReasoningEngine
    try:
        remote_app = ReasoningEngine(CHALLENGER_AGENT_RUNTIME_ID)
        reply_text = ""
        async for event in remote_app.async_stream_query(
            message=message,
            user_id=person_id,
            session_id=agent_session_id
        ):
            content = event.get("content")
            if content:
                parts = content.get("parts")
                if parts:
                    for part in parts:
                        if "text" in part:
                            reply_text += part["text"]
        reply_text = reply_text.strip()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent interaction failed: {exc}"
        )

    # 4. Audit challenge_issued for the agent's reply
    write_audit_entry(AuditLogEntry(
        timestamp=datetime.now(timezone.utc).isoformat(),
        event_type="challenge_issued",
        agent_name="submission_challenger",
        person_id=person_id,
        detail=reply_text
    ))

    # 5. Re-evaluate basket and return response
    basket = request.session.get("basket", [])
    basket_resp = await run_basket_evaluation(request, basket, session_info)

    return ChallengeRespondResponse(
        reply=reply_text,
        updated_challenges=basket_resp.challenges
    )

@app.post("/api/session/challenge/override")
async def challenge_override(body: ChallengeOverrideRequest, request: Request, session_info: Dict[str, Any] = Depends(get_session_info)):
    if not body.justification or not body.justification.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="EMPTY_JUSTIFICATION"
        )

    challenge_id = body.challenge_id
    if ":" not in challenge_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid challenge_id format"
        )

    challenge_type, course_id = challenge_id.split(":", 1)
    person_id = session_info["person_id"]

    # Write override_accepted audit entry
    write_audit_entry(AuditLogEntry(
        timestamp=datetime.now(timezone.utc).isoformat(),
        event_type="override_accepted",
        agent_name="submission_challenger",
        person_id=person_id,
        course_ids=[course_id],
        challenge_type=challenge_type,
        justification=body.justification
    ))

    # Store override server-side
    if course_id == "basket":
        overrides = request.session.setdefault("basket_overrides", {})
        overrides[challenge_type] = body.justification
        request.session["basket_overrides"] = overrides
    else:
        basket = request.session.get("basket", [])
        updated = False
        for item in basket:
            if item["course_id"] == course_id:
                item["override_justification"] = body.justification
                if challenge_type not in item.setdefault("challenge_types_fired", []):
                    item["challenge_types_fired"].append(challenge_type)
                updated = True
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course item not found in basket"
            )
        request.session["basket"] = basket

    return {"message": "Override accepted"}

@app.post("/api/session/submit/confirm", response_model=SubmitConfirmResponse)
async def submit_confirm(request: Request, session_info: Dict[str, Any] = Depends(get_session_info)):
    # HITL is a two-request flow, not a single call: this endpoint only re-evaluates the
    # basket, issues a token, and shows the review screen — it performs no write. The token
    # from here must be echoed back to /submit/execute below, where it's consumed and the
    # actual submissions-mcp write happens. A user who never clicks "confirm" on the review
    # screen never reaches a write path.
    basket = request.session.get("basket", [])
    if not basket:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Basket is empty"
        )

    # 1. Run evaluation to fetch current challenges and totals
    basket_resp = await run_basket_evaluation(request, basket, session_info)

    # 2. Build BasketItem list mapping challenges fired and overrides
    basket_items: List[BasketItem] = []
    basket_overrides = request.session.get("basket_overrides", {})
    for item in basket:
        fired = []
        for c in basket_resp.challenges:
            if c.course_id == item["course_id"]:
                fired.append(c.type)
            elif c.course_id == "basket":
                fired.append(c.type)
        fired = list(set(fired))

        override_justification = item.get("override_justification")
        if not override_justification:
            for c_type in fired:
                if c_type in ("priority_inflation", "quantity"):
                    b_override = basket_overrides.get(c_type)
                    if b_override:
                        override_justification = b_override
                        break

        basket_items.append(BasketItem(
            person_id=item["person_id"],
            course_id=item["course_id"],
            reason=item["reason"],
            priority=item["priority"],
            challenge_types_fired=fired,
            override_justification=override_justification
        ))

    # 3. Issue HITLToken
    token_obj = issue_token(
        session_id=session_info["agent_session_id"],
        basket=basket_items
    )

    # 4. Log submit_confirm_clicked audit entry
    write_audit_entry(AuditLogEntry(
        timestamp=datetime.now(timezone.utc).isoformat(),
        event_type="submit_confirm_clicked",
        agent_name="submission_challenger",
        person_id=session_info["person_id"],
        course_ids=[item.course_id for item in basket_items]
    ))

    # 5. Count resolved / unresolved challenges
    resolved_count = 0
    unresolved_count = 0
    for c in basket_resp.challenges:
        if c.course_id == "basket":
            if c.type in basket_overrides:
                resolved_count += 1
            else:
                unresolved_count += 1
        else:
            item_data = next((i for i in basket if i["course_id"] == c.course_id), None)
            if item_data and item_data.get("override_justification"):
                resolved_count += 1
            else:
                unresolved_count += 1

    data_statement = (
        "Your complete data boundary is three sources: the training catalogue (course details and target roles), "
        "the submitter's Workday profile (Lead Technical Role, Job Family, grade, management chain position — nothing else), "
        "and the submissions store (prior submission records for duplicate detection). You have no access to training history, "
        "performance records, HR records, or any other data source."
    )

    return SubmitConfirmResponse(
        items=[asdict(i) for i in basket_items],
        totals=basket_resp.totals,
        hitl_token=token_obj.token,
        data_statement=data_statement,
        resolved_challenge_count=resolved_count,
        unresolved_challenge_count=unresolved_count
    )

@app.post("/api/session/submit/execute", response_model=SubmitExecuteResponse)
async def submit_execute(body: SubmitExecuteRequest, request: Request, session_info: Dict[str, Any] = Depends(get_session_info)):
    basket = request.session.get("basket", [])
    if not basket:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Basket is empty"
        )

    # 1. Retrieve the token from store first (validates existence)
    # _token_store (src/security.py) is a plain in-process dict, not backed by Redis/DB.
    # This is why deploy_web.sh pins Cloud Run to min-instances=1, max-instances=2: a token
    # issued by /submit/confirm on one instance must be readable here on the same instance,
    # so this endpoint can't scale across multiple cold instances without losing tokens.
    token_obj = _token_store.get(body.hitl_token)
    if not token_obj:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid HITL token"
        )

    # 2. Re-evaluate basket to build BasketItem list for submission
    basket_resp = await run_basket_evaluation(request, basket, session_info)

    basket_items: List[BasketItem] = []
    basket_overrides = request.session.get("basket_overrides", {})
    for item in basket:
        fired = []
        for c in basket_resp.challenges:
            if c.course_id == item["course_id"]:
                fired.append(c.type)
            elif c.course_id == "basket":
                fired.append(c.type)
        fired = list(set(fired))

        override_justification = item.get("override_justification")
        if not override_justification:
            for c_type in fired:
                if c_type in ("priority_inflation", "quantity"):
                    b_override = basket_overrides.get(c_type)
                    if b_override:
                        override_justification = b_override
                        break

        basket_items.append(BasketItem(
            person_id=item["person_id"],
            course_id=item["course_id"],
            reason=item["reason"],
            priority=item["priority"],
            challenge_types_fired=fired,
            override_justification=override_justification
        ))

    # 3. Retrieve user PersonProfile
    try:
        profile = fetch_profile(email=session_info["email"])
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Profile retrieval failed: {exc}"
        )

    # 4. Submit via submit_request (in-process)
    # This automatically calls validate_and_consume_token and writes to submissions-mcp
    try:
        result = submit_request(
            basket=basket_items,
            hitl_token=token_obj,
            profile=profile
        )

        # Clear session basket, overrides and coherence cache on success
        request.session["basket"] = []
        request.session["basket_overrides"] = {}
        request.session["coherence_cache"] = {}

        return SubmitExecuteResponse(
            reference=result.submission_id,
            message="Submission successful"
        )
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err)
        )
    except Exception as exc:
        # No submissions-mcp write occurs on this path — submit_request (src/skills/fetch.py)
        # validates the token and writes the audit failure entry before attempting the MCP
        # call, so a zero-records-written outcome always still leaves an audit trail.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Submission failed: {exc}"
        )

@app.get("/api/health", response_model=HealthResponse)
async def get_health():
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc).isoformat(),
        version="1.0.0"
    )

# 8. Static Files Mounting (last route so it does not shadow API endpoints)
static_dir = Path("static")
static_dir.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
