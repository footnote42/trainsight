import json
import sys
from pathlib import Path
from typing import Optional

# Add workspace root to sys.path to allow running as a direct script
sys.path.append(str(Path(__file__).parent.parent.parent.resolve()))

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError as FastMCPToolError
from src.models import CourseRecord

# Define custom ToolError class to support the requested signature (code and message as keywords)
class ToolError(FastMCPToolError):
    def __init__(self, message: str = "", code: str = ""):
        self.code = code
        self.message = message
        # Pass the message to parent class. If no message, pass the code.
        super().__init__(message if message else code)

# Initialize FastMCP server
mcp = FastMCP("catalogue-server")

# Load and validate data/catalogue.json
WORKSPACE_ROOT = Path(__file__).parent.parent.parent.resolve()
CATALOGUE_PATH = WORKSPACE_ROOT / "data" / "catalogue.json"

if not CATALOGUE_PATH.exists():
    raise FileNotFoundError(f"Catalogue file not found at {CATALOGUE_PATH}")

with open(CATALOGUE_PATH, "r", encoding="utf-8") as f:
    try:
        raw_data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse catalogue JSON: {e}")

courses: list[CourseRecord] = []
for idx, item in enumerate(raw_data):
    target_roles = item.get("target_roles")
    # target_roles must never be empty list; reject records missing it on load
    if not target_roles:
        raise ValueError(
            f"CourseRecord at index {idx} ({item.get('course_id')}) is missing target_roles or it is empty."
        )
    
    courses.append(
        CourseRecord(
            course_id=item["course_id"],
            title=item["title"],
            description=item["description"],
            type=item["type"],
            category=item["category"],
            duration_hours=float(item["duration_hours"]),
            provider=item["provider"],
            cost_per_person=float(item["cost_per_person"]),
            ts_cost=float(item["ts_cost"]),
            sme_contact=item["sme_contact"],
            target_roles=target_roles,
            min_grade=item.get("min_grade"),
        )
    )

# Tool definition
@mcp.tool()
def get_courses(
    course_id: Optional[str] = None,
    query: Optional[str] = None,
) -> list[CourseRecord]:
    """Get courses from the catalogue.

    Args:
        course_id: Optional unique course identifier to fetch.
        query: Optional search query to filter courses by title or description (case-insensitive).
    """
    if not courses:
        raise ToolError(code="CATALOGUE_EMPTY", message="Catalogue is empty")

    if course_id is not None:
        # course_id lookup returns list of one (never empty list) or raises
        for course in courses:
            if course.course_id == course_id:
                return [course]
        raise ToolError(code="COURSE_NOT_FOUND", message=f"Course '{course_id}' not found")

    if query is not None:
        q = query.lower()
        return [
            c for c in courses
            if q in c.title.lower() or q in c.description.lower()
        ]

    # both None: return all courses
    return courses

# Mock write tools to enforce read-only constraint
@mcp.tool()
def create_course(course: dict) -> dict:
    """Create a new course in the catalogue (Not Permitted)."""
    raise ToolError(code="WRITE_NOT_PERMITTED", message="Write operations are not permitted")

@mcp.tool()
def update_course(course_id: str, updates: dict) -> dict:
    """Update a course in the catalogue (Not Permitted)."""
    raise ToolError(code="WRITE_NOT_PERMITTED", message="Write operations are not permitted")

@mcp.tool()
def delete_course(course_id: str) -> dict:
    """Delete a course from the catalogue (Not Permitted)."""
    raise ToolError(code="WRITE_NOT_PERMITTED", message="Write operations are not permitted")

if __name__ == "__main__":
    # Self-checks
    assert len(courses) == 35, f"Expected 35 courses, got {len(courses)}"
    
    # Assert a known course_id (MEWP-001) is found
    mewp_found = any(c.course_id == "MEWP-001" for c in courses)
    assert mewp_found, "Known course_id (MEWP-001) not found in loaded courses"
    
    # Assert get_courses behaves correctly for course_id lookup
    mewp_courses = get_courses(course_id="MEWP-001")
    assert len(mewp_courses) == 1
    assert mewp_courses[0].course_id == "MEWP-001"
    
    # Assert write tools raise WRITE_NOT_PERMITTED
    try:
        create_course({})
        raise AssertionError("Expected ToolError for write tool call")
    except ToolError as e:
        assert e.code == "WRITE_NOT_PERMITTED", f"Expected WRITE_NOT_PERMITTED code, got {e.code}"
        
    print("Self-check completed successfully. Running MCP stdio server...", file=sys.stderr)
    mcp.run(transport="stdio")
