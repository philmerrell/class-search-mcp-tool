"""
MCP Tool - Boise State University Class Search Server

An MCP server that interfaces with the Boise State University Class Search API.
This enables AI assistants to help students find classes and academic advisors
assist students with course selection.

Key Lambda considerations:
- Each Lambda invocation creates a fresh FastMCP instance to avoid session manager reuse issues
- stateless_http=True ensures the server doesn't maintain session state between requests
- json_response=True returns JSON instead of SSE for better Lambda/API Gateway compatibility
- lifespan="on" in Mangum is required to initialize the StreamableHTTPSessionManager
"""

import os
import re
from typing import Optional

import httpx

from mcp.server.fastmcp import FastMCP


# =============================================================================
# Configuration
# =============================================================================

CLASS_SEARCH_API_BASE_URL = os.environ.get(
    "CLASS_SEARCH_API_BASE_URL", "https://classes.boisestate.edu"
)


# =============================================================================
# Term Validation
# =============================================================================


def validate_term(term: str) -> tuple[bool, str]:
    """
    Validate the term format.

    Term format: IYYT
    - I (1st digit): Institution (1 = Boise State)
    - YY (2nd-3rd digits): Two-digit year
    - T (4th digit): Semester (3 = Spring, 6 = Summer, 9 = Fall)

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not term or len(term) != 4:
        return False, "Term must be a 4-digit code (e.g., 1263 for Spring 2026)"

    if not term.isdigit():
        return False, "Term must contain only digits"

    if term[0] != "1":
        return False, "First digit must be 1 (Boise State)"

    if term[3] not in ("3", "6", "9"):
        return False, "Last digit must be 3 (Spring), 6 (Summer), or 9 (Fall)"

    return True, ""


def format_term_description(term: str) -> str:
    """Convert term code to human-readable description."""
    if len(term) != 4:
        return term

    year = f"20{term[1:3]}"
    semester_map = {"3": "Spring", "6": "Summer", "9": "Fall"}
    semester = semester_map.get(term[3], "Unknown")

    return f"{semester} {year}"


# =============================================================================
# API Client
# =============================================================================


async def make_api_request(
    method: str,
    endpoint: str,
    json_data: Optional[dict] = None,
    params: Optional[dict] = None,
) -> dict:
    """Make an HTTP request to the Class Search API."""
    url = f"{CLASS_SEARCH_API_BASE_URL}{endpoint}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        if method.upper() == "POST":
            response = await client.post(url, json=json_data)
        else:
            response = await client.get(url, params=params)

        response.raise_for_status()
        return response.json()


# =============================================================================
# Response Formatting Helpers
# =============================================================================


def format_class_summary(doc: dict) -> str:
    """Format a class document into a readable summary."""
    subject = doc.get("subject", "")
    catalog_number = doc.get("catalogNumber", "")
    title = doc.get("courseTitle", "")
    credits = doc.get("courseCredits", "")

    instructors = doc.get("instructors", [])
    instructor_names = ", ".join(
        f"{i.get('firstName', '')} {i.get('lastName', '')}".strip()
        for i in instructors
    ) or "TBA"

    days = doc.get("meetingDays", [])
    days_str = "/".join(days) if days else "TBA"

    time_start = doc.get("meetingTimeStart", "")
    time_end = doc.get("meetingTimeEnd", "")
    time_str = f"{time_start}-{time_end}" if time_start and time_end else "TBA"

    location = doc.get("buildingRoom", "") or doc.get("location", "") or "TBA"

    available = doc.get("availableSeats", 0)
    capacity = doc.get("classCapacity", 0)

    mode = doc.get("instructionModeDescription", doc.get("instructionMode", ""))
    class_number = doc.get("classNumber", "")

    return (
        f"**{subject} {catalog_number}: {title}** (Class #{class_number})\n"
        f"  Credits: {credits} | Instructor: {instructor_names}\n"
        f"  Schedule: {days_str} {time_str} | Location: {location}\n"
        f"  Seats: {available}/{capacity} available | Mode: {mode}"
    )


def format_class_details(doc: dict) -> str:
    """Format detailed class information."""
    subject = doc.get("subject", "")
    catalog_number = doc.get("catalogNumber", "")
    title = doc.get("courseTitle", "")
    class_number = doc.get("classNumber", "")
    description = doc.get("description", "No description available.")
    credits = doc.get("courseCredits", "")

    instructors = doc.get("instructors", [])
    instructor_names = ", ".join(
        f"{i.get('firstName', '')} {i.get('lastName', '')}".strip()
        for i in instructors
    ) or "TBA"

    days = doc.get("meetingDays", [])
    days_str = "/".join(days) if days else "TBA"

    time_start = doc.get("meetingTimeStart", "")
    time_end = doc.get("meetingTimeEnd", "")
    time_str = f"{time_start}-{time_end}" if time_start and time_end else "TBA"

    location = doc.get("buildingRoom", "") or doc.get("location", "") or "TBA"

    start_date = doc.get("startDate", "")
    end_date = doc.get("endDate", "")

    capacity = doc.get("classCapacity", 0)
    enrolled = doc.get("enrollmentTotal", 0)
    available = doc.get("availableSeats", 0)
    waitlist_cap = doc.get("waitListCapacity", 0)
    waitlist_total = doc.get("waitListTotal", 0)

    mode = doc.get("instructionModeDescription", doc.get("instructionMode", ""))
    session = doc.get("sessionCode", "")
    career = doc.get("academicCareer", "")
    status = doc.get("classStatus", "")

    attributes = doc.get("courseAttributeValues", [])
    attributes_str = ", ".join(attributes) if attributes else "None"

    req_designation = doc.get("requirementDesignation", "") or "None"

    return (
        f"## {subject} {catalog_number}: {title}\n"
        f"**Class Number:** {class_number}\n\n"
        f"**Description:** {description}\n\n"
        f"### Schedule & Location\n"
        f"- **Days/Times:** {days_str} {time_str}\n"
        f"- **Location:** {location}\n"
        f"- **Dates:** {start_date} to {end_date}\n"
        f"- **Session:** {session}\n\n"
        f"### Enrollment\n"
        f"- **Capacity:** {capacity}\n"
        f"- **Enrolled:** {enrolled}\n"
        f"- **Available Seats:** {available}\n"
        f"- **Waitlist:** {waitlist_total}/{waitlist_cap}\n\n"
        f"### Course Info\n"
        f"- **Credits:** {credits}\n"
        f"- **Instructor(s):** {instructor_names}\n"
        f"- **Instruction Mode:** {mode}\n"
        f"- **Academic Level:** {career}\n"
        f"- **Status:** {status}\n\n"
        f"### Requirements Fulfilled\n"
        f"- **Attributes:** {attributes_str}\n"
        f"- **Designation:** {req_designation}"
    )


# =============================================================================
# Tool Implementation Functions
# =============================================================================


async def _search_classes_impl(
    term: str,
    query: Optional[str] = None,
    page: int = 1,
    results_per_page: int = 10,
    academic_level: Optional[str] = None,
    subject_code: Optional[str] = None,
    campus: Optional[str] = None,
    instruction_mode: Optional[str] = None,
    session: Optional[str] = None,
    credits: Optional[str] = None,
    min_credits: Optional[int] = None,
    max_credits: Optional[int] = None,
    class_type: Optional[str] = None,
    meeting_time: Optional[str] = None,
    days: Optional[list[str]] = None,
    available_seats: Optional[str] = None,
    fee_structure: Optional[str] = None,
    foundations: Optional[list[str]] = None,
    requirement_designation: Optional[str] = None,
    course_id: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_direction: Optional[str] = None,
) -> dict:
    """Search for classes with flexible filtering options."""
    # Validate term
    is_valid, error_msg = validate_term(term)
    if not is_valid:
        return {"error": error_msg}

    # Validate query length if provided
    if query and len(query) <= 2:
        return {"error": "Search query must be more than 2 characters"}

    # Build request payload
    payload = {
        "term": term,
        "page": page,
        "resultsPerPage": results_per_page,
    }

    if query:
        payload["query"] = query
    if academic_level:
        payload["academicLevel"] = academic_level
    if subject_code:
        payload["subjectCode"] = subject_code
    if campus:
        payload["campus"] = campus
    if instruction_mode:
        payload["instructionMode"] = instruction_mode
    if session:
        payload["session"] = session
    if credits:
        payload["credits"] = credits
    if min_credits is not None:
        payload["minCredits"] = min_credits
    if max_credits is not None:
        payload["maxCredits"] = max_credits
    if class_type:
        payload["classType"] = class_type
    if meeting_time:
        payload["meetingTime"] = meeting_time
    if days:
        payload["days"] = days
    if available_seats:
        payload["availableSeats"] = available_seats
    if fee_structure:
        payload["feeStructure"] = fee_structure
    if foundations:
        payload["foundations"] = foundations
    if requirement_designation:
        payload["requirementDesignation"] = requirement_designation
    if course_id:
        payload["courseId"] = course_id
    if sort_by:
        payload["sortBy"] = sort_by
    if sort_direction:
        payload["sortDirection"] = sort_direction

    try:
        response = await make_api_request("POST", "/api/search", json_data=payload)

        total_hits = response.get("totalHits", 0)
        documents = response.get("documents", [])

        # Format results
        term_desc = format_term_description(term)

        if total_hits == 0:
            return {
                "term": term_desc,
                "total_results": 0,
                "message": "No classes found matching your criteria. Try broadening your search.",
                "classes": [],
            }

        formatted_classes = [format_class_summary(doc) for doc in documents]

        return {
            "term": term_desc,
            "total_results": total_hits,
            "page": page,
            "results_per_page": results_per_page,
            "showing": f"{(page - 1) * results_per_page + 1}-{min(page * results_per_page, total_hits)} of {total_hits}",
            "classes": formatted_classes,
        }

    except httpx.HTTPStatusError as e:
        return {"error": f"API request failed: {e.response.status_code}"}
    except Exception as e:
        return {"error": f"Request failed: {str(e)}"}


async def _get_class_details_impl(term: str, class_numbers: str) -> dict:
    """Get detailed information about specific class(es)."""
    # Validate term
    is_valid, error_msg = validate_term(term)
    if not is_valid:
        return {"error": error_msg}

    # Validate class numbers
    if not class_numbers:
        return {"error": "Class numbers are required"}

    # Clean up class numbers (remove spaces)
    class_numbers = re.sub(r"\s+", "", class_numbers)

    try:
        response = await make_api_request(
            "GET", f"/api/class/{term}/{class_numbers}"
        )

        # Handle both single class and multiple classes response
        if isinstance(response, list):
            documents = response
        elif isinstance(response, dict):
            documents = [response] if "classNumber" in response else response.get("documents", [response])
        else:
            documents = []

        if not documents:
            return {
                "term": format_term_description(term),
                "message": "No class details found for the provided class number(s).",
                "classes": [],
            }

        formatted_details = [format_class_details(doc) for doc in documents]

        return {
            "term": format_term_description(term),
            "class_count": len(documents),
            "classes": formatted_details,
        }

    except httpx.HTTPStatusError as e:
        return {"error": f"API request failed: {e.response.status_code}"}
    except Exception as e:
        return {"error": f"Request failed: {str(e)}"}


async def _check_seat_availability_impl(term: str, class_number: str) -> dict:
    """Get real-time seat availability for a specific class."""
    # Validate term
    is_valid, error_msg = validate_term(term)
    if not is_valid:
        return {"error": error_msg}

    if not class_number:
        return {"error": "Class number is required"}

    # Clean up class number
    class_number = class_number.strip()

    try:
        response = await make_api_request(
            "GET", f"/api/class/{term}/{class_number}/availability"
        )

        capacity = response.get("classCapacity", 0)
        enrolled = response.get("enrollmentTotal", 0)
        available = response.get("availableSeats", 0)
        waitlist_cap = response.get("waitListCapacity", 0)
        waitlist_total = response.get("waitListTotal", 0)

        # Determine status
        if available > 0:
            status = "OPEN"
            status_message = f"This class has {available} seat(s) available."
        elif waitlist_cap > 0 and waitlist_total < waitlist_cap:
            status = "WAITLIST AVAILABLE"
            waitlist_spots = waitlist_cap - waitlist_total
            status_message = f"This class is full, but {waitlist_spots} waitlist spot(s) are available."
        else:
            status = "FULL"
            status_message = "This class is full with no waitlist availability."

        return {
            "term": format_term_description(term),
            "class_number": class_number,
            "status": status,
            "status_message": status_message,
            "capacity": capacity,
            "enrolled": enrolled,
            "available_seats": available,
            "waitlist_capacity": waitlist_cap,
            "waitlist_enrolled": waitlist_total,
        }

    except httpx.HTTPStatusError as e:
        return {"error": f"API request failed: {e.response.status_code}"}
    except Exception as e:
        return {"error": f"Request failed: {str(e)}"}


async def _search_by_instructor_impl(term: str, instructor_name: str) -> dict:
    """Find all classes taught by a specific instructor."""
    # Validate term
    is_valid, error_msg = validate_term(term)
    if not is_valid:
        return {"error": error_msg}

    if not instructor_name or len(instructor_name.strip()) < 2:
        return {"error": "Instructor name must be at least 2 characters"}

    try:
        response = await make_api_request(
            "GET",
            f"/api/search/{term}/professor",
            params={"query": instructor_name.strip()},
        )

        # Handle response format
        if isinstance(response, dict):
            total_hits = response.get("totalHits", 0)
            documents = response.get("documents", [])
        else:
            documents = response if isinstance(response, list) else []
            total_hits = len(documents)

        if total_hits == 0:
            return {
                "term": format_term_description(term),
                "instructor_query": instructor_name,
                "total_results": 0,
                "message": f"No classes found for instructor matching '{instructor_name}'.",
                "classes": [],
            }

        formatted_classes = [format_class_summary(doc) for doc in documents]

        return {
            "term": format_term_description(term),
            "instructor_query": instructor_name,
            "total_results": total_hits,
            "classes": formatted_classes,
        }

    except httpx.HTTPStatusError as e:
        return {"error": f"API request failed: {e.response.status_code}"}
    except Exception as e:
        return {"error": f"Request failed: {str(e)}"}


async def _get_filter_options_impl(
    term: str,
    field_name: str,
    filter_key: Optional[str] = None,
    filter_value: Optional[str] = None,
) -> dict:
    """Get available values for a specific filter field."""
    # Validate term
    is_valid, error_msg = validate_term(term)
    if not is_valid:
        return {"error": error_msg}

    if not field_name:
        return {"error": "Field name is required"}

    # Build params
    params = {}
    if filter_key:
        params["filterKey"] = filter_key
    if filter_value:
        params["filterValue"] = filter_value

    try:
        response = await make_api_request(
            "GET",
            f"/api/{term}/filter-options/{field_name}",
            params=params if params else None,
        )

        # Handle response format
        if isinstance(response, list):
            options = response
        else:
            options = response.get("options", response.get("values", []))

        if not options:
            return {
                "term": format_term_description(term),
                "field": field_name,
                "message": f"No options found for field '{field_name}'.",
                "options": [],
            }

        # Format options
        formatted_options = []
        for opt in options:
            if isinstance(opt, dict):
                key = opt.get("key", opt.get("value", ""))
                count = opt.get("docCount", opt.get("count", 0))
                formatted_options.append({"value": key, "count": count})
            else:
                formatted_options.append({"value": str(opt), "count": None})

        return {
            "term": format_term_description(term),
            "field": field_name,
            "option_count": len(formatted_options),
            "options": formatted_options,
        }

    except httpx.HTTPStatusError as e:
        return {"error": f"API request failed: {e.response.status_code}"}
    except Exception as e:
        return {"error": f"Request failed: {str(e)}"}


# =============================================================================
# MCP Server Factory
# =============================================================================


def create_mcp_server() -> FastMCP:
    """
    Create a fresh FastMCP server instance.

    This factory function is called for each Lambda invocation to ensure
    a clean session manager state. The StreamableHTTPSessionManager can
    only run once per instance, so we need a fresh instance for each request.
    """
    # Try to import TransportSecuritySettings for DNS rebinding protection config
    try:
        from mcp.server.transport_security import TransportSecuritySettings

        transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        )
    except ImportError:
        transport_security = None

    # Initialize the MCP server in stateless mode for Lambda compatibility
    mcp_kwargs = {
        "name": "class-search-server",
        "instructions": """Use this server to help students and academic advisors search for classes at Boise State University.

Key capabilities:
- Search for classes by subject, keywords, schedule, availability, and more
- Get detailed information about specific classes
- Check real-time seat availability
- Find classes by instructor name
- Get available filter options (subjects, requirements, etc.)

Term Format (required for all operations):
- 4-digit code: IYYT where I=1 (Boise State), YY=year, T=semester
- T values: 3=Spring, 6=Summer, 9=Fall
- Examples: 1263=Spring 2026, 1269=Fall 2026, 1273=Spring 2027

Always use these tools when users ask about classes, course schedules, or registration-related queries.""",
        "stateless_http": True,
        "json_response": True,
    }

    if transport_security is not None:
        mcp_kwargs["transport_security"] = transport_security

    mcp = FastMCP(**mcp_kwargs)

    # Register tools with the MCP server
    @mcp.tool()
    async def search_classes(
        term: str,
        query: Optional[str] = None,
        page: int = 1,
        results_per_page: int = 10,
        academic_level: Optional[str] = None,
        subject_code: Optional[str] = None,
        campus: Optional[str] = None,
        instruction_mode: Optional[str] = None,
        session: Optional[str] = None,
        credits: Optional[str] = None,
        min_credits: Optional[int] = None,
        max_credits: Optional[int] = None,
        class_type: Optional[str] = None,
        meeting_time: Optional[str] = None,
        days: Optional[list[str]] = None,
        available_seats: Optional[str] = None,
        fee_structure: Optional[str] = None,
        foundations: Optional[list[str]] = None,
        requirement_designation: Optional[str] = None,
        course_id: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_direction: Optional[str] = None,
    ) -> dict:
        """
        Search for classes with flexible filtering options.

        Use this tool when a user wants to find classes based on keywords, subject,
        schedule preferences, availability, or other criteria.

        Args:
            term: Required. Term code (e.g., 1263 for Spring 2026). Format: IYYT where
                  I=1 (Boise State), YY=year, T=semester (3=Spring, 6=Summer, 9=Fall)
            query: Search keywords (course title, description, instructor). Must be >2 chars.
            page: Page number (1-indexed). Default: 1
            results_per_page: Results per page. Default: 10
            academic_level: UGRD (Undergraduate) or GRAD (Graduate)
            subject_code: Subject code (e.g., CS, MATH, BIOL)
            campus: Campus location (boise, center, southern, lcsc, online)
            instruction_mode: Delivery method (P=In Person, IN=Online, HY=Hybrid, RM=Remote)
            session: Academic session (1=Regular, 5W1/5W2/5W3=Five Week, 7W1/7W2=Seven Week, etc.)
            credits: Credit hours (1-5) or 'variable'
            min_credits: Minimum credits when credits='variable'
            max_credits: Maximum credits when credits='variable'
            class_type: Class activity type (LEC, LAB, DIS, SEM, etc.)
            meeting_time: Time preference (morning, afternoon, evening)
            days: Meeting days array (Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday)
            available_seats: Availability filter (open=has seats, waitlist=full)
            fee_structure: Billing structure (std=Standard, alt=Alternative)
            foundations: General education requirements array (e.g., Foundations of Mathematics)
            requirement_designation: Special designations (HON=Honors, SERV=Service Learning, etc.)
            course_id: Specific course identifier
            sort_by: Sort field (Catalog Number, Alphabetical, Enrollment)
            sort_direction: Sort order (Ascending, Descending)

        Returns:
            Search results with class summaries including subject, number, title, credits,
            instructor, schedule, location, and seat availability.
        """
        return await _search_classes_impl(
            term=term,
            query=query,
            page=page,
            results_per_page=results_per_page,
            academic_level=academic_level,
            subject_code=subject_code,
            campus=campus,
            instruction_mode=instruction_mode,
            session=session,
            credits=credits,
            min_credits=min_credits,
            max_credits=max_credits,
            class_type=class_type,
            meeting_time=meeting_time,
            days=days,
            available_seats=available_seats,
            fee_structure=fee_structure,
            foundations=foundations,
            requirement_designation=requirement_designation,
            course_id=course_id,
            sort_by=sort_by,
            sort_direction=sort_direction,
        )

    @mcp.tool()
    async def get_class_details(term: str, class_numbers: str) -> dict:
        """
        Get detailed information about specific class(es) by class number.

        Use this tool when a user wants full details about a specific class they've
        identified, or when comparing multiple specific classes.

        Args:
            term: Required. Term code (e.g., 1263 for Spring 2026)
            class_numbers: Required. One or more class numbers (comma-separated for multiple)

        Returns:
            Comprehensive class details including:
            - Full course title and description
            - Prerequisites/requisites
            - Meeting schedule (days, times, dates)
            - Location (building/room)
            - Instructor information
            - Enrollment numbers (capacity, enrolled, available, waitlist)
            - Course attributes and requirements fulfilled
        """
        return await _get_class_details_impl(term, class_numbers)

    @mcp.tool()
    async def check_seat_availability(term: str, class_number: str) -> dict:
        """
        Get real-time seat availability for a specific class.

        Use this tool when a user needs current enrollment numbers before registering,
        or when checking if a previously full class has openings.

        Args:
            term: Required. Term code (e.g., 1263 for Spring 2026)
            class_number: Required. Single class number to check

        Returns:
            Current availability status including:
            - Status (OPEN, WAITLIST AVAILABLE, or FULL)
            - Class capacity
            - Current enrollment
            - Available seats
            - Waitlist capacity and current waitlist count
        """
        return await _check_seat_availability_impl(term, class_number)

    @mcp.tool()
    async def search_by_instructor(term: str, instructor_name: str) -> dict:
        """
        Find all classes taught by a specific instructor.

        Use this tool when a user wants to find classes by a particular professor,
        or when an advisor knows a student works well with a specific instructor.

        Args:
            term: Required. Term code (e.g., 1263 for Spring 2026)
            instructor_name: Required. Instructor first and/or last name (min 2 characters)

        Returns:
            List of classes taught by matching instructor(s) with class summaries.
        """
        return await _search_by_instructor_impl(term, instructor_name)

    @mcp.tool()
    async def get_filter_options(
        term: str,
        field_name: str,
        filter_key: Optional[str] = None,
        filter_value: Optional[str] = None,
    ) -> dict:
        """
        Get available values for a specific filter field.

        Use this tool when you need to validate user input, show available options,
        or when filter values vary by term (like subject codes).

        Args:
            term: Required. Term code (e.g., 1263 for Spring 2026)
            field_name: Required. Field to get options for. Common values:
                - subject: All available subject codes
                - requirementDesignation: Special designations (Honors, Service Learning)
                - campus: Available campus locations
                - instructionMode: Delivery methods
                - session: Academic sessions
            filter_key: Optional field to filter results by
            filter_value: Value for the filter field

        Returns:
            List of available values with document counts where applicable.
        """
        return await _get_filter_options_impl(term, field_name, filter_key, filter_value)

    return mcp


# =============================================================================
# Lambda Handler
# =============================================================================


def lambda_handler(event, context):
    """
    AWS Lambda handler function.
    Uses Mangum to adapt the ASGI app for Lambda.
    """
    from mangum import Mangum

    mcp = create_mcp_server()
    app = mcp.streamable_http_app()

    handler = Mangum(app, lifespan="on")
    return handler(event, context)


# =============================================================================
# Local Development
# =============================================================================

_local_mcp = None


def get_local_app():
    """Get the ASGI app for local development."""
    global _local_mcp
    if _local_mcp is None:
        _local_mcp = create_mcp_server()
    return _local_mcp.streamable_http_app()


if __name__ == "__main__":
    import uvicorn

    app = get_local_app()
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
