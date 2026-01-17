"""
MCP Tool - Boise State University Class Search Server

An MCP server that queries OpenSearch directly for Boise State University class data.
This enables AI assistants to help students find classes and academic advisors
assist students with course selection.

Key features:
- Direct OpenSearch queries for maximum flexibility
- Fuzzy matching for subject codes and instructor names
- Schedule-based filtering for finding classes that fit
- Aggregations for analytics and discovery
"""

import os
from typing import Literal, Optional

from mcp.server.fastmcp import FastMCP

from opensearch_client import (
    get_opensearch_client,
    get_index_for_term,
    format_term_description,
    validate_term,
    validate_and_match_subject,
    get_valid_values,
    fuzzy_match_value,
    time_to_minutes,
    minutes_to_time,
)


# =============================================================================
# Type Definitions for Stable Values
# =============================================================================

DayOfWeek = Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
InstructionMode = Literal["In Person", "Online", "Hybrid", "Remote"]
AcademicLevel = Literal["UGRD", "GRAD"]
Location = Literal["Boise Campus", "Online", "City Center Plaza", "Remote", "Arranged"]
MeetingTime = Literal["morning", "afternoon", "evening"]


# =============================================================================
# Response Formatting
# =============================================================================


def format_class_summary(doc: dict) -> str:
    """Format a class document into a readable summary."""
    subject = doc.get("subject", "")
    catalog_number = doc.get("catalogNumber", "").strip()
    title = doc.get("courseTitle", "")
    credits = doc.get("courseCredits", "")

    # Try flat fields first (more reliable)
    first = doc.get("professorFirstName", "")
    last = doc.get("professorLastName", "")
    if first or last:
        instructor_names = f"{first} {last}".strip()
    else:
        # Fallback to instructors array
        instructors = doc.get("instructors", [])
        names = [
            f"{i.get('firstName', '')} {i.get('lastName', '')}".strip()
            for i in instructors
            if i.get('firstName') or i.get('lastName')
        ]
        instructor_names = ", ".join(names) if names else "TBA"

    days = doc.get("meetingDays", [])
    days_str = "/".join(days) if days else "TBA"

    start_mins = doc.get("meetingStartTimeInMinutes", 0)
    end_mins = doc.get("meetingEndTimeInMinutes", 0)
    if start_mins and end_mins:
        time_str = f"{minutes_to_time(start_mins)}-{minutes_to_time(end_mins)}"
    else:
        time_str = "TBA"

    location = doc.get("location", "") or doc.get("buildingRoom", "") or "TBA"

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
    catalog_number = doc.get("catalogNumber", "").strip()
    title = doc.get("courseTitle", "")
    class_number = doc.get("classNumber", "")
    description = doc.get("description", "No description available.")
    credits = doc.get("courseCredits", "")

    # Try flat fields first (more reliable)
    first = doc.get("professorFirstName", "")
    last = doc.get("professorLastName", "")
    if first or last:
        instructor_names = f"{first} {last}".strip()
    else:
        # Fallback to instructors array
        instructors = doc.get("instructors", [])
        names = [
            f"{i.get('firstName', '')} {i.get('lastName', '')}".strip()
            for i in instructors
            if i.get('firstName') or i.get('lastName')
        ]
        instructor_names = ", ".join(names) if names else "TBA"

    days = doc.get("meetingDays", [])
    days_str = "/".join(days) if days else "TBA"

    start_mins = doc.get("meetingStartTimeInMinutes", 0)
    end_mins = doc.get("meetingEndTimeInMinutes", 0)
    if start_mins and end_mins:
        time_str = f"{minutes_to_time(start_mins)}-{minutes_to_time(end_mins)}"
    else:
        time_str = "TBA"

    location = doc.get("location", "") or doc.get("buildingRoom", "") or "TBA"
    start_date = doc.get("startDate", "")
    end_date = doc.get("endDate", "")

    capacity = doc.get("classCapacity", 0)
    enrolled = doc.get("enrollmentTotal", 0)
    available = doc.get("availableSeats", 0)
    waitlist_cap = doc.get("waitListCapacity", 0)
    waitlist_total = doc.get("waitListTotal", 0)

    mode = doc.get("instructionModeDescription", doc.get("instructionMode", ""))
    session = doc.get("sessionCodeDescription", doc.get("sessionCode", ""))
    career = doc.get("academicCareer", "")
    status = doc.get("classStatusDescription", doc.get("classStatus", ""))

    attributes = doc.get("courseAttributeValues", [])
    attributes_str = ", ".join(attributes) if attributes else "None"

    req_designation = doc.get("requirementDesignationDescription", "") or doc.get("requirementDesignation", "") or "None"
    requisite = doc.get("requisite", "")

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
        f"### Requirements\n"
        f"- **Prerequisites:** {requisite if requisite else 'None'}\n"
        f"- **Attributes:** {attributes_str}\n"
        f"- **Designation:** {req_designation}"
    )


# =============================================================================
# Query Builders
# =============================================================================


def build_search_query(
    query: Optional[str] = None,
    subject: Optional[str] = None,
    catalog_number: Optional[str] = None,
    academic_level: Optional[str] = None,
    instruction_mode: Optional[str] = None,
    location: Optional[str] = None,
    days: Optional[list[str]] = None,
    meeting_time: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    min_credits: Optional[int] = None,
    max_credits: Optional[int] = None,
    session: Optional[str] = None,
    has_open_seats: Optional[bool] = None,
    course_attribute: Optional[str] = None,
    requirement_designation: Optional[str] = None,
    instructor_name: Optional[str] = None,
) -> dict:
    """Build an OpenSearch query from filter parameters."""
    must_clauses = []
    filter_clauses = []

    # Full-text search on title and description
    if query:
        must_clauses.append({
            "multi_match": {
                "query": query,
                "fields": ["courseTitle^2", "description", "subject"],
                "type": "best_fields",
                "fuzziness": "AUTO"
            }
        })

    # Subject filter (exact match on keyword field)
    if subject:
        filter_clauses.append({"term": {"subject": subject}})

    # Catalog number (supports prefix matching for level filtering like "3*" for 300-level)
    if catalog_number:
        if "*" in catalog_number or "?" in catalog_number:
            # Wildcard query - need to handle the leading space in catalog numbers
            filter_clauses.append({"wildcard": {"catalogNumber": f"*{catalog_number.lstrip()}"}})
        else:
            # Exact match - pad with space like the data has
            padded = catalog_number.strip().rjust(4)
            filter_clauses.append({"term": {"catalogNumber": padded}})

    # Academic level
    if academic_level:
        filter_clauses.append({"term": {"academicCareer": academic_level}})

    # Instruction mode
    if instruction_mode:
        filter_clauses.append({"term": {"instructionModeDescription": instruction_mode}})

    # Location
    if location:
        filter_clauses.append({"term": {"location": location}})

    # Days of week
    if days:
        for day in days:
            filter_clauses.append({"term": {"meetingDays": day}})

    # Meeting time (morning/afternoon/evening)
    if meeting_time:
        if meeting_time == "morning":
            # Before noon (720 minutes)
            filter_clauses.append({"range": {"meetingStartTimeInMinutes": {"gt": 0, "lt": 720}}})
        elif meeting_time == "afternoon":
            # Noon to 5pm (720-1020 minutes)
            filter_clauses.append({"range": {"meetingStartTimeInMinutes": {"gte": 720, "lt": 1020}}})
        elif meeting_time == "evening":
            # 5pm and later (1020+ minutes)
            filter_clauses.append({"range": {"meetingStartTimeInMinutes": {"gte": 1020}}})

    # Specific time range
    if start_time:
        start_mins = time_to_minutes(start_time)
        if start_mins is not None:
            filter_clauses.append({"range": {"meetingStartTimeInMinutes": {"gte": start_mins}}})

    if end_time:
        end_mins = time_to_minutes(end_time)
        if end_mins is not None:
            filter_clauses.append({"range": {"meetingEndTimeInMinutes": {"lte": end_mins}}})

    # Credits
    if min_credits is not None:
        filter_clauses.append({"range": {"courseCreditMin": {"gte": min_credits}}})
    if max_credits is not None:
        filter_clauses.append({"range": {"courseCreditMax": {"lte": max_credits}}})

    # Session
    if session:
        filter_clauses.append({"term": {"sessionCodeDescription": session}})

    # Open seats
    if has_open_seats:
        filter_clauses.append({"range": {"availableSeats": {"gt": 0}}})

    # Course attribute (gen ed, affordable materials, etc.)
    if course_attribute:
        filter_clauses.append({"term": {"courseAttributeValues": course_attribute}})

    # Requirement designation (honors, service learning, etc.)
    if requirement_designation:
        filter_clauses.append({"term": {"requirementDesignation": requirement_designation}})

    # Instructor name (fuzzy match on flat professor fields)
    if instructor_name:
        must_clauses.append({
            "bool": {
                "should": [
                    {"wildcard": {"professorFirstName": f"*{instructor_name}*"}},
                    {"wildcard": {"professorLastName": f"*{instructor_name}*"}}
                ],
                "minimum_should_match": 1
            }
        })

    # Build final query
    if must_clauses or filter_clauses:
        return {
            "bool": {
                "must": must_clauses if must_clauses else [{"match_all": {}}],
                "filter": filter_clauses
            }
        }
    else:
        return {"match_all": {}}


# =============================================================================
# MCP Server Factory
# =============================================================================


def create_mcp_server() -> FastMCP:
    """Create a fresh FastMCP server instance."""
    try:
        from mcp.server.transport_security import TransportSecuritySettings
        transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    except ImportError:
        transport_security = None

    mcp_kwargs = {
        "name": "class-search-server",
        "instructions": """Boise State University Class Search - Help students and advisors find classes.

TERM CODES (required for all searches):
- Spring 2026 = "1263"
- Summer 2026 = "1266"
- Fall 2026 = "1269"
- Pattern: 1 + YY + semester (3=Spring, 6=Summer, 9=Fall)

=== HANDLING AMBIGUOUS QUERIES ===

Students often don't know the exact system terminology. Use these strategies:

1. SCHEDULE CONFLICTS - When student says "doesn't conflict with my X class":
   - ASK: "What days does your class meet? What time does it start and end?"
   - THEN USE: check_schedule_conflicts with the time blocks they provide
   - Example: "CS classes that don't conflict with my MWF 10am class"
     -> Ask for end time, then use check_schedule_conflicts

2. VAGUE REQUIREMENTS - When student says "gen ed", "core", "cheap books":
   - USE: suggest_filter_values to find actual system values
   - Example: "general ed requirements" -> suggest_filter_values(keyword="gen ed")
     -> Returns "Foundations of Mathematics", "Foundations of Writing", etc.

3. UNKNOWN FILTER VALUES - Before filtering by attributes, sessions, etc.:
   - USE: get_filter_options to discover what values exist
   - Example: Before filtering by course_attribute, check what attributes are available

=== TOOL SELECTION GUIDE ===

DISCOVERY TOOLS (use first when query is ambiguous):
- suggest_filter_values - Map informal language to system values
  "gen ed" -> "Foundations of Mathematics"
  "cheap textbooks" -> "Zero Cost Course Materials"
- get_filter_options - See all valid values for a field
  field="attributes" shows all gen-ed categories

CONFLICT DETECTION:
- check_schedule_conflicts - Find classes avoiding time blocks
  REQUIRES: days, start_time, end_time for each class to avoid
  ASK the student if they don't provide complete info

SEARCH TOOLS:
- search_classes - Main search with filters (subject, time, mode, etc.)
- find_classes_by_schedule - When student has limited availability
- search_by_instructor - Find professor's classes
- compare_sections - Compare sections of same course

DETAIL TOOLS:
- get_class_details - Full info for a specific class
- check_availability - Quick seat/waitlist check

=== QUERY PATTERNS ===

EXPLICIT (ready to search):
- "CS classes on Tuesday/Thursday mornings" -> search_classes
- "MATH 170 sections" -> compare_sections

NEEDS DISCOVERY:
- "classes that fulfill general ed" -> suggest_filter_values first
- "affordable textbook classes" -> suggest_filter_values first

NEEDS CLARIFICATION:
- "doesn't conflict with my 10am class" -> ask for days + end time
- "fits my schedule" -> ask what times work

=== TIPS ===
- Subject codes auto-convert: "Computer Science" -> "CS"
- Wildcards for levels: catalog_number="3*" for 300-level
- Always default to has_open_seats=true unless student asks otherwise""",
        "stateless_http": True,
        "json_response": True,
    }

    if transport_security is not None:
        mcp_kwargs["transport_security"] = transport_security

    mcp = FastMCP(**mcp_kwargs)

    # =========================================================================
    # Tool: search_classes
    # =========================================================================

    @mcp.tool()
    async def search_classes(
        term: str,
        query: Optional[str] = None,
        subject: Optional[str] = None,
        catalog_number: Optional[str] = None,
        academic_level: Optional[AcademicLevel] = None,
        instruction_mode: Optional[InstructionMode] = None,
        location: Optional[Location] = None,
        days: Optional[list[DayOfWeek]] = None,
        meeting_time: Optional[MeetingTime] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        min_credits: Optional[int] = None,
        max_credits: Optional[int] = None,
        session: Optional[str] = None,
        has_open_seats: Optional[bool] = None,
        course_attribute: Optional[str] = None,
        requirement_designation: Optional[str] = None,
        instructor_name: Optional[str] = None,
        page: int = 1,
        results_per_page: int = 10,
        # Aliases for common parameter name variations agents might use
        subject_code: Optional[str] = None,  # Alias for subject
        department: Optional[str] = None,  # Alias for subject
        instructor: Optional[str] = None,  # Alias for instructor_name
        professor: Optional[str] = None,  # Alias for instructor_name
        open_seats: Optional[bool] = None,  # Alias for has_open_seats
        available_seats: Optional[bool] = None,  # Alias for has_open_seats
        availability: Optional[str] = None,  # Alias for has_open_seats (handles "open" string)
        course_number: Optional[str] = None,  # Alias for catalog_number
        number: Optional[str] = None,  # Alias for catalog_number
        level: Optional[AcademicLevel] = None,  # Alias for academic_level
        mode: Optional[InstructionMode] = None,  # Alias for instruction_mode
        delivery: Optional[InstructionMode] = None,  # Alias for instruction_mode
    ) -> dict:
        """
        Search for classes at Boise State University with flexible filtering.

        This is the primary search tool for EXPLICIT queries where you know the filter values.

        BEFORE USING - Check if you need discovery tools:
        - Vague attribute terms ("gen ed", "core requirements") -> use suggest_filter_values first
        - Schedule conflicts ("doesn't conflict with...") -> use check_schedule_conflicts instead
        - Unknown valid values -> use get_filter_options to see options

        USE THIS TOOL for queries like:
        - "Find CS classes" -> subject="CS"
        - "Online math classes" -> subject="MATH", instruction_mode="Online"
        - "Classes with Professor Smith" -> instructor_name="Smith"
        - "Morning classes on Monday/Wednesday" -> days=["Monday","Wednesday"], meeting_time="morning"
        - "Classes with open seats" -> has_open_seats=true
        - "Data science courses" -> query="data science"
        - "300-level biology" -> subject="BIOL", catalog_number="3*"

        IMPORTANT - Term codes:
        - Spring 2026 = "1263"
        - Summer 2026 = "1266"
        - Fall 2026 = "1269"
        - Format: 1 + YY + semester (3=Spring, 6=Summer, 9=Fall)

        Args:
            term: REQUIRED. Term code like "1263" for Spring 2026
            query: Free-text search of course titles/descriptions (e.g., "artificial intelligence")
            subject: Department code. Accepts full names like "Computer Science" (auto-converted to "CS")
            catalog_number: Course number. Use wildcards: "3*" for 300-level, "4*" for 400-level
            academic_level: "UGRD" for undergraduate, "GRAD" for graduate
            instruction_mode: "In Person", "Online", "Hybrid", or "Remote"
            location: "Boise Campus", "Online", "City Center Plaza", "Remote", or "Arranged"
            days: Array of days: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            meeting_time: "morning" (before noon), "afternoon" (12-5pm), "evening" (after 5pm)
            start_time: Earliest class start, e.g., "9:00 AM" or "09:00"
            end_time: Latest class end, e.g., "5:00 PM" or "17:00"
            min_credits: Minimum credits (1-6)
            max_credits: Maximum credits (1-6)
            session: "Regular Session", "1st Seven Week Session", "2nd Seven Week Session", etc.
            has_open_seats: Set to true to only show classes with available seats
            course_attribute: Gen-ed like "Foundations of Mathematics", or "Zero Cost Course Materials"
            requirement_designation: "HON" for Honors, "SERV" for Service Learning
            instructor_name: Instructor's first or last name (partial match supported)
            page: Page number for pagination (default: 1)
            results_per_page: Results per page, 1-50 (default: 10)

        Returns:
            Object with term, total_results, and array of formatted class summaries
        """
        # Handle parameter aliases - merge into primary parameter names
        if subject_code and not subject:
            subject = subject_code
        if department and not subject:
            subject = department
        if instructor and not instructor_name:
            instructor_name = instructor
        if professor and not instructor_name:
            instructor_name = professor
        if open_seats is not None and has_open_seats is None:
            has_open_seats = open_seats
        if available_seats is not None and has_open_seats is None:
            has_open_seats = available_seats
        if availability and has_open_seats is None:
            # Handle string values like "open"
            has_open_seats = availability.lower() in ("open", "available", "true", "yes")
        if course_number and not catalog_number:
            catalog_number = course_number
        if number and not catalog_number:
            catalog_number = number
        if level and not academic_level:
            academic_level = level
        if mode and not instruction_mode:
            instruction_mode = mode
        if delivery and not instruction_mode:
            instruction_mode = delivery

        # Validate term
        is_valid, error_msg = validate_term(term)
        if not is_valid:
            return {"error": error_msg}

        index = get_index_for_term(term)
        client = get_opensearch_client()

        # Validate and fuzzy-match subject if provided
        matched_subject = None
        if subject:
            matched_subject, subject_error = validate_and_match_subject(client, index, subject)
            if subject_error:
                return {"error": subject_error}

        # Build query
        search_query = build_search_query(
            query=query,
            subject=matched_subject,
            catalog_number=catalog_number,
            academic_level=academic_level,
            instruction_mode=instruction_mode,
            location=location,
            days=days,
            meeting_time=meeting_time,
            start_time=start_time,
            end_time=end_time,
            min_credits=min_credits,
            max_credits=max_credits,
            session=session,
            has_open_seats=has_open_seats,
            course_attribute=course_attribute,
            requirement_designation=requirement_designation,
            instructor_name=instructor_name,
        )

        # Pagination
        results_per_page = min(results_per_page, 50)
        from_offset = (page - 1) * results_per_page

        try:
            response = client.search(
                index=index,
                body={
                    "query": search_query,
                    "from": from_offset,
                    "size": results_per_page,
                    "sort": [
                        {"subject": "asc"},
                        {"catalogNumber": "asc"},
                        {"classSection": "asc"}
                    ]
                }
            )

            total_hits = response["hits"]["total"]["value"]
            documents = [hit["_source"] for hit in response["hits"]["hits"]]

            term_desc = format_term_description(term)

            if total_hits == 0:
                return {
                    "term": term_desc,
                    "total_results": 0,
                    "message": "No classes found matching your criteria. Try broadening your search.",
                    "classes": [],
                }

            formatted_classes = [format_class_summary(doc) for doc in documents]

            result = {
                "term": term_desc,
                "total_results": total_hits,
                "page": page,
                "results_per_page": results_per_page,
                "showing": f"{from_offset + 1}-{min(from_offset + results_per_page, total_hits)} of {total_hits}",
                "classes": formatted_classes,
            }

            # Note if subject was fuzzy-matched
            if subject and matched_subject and subject.upper() != matched_subject:
                result["note"] = f"Interpreted '{subject}' as '{matched_subject}'"

            return result

        except Exception as e:
            return {"error": f"Search failed: {str(e)}"}

    # =========================================================================
    # Tool: find_classes_by_schedule
    # =========================================================================

    @mcp.tool()
    async def find_classes_by_schedule(
        term: str,
        available_days: list[DayOfWeek],
        earliest_time: str,
        latest_time: str,
        subject: Optional[str] = None,
        academic_level: Optional[AcademicLevel] = None,
        has_open_seats: bool = True,
        min_credits: Optional[int] = None,
        max_credits: Optional[int] = None,
        results_per_page: int = 20,
    ) -> dict:
        """
        Find classes that fit within a student's available schedule.

        Use this tool when a student has specific time constraints:
        - "I work mornings, need afternoon classes" -> available_days=["Monday","Tuesday","Wednesday","Thursday","Friday"], earliest_time="12:00 PM", latest_time="9:00 PM"
        - "Only free Tuesday/Thursday" -> available_days=["Tuesday","Thursday"], earliest_time="8:00 AM", latest_time="10:00 PM"
        - "Need classes between 10am-2pm on MWF" -> available_days=["Monday","Wednesday","Friday"], earliest_time="10:00 AM", latest_time="2:00 PM"

        This tool finds classes that ONLY meet on the specified days and within the time window.
        Classes meeting on other days are excluded.

        Args:
            term: REQUIRED. Term code like "1263" for Spring 2026
            available_days: REQUIRED. Days student can attend: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            earliest_time: REQUIRED. Earliest start time, e.g., "8:00 AM" or "08:00"
            latest_time: REQUIRED. Latest end time, e.g., "5:00 PM" or "17:00"
            subject: Optional department code like "CS", "MATH" (accepts full names)
            academic_level: "UGRD" or "GRAD"
            has_open_seats: Only show available classes (default: true)
            min_credits: Minimum credits
            max_credits: Maximum credits
            results_per_page: Number of results (default: 20, max: 50)

        Returns:
            Classes fitting the schedule with days/time constraints shown
        """
        is_valid, error_msg = validate_term(term)
        if not is_valid:
            return {"error": error_msg}

        earliest_mins = time_to_minutes(earliest_time)
        latest_mins = time_to_minutes(latest_time)

        if earliest_mins is None:
            return {"error": f"Could not parse earliest_time '{earliest_time}'. Use format like '9:00 AM' or '14:00'"}
        if latest_mins is None:
            return {"error": f"Could not parse latest_time '{latest_time}'. Use format like '3:00 PM' or '15:00'"}

        index = get_index_for_term(term)
        client = get_opensearch_client()

        # Validate subject if provided
        matched_subject = None
        if subject:
            matched_subject, subject_error = validate_and_match_subject(client, index, subject)
            if subject_error:
                return {"error": subject_error}

        # Build query: classes that ONLY meet on available days AND within time range
        filter_clauses = [
            {"range": {"meetingStartTimeInMinutes": {"gte": earliest_mins}}},
            {"range": {"meetingEndTimeInMinutes": {"lte": latest_mins}}},
        ]

        # Only include classes whose meeting days are subset of available days
        # This is tricky - we need classes that don't meet on unavailable days
        all_days = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}
        unavailable_days = all_days - set(available_days)

        for day in unavailable_days:
            filter_clauses.append({"bool": {"must_not": {"term": {"meetingDays": day}}}})

        # Must have at least one meeting day
        should_days = [{"term": {"meetingDays": day}} for day in available_days]
        filter_clauses.append({"bool": {"should": should_days, "minimum_should_match": 1}})

        if matched_subject:
            filter_clauses.append({"term": {"subject": matched_subject}})

        if academic_level:
            filter_clauses.append({"term": {"academicCareer": academic_level}})

        if has_open_seats:
            filter_clauses.append({"range": {"availableSeats": {"gt": 0}}})

        if min_credits is not None:
            filter_clauses.append({"range": {"courseCreditMin": {"gte": min_credits}}})
        if max_credits is not None:
            filter_clauses.append({"range": {"courseCreditMax": {"lte": max_credits}}})

        try:
            response = client.search(
                index=index,
                body={
                    "query": {"bool": {"filter": filter_clauses}},
                    "size": min(results_per_page, 50),
                    "sort": [
                        {"subject": "asc"},
                        {"catalogNumber": "asc"}
                    ]
                }
            )

            total_hits = response["hits"]["total"]["value"]
            documents = [hit["_source"] for hit in response["hits"]["hits"]]

            term_desc = format_term_description(term)

            if total_hits == 0:
                return {
                    "term": term_desc,
                    "schedule_constraints": {
                        "days": available_days,
                        "time_range": f"{earliest_time} - {latest_time}"
                    },
                    "total_results": 0,
                    "message": "No classes found matching your schedule. Try expanding your available times or days.",
                    "classes": [],
                }

            return {
                "term": term_desc,
                "schedule_constraints": {
                    "days": available_days,
                    "time_range": f"{earliest_time} - {latest_time}"
                },
                "total_results": total_hits,
                "showing": min(results_per_page, total_hits),
                "classes": [format_class_summary(doc) for doc in documents],
            }

        except Exception as e:
            return {"error": f"Search failed: {str(e)}"}

    # =========================================================================
    # Tool: search_by_instructor
    # =========================================================================

    @mcp.tool()
    async def search_by_instructor(
        term: str,
        instructor_name: str,
        subject: Optional[str] = None,
        has_open_seats: Optional[bool] = None,
    ) -> dict:
        """
        Find all classes taught by a specific instructor.

        Use this when a student asks about a specific professor:
        - "What is Dr. Smith teaching?" -> instructor_name="Smith"
        - "Find Professor Johnson's CS classes" -> instructor_name="Johnson", subject="CS"
        - "Classes by Vail with open seats" -> instructor_name="Vail", has_open_seats=true

        Supports partial name matching - "John" will match "Johnson", "Johnston", etc.

        Args:
            term: REQUIRED. Term code like "1263" for Spring 2026
            instructor_name: REQUIRED. First or last name (partial matches work)
            subject: Optional department filter like "CS", "MATH"
            has_open_seats: Set true to only show classes with availability

        Returns:
            All classes taught by matching instructor(s) with schedule and seat info
        """
        is_valid, error_msg = validate_term(term)
        if not is_valid:
            return {"error": error_msg}

        if not instructor_name or len(instructor_name.strip()) < 2:
            return {"error": "Instructor name must be at least 2 characters"}

        index = get_index_for_term(term)
        client = get_opensearch_client()

        # Validate subject if provided
        matched_subject = None
        if subject:
            matched_subject, subject_error = validate_and_match_subject(client, index, subject)
            if subject_error:
                return {"error": subject_error}

        # Build query with wildcard instructor search on flat fields
        must_clauses = [{
            "bool": {
                "should": [
                    {"wildcard": {"professorFirstName": f"*{instructor_name}*"}},
                    {"wildcard": {"professorLastName": f"*{instructor_name}*"}}
                ],
                "minimum_should_match": 1
            }
        }]

        filter_clauses = []
        if matched_subject:
            filter_clauses.append({"term": {"subject": matched_subject}})
        if has_open_seats:
            filter_clauses.append({"range": {"availableSeats": {"gt": 0}}})

        try:
            response = client.search(
                index=index,
                body={
                    "query": {
                        "bool": {
                            "must": must_clauses,
                            "filter": filter_clauses
                        }
                    },
                    "size": 50,
                    "sort": [
                        {"subject": "asc"},
                        {"catalogNumber": "asc"}
                    ]
                }
            )

            total_hits = response["hits"]["total"]["value"]
            documents = [hit["_source"] for hit in response["hits"]["hits"]]

            term_desc = format_term_description(term)

            if total_hits == 0:
                return {
                    "term": term_desc,
                    "instructor_query": instructor_name,
                    "total_results": 0,
                    "message": f"No classes found for instructor matching '{instructor_name}'.",
                    "classes": [],
                }

            return {
                "term": term_desc,
                "instructor_query": instructor_name,
                "total_results": total_hits,
                "classes": [format_class_summary(doc) for doc in documents],
            }

        except Exception as e:
            return {"error": f"Search failed: {str(e)}"}

    # =========================================================================
    # Tool: get_class_details
    # =========================================================================

    @mcp.tool()
    async def get_class_details(term: str, class_number: str) -> dict:
        """
        Get full details about a specific class section.

        Use this after a search when the user wants more information:
        - Course description and prerequisites
        - Complete schedule (days, times, dates, location)
        - Current enrollment numbers
        - Instructor information
        - Course attributes and requirements fulfilled

        The class_number comes from search results (shown as "Class #12345").

        Args:
            term: REQUIRED. Term code like "1263" for Spring 2026
            class_number: REQUIRED. The 5-digit class number from search results (e.g., "11039")

        Returns:
            Detailed class information including description, schedule, enrollment, and requirements
        """
        is_valid, error_msg = validate_term(term)
        if not is_valid:
            return {"error": error_msg}

        if not class_number:
            return {"error": "Class number is required"}

        index = get_index_for_term(term)
        client = get_opensearch_client()

        try:
            response = client.search(
                index=index,
                body={
                    "query": {"term": {"classNumber": class_number.strip()}},
                    "size": 1
                }
            )

            if response["hits"]["total"]["value"] == 0:
                return {
                    "term": format_term_description(term),
                    "class_number": class_number,
                    "error": f"No class found with number '{class_number}'"
                }

            doc = response["hits"]["hits"][0]["_source"]

            return {
                "term": format_term_description(term),
                "details": format_class_details(doc)
            }

        except Exception as e:
            return {"error": f"Lookup failed: {str(e)}"}

    # =========================================================================
    # Tool: check_availability
    # =========================================================================

    @mcp.tool()
    async def check_availability(term: str, class_number: str) -> dict:
        """
        Quick check of seat availability for a specific class.

        Use this to check if a class has open seats or waitlist spots:
        - "Is CS 121 section 001 still open?" -> Use class_number from that section
        - "Check if class 11039 has seats" -> class_number="11039"

        Returns a clear status: OPEN, WAITLIST AVAILABLE, or FULL.

        Args:
            term: REQUIRED. Term code like "1263" for Spring 2026
            class_number: REQUIRED. The 5-digit class number (e.g., "11039")

        Returns:
            Status (OPEN/WAITLIST/FULL), seat counts, and waitlist info
        """
        is_valid, error_msg = validate_term(term)
        if not is_valid:
            return {"error": error_msg}

        if not class_number:
            return {"error": "Class number is required"}

        index = get_index_for_term(term)
        client = get_opensearch_client()

        try:
            response = client.search(
                index=index,
                body={
                    "query": {"term": {"classNumber": class_number.strip()}},
                    "size": 1,
                    "_source": [
                        "subject", "catalogNumber", "courseTitle", "classNumber",
                        "classCapacity", "enrollmentTotal", "availableSeats",
                        "waitListCapacity", "waitListTotal"
                    ]
                }
            )

            if response["hits"]["total"]["value"] == 0:
                return {
                    "term": format_term_description(term),
                    "class_number": class_number,
                    "error": f"No class found with number '{class_number}'"
                }

            doc = response["hits"]["hits"][0]["_source"]

            capacity = doc.get("classCapacity", 0)
            enrolled = doc.get("enrollmentTotal", 0)
            available = doc.get("availableSeats", 0)
            waitlist_cap = doc.get("waitListCapacity", 0)
            waitlist_total = doc.get("waitListTotal", 0)

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

            subject = doc.get("subject", "")
            catalog = doc.get("catalogNumber", "").strip()
            title = doc.get("courseTitle", "")

            return {
                "term": format_term_description(term),
                "class": f"{subject} {catalog}: {title}",
                "class_number": class_number,
                "status": status,
                "status_message": status_message,
                "capacity": capacity,
                "enrolled": enrolled,
                "available_seats": available,
                "waitlist_capacity": waitlist_cap,
                "waitlist_enrolled": waitlist_total,
            }

        except Exception as e:
            return {"error": f"Lookup failed: {str(e)}"}

    # =========================================================================
    # Tool: compare_sections
    # =========================================================================

    @mcp.tool()
    async def compare_sections(
        term: str,
        subject: str,
        catalog_number: str,
    ) -> dict:
        """
        Compare all sections of a specific course side-by-side.

        Use this when a student knows which course they want and needs to pick a section:
        - "Show me all sections of CS 121" -> subject="CS", catalog_number="121"
        - "Compare MATH 170 sections" -> subject="MATH", catalog_number="170"
        - "What times is BIOL 191 offered?" -> subject="BIOL", catalog_number="191"

        Returns a comparison table with instructor, days/times, location, and seat availability
        for each section.

        Args:
            term: REQUIRED. Term code like "1263" for Spring 2026
            subject: REQUIRED. Department code like "CS", "MATH", "BIOL"
            catalog_number: REQUIRED. Course number like "121", "170", "191"

        Returns:
            All sections with instructor, schedule, location, mode, and availability for easy comparison
        """
        is_valid, error_msg = validate_term(term)
        if not is_valid:
            return {"error": error_msg}

        index = get_index_for_term(term)
        client = get_opensearch_client()

        # Validate subject
        matched_subject, subject_error = validate_and_match_subject(client, index, subject)
        if subject_error:
            return {"error": subject_error}

        # Pad catalog number
        padded_catalog = catalog_number.strip().rjust(4)

        try:
            response = client.search(
                index=index,
                body={
                    "query": {
                        "bool": {
                            "filter": [
                                {"term": {"subject": matched_subject}},
                                {"term": {"catalogNumber": padded_catalog}}
                            ]
                        }
                    },
                    "size": 50,
                    "sort": [{"classSection": "asc"}]
                }
            )

            total_hits = response["hits"]["total"]["value"]
            documents = [hit["_source"] for hit in response["hits"]["hits"]]

            term_desc = format_term_description(term)
            course_name = f"{matched_subject} {catalog_number.strip()}"

            if total_hits == 0:
                return {
                    "term": term_desc,
                    "course": course_name,
                    "total_sections": 0,
                    "message": f"No sections found for {course_name}. Verify the course exists this term.",
                    "sections": [],
                }

            # Get course title from first result
            course_title = documents[0].get("courseTitle", "")

            # Format sections for comparison
            sections = []
            for doc in documents:
                instructors = doc.get("instructors", [])
                if instructors:
                    instructor = f"{instructors[0].get('firstName', '')} {instructors[0].get('lastName', '')}".strip()
                else:
                    instructor = f"{doc.get('professorFirstName', '')} {doc.get('professorLastName', '')}".strip() or "TBA"

                days = doc.get("meetingDays", [])
                start_mins = doc.get("meetingStartTimeInMinutes", 0)
                end_mins = doc.get("meetingEndTimeInMinutes", 0)

                if start_mins and end_mins:
                    time_str = f"{minutes_to_time(start_mins)}-{minutes_to_time(end_mins)}"
                else:
                    time_str = "TBA"

                sections.append({
                    "class_number": doc.get("classNumber", ""),
                    "section": doc.get("classSection", ""),
                    "instructor": instructor,
                    "days": "/".join(days) if days else "TBA",
                    "time": time_str,
                    "location": doc.get("location", "") or doc.get("buildingRoom", "") or "TBA",
                    "mode": doc.get("instructionModeDescription", ""),
                    "available_seats": doc.get("availableSeats", 0),
                    "capacity": doc.get("classCapacity", 0),
                    "session": doc.get("sessionCodeDescription", ""),
                })

            return {
                "term": term_desc,
                "course": f"{course_name}: {course_title}",
                "total_sections": total_hits,
                "sections": sections,
            }

        except Exception as e:
            return {"error": f"Search failed: {str(e)}"}

    # =========================================================================
    # Tool: check_schedule_conflicts
    # =========================================================================

    @mcp.tool()
    async def check_schedule_conflicts(
        term: str,
        existing_classes: list[dict],
        subject: Optional[str] = None,
        academic_level: Optional[AcademicLevel] = None,
        instruction_mode: Optional[InstructionMode] = None,
        min_credits: Optional[int] = None,
        max_credits: Optional[int] = None,
        has_open_seats: bool = True,
        buffer_minutes: int = 15,
        results_per_page: int = 20,
    ) -> dict:
        """
        Find classes that don't conflict with a student's existing schedule.

        Use this when a student has existing classes and wants to find non-conflicting options:
        - "CS classes that don't conflict with my MWF 10am class"
        - "Find MATH classes that fit around my current schedule"
        - "What electives can I take that won't overlap with my Tuesday classes?"

        IMPORTANT: The agent should ask clarifying questions to build the existing_classes list:
        - What days does your current class meet?
        - What time does it start and end?
        - Do you have multiple classes to avoid?

        Args:
            term: REQUIRED. Term code like "1263" for Spring 2026
            existing_classes: REQUIRED. List of time blocks to avoid. Each dict needs:
                - days: list of days ["Monday", "Wednesday", "Friday"]
                - start_time: start time like "10:00 AM"
                - end_time: end time like "11:15 AM"
                Example: [{"days": ["Monday", "Wednesday", "Friday"], "start_time": "10:00 AM", "end_time": "11:15 AM"}]
            subject: Optional department code like "CS", "MATH" (accepts full names)
            academic_level: "UGRD" or "GRAD"
            instruction_mode: "In Person", "Online", "Hybrid", or "Remote"
            min_credits: Minimum credits
            max_credits: Maximum credits
            has_open_seats: Only show available classes (default: true)
            buffer_minutes: Minutes of travel time between classes (default: 15)
            results_per_page: Number of results (default: 20, max: 50)

        Returns:
            Classes that don't conflict with any of the existing time blocks
        """
        is_valid, error_msg = validate_term(term)
        if not is_valid:
            return {"error": error_msg}

        if not existing_classes:
            return {"error": "existing_classes is required. Provide at least one time block to avoid."}

        # Validate and parse existing class times
        conflict_blocks = []
        for i, block in enumerate(existing_classes):
            if not isinstance(block, dict):
                return {"error": f"existing_classes[{i}] must be an object with days, start_time, end_time"}

            days = block.get("days", [])
            start_str = block.get("start_time", "")
            end_str = block.get("end_time", "")

            if not days or not start_str or not end_str:
                return {"error": f"existing_classes[{i}] requires days, start_time, and end_time"}

            start_mins = time_to_minutes(start_str)
            end_mins = time_to_minutes(end_str)

            if start_mins is None:
                return {"error": f"Could not parse start_time '{start_str}' in existing_classes[{i}]"}
            if end_mins is None:
                return {"error": f"Could not parse end_time '{end_str}' in existing_classes[{i}]"}

            conflict_blocks.append({
                "days": set(days),
                "start": start_mins - buffer_minutes,  # Add buffer before
                "end": end_mins + buffer_minutes,       # Add buffer after
            })

        index = get_index_for_term(term)
        client = get_opensearch_client()

        # Validate subject if provided
        matched_subject = None
        if subject:
            matched_subject, subject_error = validate_and_match_subject(client, index, subject)
            if subject_error:
                return {"error": subject_error}

        # Build base query
        filter_clauses = []

        if matched_subject:
            filter_clauses.append({"term": {"subject": matched_subject}})

        if academic_level:
            filter_clauses.append({"term": {"academicCareer": academic_level}})

        if instruction_mode:
            filter_clauses.append({"term": {"instructionModeDescription": instruction_mode}})

        if has_open_seats:
            filter_clauses.append({"range": {"availableSeats": {"gt": 0}}})

        if min_credits is not None:
            filter_clauses.append({"range": {"courseCreditMin": {"gte": min_credits}}})
        if max_credits is not None:
            filter_clauses.append({"range": {"courseCreditMax": {"lte": max_credits}}})

        try:
            # First, get candidate classes
            response = client.search(
                index=index,
                body={
                    "query": {"bool": {"filter": filter_clauses}} if filter_clauses else {"match_all": {}},
                    "size": 200,  # Get more to filter locally
                    "sort": [
                        {"subject": "asc"},
                        {"catalogNumber": "asc"}
                    ]
                }
            )

            documents = [hit["_source"] for hit in response["hits"]["hits"]]

            # Filter out conflicting classes
            non_conflicting = []
            for doc in documents:
                class_days = set(doc.get("meetingDays", []))
                class_start = doc.get("meetingStartTimeInMinutes", 0)
                class_end = doc.get("meetingEndTimeInMinutes", 0)

                # Online/async classes with no meeting time don't conflict
                if not class_days or (class_start == 0 and class_end == 0):
                    non_conflicting.append(doc)
                    continue

                # Check against each conflict block
                has_conflict = False
                for block in conflict_blocks:
                    # Check if days overlap
                    if class_days & block["days"]:
                        # Check if times overlap
                        if class_start < block["end"] and class_end > block["start"]:
                            has_conflict = True
                            break

                if not has_conflict:
                    non_conflicting.append(doc)

            # Limit results
            total_found = len(non_conflicting)
            non_conflicting = non_conflicting[:min(results_per_page, 50)]

            term_desc = format_term_description(term)

            # Format conflict summary for response
            conflict_summary = []
            for block in existing_classes:
                days_str = "/".join(block.get("days", []))
                conflict_summary.append(f"{days_str} {block.get('start_time', '')} - {block.get('end_time', '')}")

            if total_found == 0:
                return {
                    "term": term_desc,
                    "avoiding": conflict_summary,
                    "buffer_minutes": buffer_minutes,
                    "total_results": 0,
                    "message": "No classes found that avoid your schedule conflicts. Try different subjects or removing some constraints.",
                    "classes": [],
                }

            return {
                "term": term_desc,
                "avoiding": conflict_summary,
                "buffer_minutes": buffer_minutes,
                "total_results": total_found,
                "showing": len(non_conflicting),
                "classes": [format_class_summary(doc) for doc in non_conflicting],
            }

        except Exception as e:
            return {"error": f"Search failed: {str(e)}"}

    # =========================================================================
    # Tool: suggest_filter_values
    # =========================================================================

    @mcp.tool()
    async def suggest_filter_values(
        term: str,
        keyword: str,
        field: str = "attributes",
    ) -> dict:
        """
        Find filter values that match a keyword or phrase.

        Use this when a student uses informal language that needs to be mapped to actual filter values:
        - "general ed" -> finds "Foundations of Mathematics", "Foundations of Writing", etc.
        - "cheap textbooks" -> finds "Zero Cost Course Materials", "Low Cost Course Materials"
        - "honors" -> finds honors-related attributes or designations

        This tool helps bridge the gap between how students describe requirements
        and the actual system values.

        Common keyword mappings:
        - "gen ed", "general education", "core" -> Foundations attributes
        - "free textbooks", "affordable", "cheap books" -> Cost-related attributes
        - "honors" -> Honors designation
        - "service", "community" -> Service Learning

        Args:
            term: REQUIRED. Term code like "1263" for Spring 2026
            keyword: REQUIRED. Informal keyword or phrase to search for (e.g., "gen ed", "cheap books")
            field: Which field to search. Options:
                - "attributes" (default) - Course attributes like gen-ed requirements
                - "designation" - Requirement designations like Honors
                - "session" - Session types
                - "mode" - Instruction modes

        Returns:
            Matching filter values with explanations, ready to use in search_classes
        """
        is_valid, error_msg = validate_term(term)
        if not is_valid:
            return {"error": error_msg}

        if not keyword or len(keyword.strip()) < 2:
            return {"error": "Keyword must be at least 2 characters"}

        # Map field to actual field name
        field_map = {
            "attributes": "courseAttributeValues",
            "attribute": "courseAttributeValues",
            "designation": "requirementDesignation",
            "designations": "requirementDesignation",
            "session": "sessionCodeDescription",
            "sessions": "sessionCodeDescription",
            "mode": "instructionModeDescription",
            "modes": "instructionModeDescription",
        }
        actual_field = field_map.get(field.lower(), "courseAttributeValues")

        index = get_index_for_term(term)
        client = get_opensearch_client()

        # Keyword expansion - common student phrases to system concepts
        keyword_lower = keyword.lower().strip()
        expanded_keywords = [keyword_lower]

        # Add related terms
        keyword_expansions = {
            "gen ed": ["foundations", "core", "general"],
            "general ed": ["foundations", "core", "general"],
            "general education": ["foundations", "core", "general"],
            "core": ["foundations", "general"],
            "cheap": ["zero cost", "low cost", "affordable"],
            "free": ["zero cost"],
            "affordable": ["low cost", "zero cost"],
            "textbook": ["course materials", "materials"],
            "textbooks": ["course materials", "materials"],
            "books": ["course materials", "materials"],
            "honors": ["hon", "honors"],
            "service": ["service learning", "community"],
            "community": ["service learning"],
            "online": ["distance", "remote", "web"],
            "math": ["mathematics", "quantitative"],
            "writing": ["composition", "written"],
            "science": ["scientific", "natural"],
        }

        for key, expansions in keyword_expansions.items():
            if key in keyword_lower:
                expanded_keywords.extend(expansions)

        try:
            # Get all values for the field
            response = client.search(
                index=index,
                body={
                    "size": 0,
                    "aggs": {
                        "values": {
                            "terms": {
                                "field": actual_field,
                                "size": 500
                            }
                        }
                    }
                }
            )

            buckets = response.get("aggregations", {}).get("values", {}).get("buckets", [])
            all_values = [(bucket["key"], bucket["doc_count"]) for bucket in buckets if bucket["key"]]

            # Find matches
            matches = []
            for value, count in all_values:
                value_lower = value.lower()
                for kw in expanded_keywords:
                    if kw in value_lower or value_lower in kw:
                        matches.append({
                            "value": value,
                            "class_count": count,
                            "matched_keyword": kw if kw != keyword_lower else None,
                        })
                        break

            # Remove duplicates and sort by count
            seen = set()
            unique_matches = []
            for m in sorted(matches, key=lambda x: x["class_count"], reverse=True):
                if m["value"] not in seen:
                    seen.add(m["value"])
                    unique_matches.append(m)

            term_desc = format_term_description(term)

            if not unique_matches:
                # Provide some suggestions even if no match
                sample_values = [v for v, c in all_values[:10]]
                return {
                    "term": term_desc,
                    "keyword": keyword,
                    "field": field,
                    "matches": [],
                    "message": f"No {field} values matched '{keyword}'.",
                    "available_samples": sample_values,
                    "tip": "Use get_filter_options to see all available values for this field.",
                }

            return {
                "term": term_desc,
                "keyword": keyword,
                "field": field,
                "matches": unique_matches,
                "usage_tip": "Use these values with search_classes course_attribute parameter",
            }

        except Exception as e:
            return {"error": f"Search failed: {str(e)}"}

    # =========================================================================
    # Tool: get_filter_options
    # =========================================================================

    @mcp.tool()
    async def get_filter_options(
        term: str,
        field: str,
    ) -> dict:
        """
        Discover ALL available filter values for a field.

        USE THIS when you need to see the complete list of valid values.
        For keyword-based discovery (e.g., "gen ed" -> matching values), use suggest_filter_values instead.

        When to use this vs suggest_filter_values:
        - get_filter_options: "Show me all available attributes" -> complete list
        - suggest_filter_values: "Find attributes related to 'gen ed'" -> filtered matches

        Common use cases:
        - "What subjects are available?" -> field="subject"
        - "What gen-ed requirements exist?" -> field="attributes"
        - "What session types are offered?" -> field="session"

        Available fields:
        - "subject" - All department codes (CS, MATH, BIOL, etc.) with class counts
        - "attributes" - Course attributes like "Foundations of Mathematics", "Zero Cost Course Materials"
        - "session" - Session types: "Regular Session", "1st Seven Week Session", etc.
        - "mode" - Instruction modes: "In Person", "Online", "Hybrid", "Remote"
        - "location" - Campus locations: "Boise Campus", "Online", "City Center Plaza"
        - "level" - Academic levels: "UGRD", "GRAD"

        Args:
            term: REQUIRED. Term code like "1263" for Spring 2026
            field: REQUIRED. One of: "subject", "attributes", "session", "mode", "location", "level"

        Returns:
            List of available values with the count of classes for each
        """
        is_valid, error_msg = validate_term(term)
        if not is_valid:
            return {"error": error_msg}

        # Map friendly names to actual field names
        field_map = {
            "subject": "subject",
            "subjects": "subject",
            "courseAttributeValues": "courseAttributeValues",
            "course_attribute": "courseAttributeValues",
            "course_attributes": "courseAttributeValues",
            "attributes": "courseAttributeValues",
            "requirementDesignation": "requirementDesignation",
            "requirement_designation": "requirementDesignation",
            "designation": "requirementDesignation",
            "sessionCodeDescription": "sessionCodeDescription",
            "session": "sessionCodeDescription",
            "sessions": "sessionCodeDescription",
            "instructionModeDescription": "instructionModeDescription",
            "instruction_mode": "instructionModeDescription",
            "mode": "instructionModeDescription",
            "location": "location",
            "locations": "location",
            "academicCareer": "academicCareer",
            "academic_level": "academicCareer",
            "level": "academicCareer",
        }

        actual_field = field_map.get(field.lower().replace(" ", "_"), field)

        index = get_index_for_term(term)
        client = get_opensearch_client()

        try:
            response = client.search(
                index=index,
                body={
                    "size": 0,
                    "aggs": {
                        "options": {
                            "terms": {
                                "field": actual_field,
                                "size": 500
                            }
                        }
                    }
                }
            )

            buckets = response.get("aggregations", {}).get("options", {}).get("buckets", [])

            if not buckets:
                return {
                    "term": format_term_description(term),
                    "field": field,
                    "message": f"No values found for field '{field}'. It may not exist or may be empty.",
                    "options": [],
                }

            options = [
                {"value": bucket["key"], "count": bucket["doc_count"]}
                for bucket in buckets
                if bucket["key"]  # Skip empty values
            ]

            return {
                "term": format_term_description(term),
                "field": field,
                "total_options": len(options),
                "options": options,
            }

        except Exception as e:
            return {"error": f"Query failed: {str(e)}"}

    return mcp


# =============================================================================
# Lambda Handler
# =============================================================================


def lambda_handler(event, context):
    """AWS Lambda handler function."""
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
