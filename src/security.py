import secrets
import hashlib
import json
import re
import os
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dataclasses import asdict
from typing import Optional

from src.models import HITLToken, AuditLogEntry, BasketItem, PersonProfile

# 1. Prompt Injection Sanitisation
_INJECTION_PATTERNS = [
    re.compile(r'ignore\s+previous\s+instructions', re.IGNORECASE),
    re.compile(r'you\s+are\s+now', re.IGNORECASE),
    re.compile(r'new\s+instructions:', re.IGNORECASE),
    re.compile(r'act\s+as', re.IGNORECASE),
    re.compile(r'pretend\s+you\s+are', re.IGNORECASE),
    re.compile(r'system\s+prompt:', re.IGNORECASE),
    re.compile(r'from\s+now\s+on', re.IGNORECASE),
    re.compile(r'disregard', re.IGNORECASE),
    re.compile(r'<s>|</s>', re.IGNORECASE),
    re.compile(r'\[INST\]|\[/INST\]', re.IGNORECASE),
]

def _sanitise(text: str) -> str:
    """Replaces injection patterns with [content removed]."""
    for pattern in _INJECTION_PATTERNS:
        text = pattern.sub("[content removed]", text)
    return text

# 2. Basket Hash Computation
def _compute_basket_hash(basket: list[BasketItem]) -> str:
    """Computes SHA-256 of sorted canonical JSON of the basket items."""
    canonical = sorted(
        [asdict(item) for item in basket],
        key=lambda x: (x["person_id"], x["course_id"])
    )
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()

# 3. HITL Token Store and Issuance
_token_store: dict[str, HITLToken] = {}
TOKEN_TTL_SECONDS = 600

def issue_token(session_id: str, basket: list[BasketItem]) -> HITLToken:
    """Issues a session-scoped HITLToken valid for 10 minutes."""
    token_str = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    tok = HITLToken(
        token=token_str,
        session_id=session_id,
        basket_hash=_compute_basket_hash(basket),
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(seconds=TOKEN_TTL_SECONDS)).isoformat(),
        used=False,
    )
    _token_store[token_str] = tok
    return tok

# 4. HITL Token Validation and Consumption
def validate_and_consume_token(
    token_str: str,
    session_id: str,
    basket: list[BasketItem],
) -> HITLToken:
    """
    Validates and marks the token as used before returning.
    Raises ValueError with descriptive message on any validation failure.
    """
    tok = _token_store.get(token_str)
    if tok is None:
        raise ValueError("Token not found")
    if tok.used:
        raise ValueError("Token already used")
    if tok.session_id != session_id:
        raise ValueError("Session mismatch")
    
    now = datetime.now(timezone.utc)
    if now > datetime.fromisoformat(tok.expires_at):
        raise ValueError("Token expired")
        
    if _compute_basket_hash(basket) != tok.basket_hash:
        raise ValueError("Basket contents changed since confirmation")
        
    tok.used = True
    return tok

# 5. PII Guard for PersonProfile
_FORBIDDEN_PROFILE_ATTRS = {"age_band", "name", "email"}

def _assert_no_pii(profile: PersonProfile, person_id: Optional[str] = None) -> None:
    """Raises AttributeError if PersonProfile has any forbidden field, logging beforehand."""
    violations = []
    for attr in _FORBIDDEN_PROFILE_ATTRS:
        if hasattr(profile, attr):
            violations.append(attr)
            
    profile_dict = asdict(profile)
    for key in _FORBIDDEN_PROFILE_ATTRS:
        if key in profile_dict:
            violations.append(key)
            
    if violations:
        unique_violations = sorted(list(set(violations)))
        detail_str = ", ".join(unique_violations)
        pid = person_id or getattr(profile, "person_id", None)
        
        write_audit_entry(AuditLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type="pii_guard_triggered",
            agent_name="submission_challenger",
            person_id=pid,
            detail=detail_str,
        ))
        
        raise AttributeError(
            f"PersonProfile contains forbidden field(s): {unique_violations}. "
            "PII scrub failed – submission aborted."
        )

# 6. PII Guard for Free Text
_EMAIL_PII_PATTERN = re.compile(
    r'\b[A-Za-z0-9._%+-]+@(?!company\.example\.com)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b',
    re.IGNORECASE
)
_JSON_PII_PATTERN = re.compile(r'"(name|email|age_band)"\s*:', re.IGNORECASE)

def _pii_guard(text: str) -> str:
    """Scans free text for PII leakage in non-structural paths and redacts it."""
    has_match = False
    
    # Check for PII presence
    if _EMAIL_PII_PATTERN.search(text) or _JSON_PII_PATTERN.search(text):
        has_match = True
        
    if has_match:
        write_audit_entry(AuditLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type="pii_guard_triggered",
            agent_name="submission_challenger",
            detail="Redacted PII match in free text",
        ))
        text = _EMAIL_PII_PATTERN.sub("[REDACTED]", text)
        text = _JSON_PII_PATTERN.sub('"[REDACTED]":', text)
        
    return text

# 7. Audit Log Writer
AUDIT_LOG_PATH = Path(os.environ.get("AUDIT_LOG_PATH", "data/audit.log"))
_audit_lock = threading.Lock()

def write_audit_entry(entry: AuditLogEntry) -> None:
    """Append one JSON line to the audit log. Thread-safe for single-process use."""
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(asdict(entry), ensure_ascii=False) + "\n"
    with _audit_lock:
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)


if __name__ == "__main__":
    print("Running security.py self-checks...")
    
    # Test token creation and validation
    basket = [
        BasketItem(
            person_id="WD-001234",
            course_id="MEWP-001",
            reason="Capability Gap",
            priority="Medium",
            challenge_types_fired=[]
        )
    ]
    
    session_id = "test-session-123"
    token = issue_token(session_id, basket)
    assert token.token in _token_store
    assert not token.used
    
    # Validation passes
    validated = validate_and_consume_token(token.token, session_id, basket)
    assert validated.used
    
    # Second validation raises ValueError
    try:
        validate_and_consume_token(token.token, session_id, basket)
        raise AssertionError("Expected ValueError for already used token")
    except ValueError as e:
        print(f"Token reuse check passed: {e}")
        
    # Test _pii_guard redaction
    external_email = "test.user@gmail.com"
    internal_email = "john.doe@company.example.com"
    
    redacted_ext = _pii_guard(f"My email is {external_email}")
    assert "[REDACTED]" in redacted_ext
    assert external_email not in redacted_ext
    print("External email redaction check passed.")
    
    unchanged_int = _pii_guard(f"My email is {internal_email}")
    assert internal_email in unchanged_int
    assert "[REDACTED]" not in unchanged_int
    print("Internal email bypass check passed.")
    
    # Test JSON PII check
    json_text = '{"name": "John", "role": "Operator"}'
    redacted_json = _pii_guard(json_text)
    assert '"[REDACTED]":' in redacted_json
    assert '"name":' not in redacted_json
    print("JSON PII redaction check passed.")
    
    print("All security module self-checks passed!")
