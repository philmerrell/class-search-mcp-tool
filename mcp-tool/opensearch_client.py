"""
OpenSearch client configuration and utilities.

Handles connection to AWS OpenSearch with IAM authentication.
Works both locally (with AWS profile) and in Lambda (with IAM role).
"""

import os
from functools import lru_cache
from typing import Optional

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth


# Configuration from environment variables
OPENSEARCH_HOST = os.environ.get(
    "OPENSEARCH_HOST",
    "search-opensearch-dev-01-t4a3j3mz3m5zedfbx2tnhkd2oi.us-west-2.es.amazonaws.com"
)
OPENSEARCH_REGION = os.environ.get("OPENSEARCH_REGION", "us-west-2")
AWS_PROFILE = os.environ.get("AWS_PROFILE", "dev-ai")


def get_aws_auth() -> AWS4Auth:
    """
    Get AWS4Auth for OpenSearch request signing.

    In Lambda: Uses the execution role credentials automatically.
    Locally: Uses the configured AWS profile.
    """
    # Check if running in Lambda (has AWS_LAMBDA_FUNCTION_NAME env var)
    if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        # In Lambda, use default credential chain (IAM role)
        session = boto3.Session()
    else:
        # Local development, use profile
        session = boto3.Session(profile_name=AWS_PROFILE)

    credentials = session.get_credentials()

    return AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        OPENSEARCH_REGION,
        "es",  # OpenSearch service
        session_token=credentials.token
    )


def get_opensearch_client() -> OpenSearch:
    """
    Create an OpenSearch client with AWS IAM authentication.

    Note: We create a new client for each request rather than caching,
    because AWS credentials can expire and need to be refreshed.
    """
    awsauth = get_aws_auth()

    return OpenSearch(
        hosts=[{"host": OPENSEARCH_HOST, "port": 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=30
    )


def get_index_for_term(term: str) -> str:
    """
    Get the OpenSearch index alias for a given term code.

    Term format: IYYT
    - I (1st digit): Institution (1 = Boise State)
    - YY (2nd-3rd digits): Two-digit year
    - T (4th digit): Semester (3 = Spring, 6 = Summer, 9 = Fall)

    Returns the index alias in format: {term}_classes_current
    """
    return f"{term}_classes_current"


def format_term_description(term: str) -> str:
    """Convert term code to human-readable description."""
    if len(term) != 4:
        return term

    year = f"20{term[1:3]}"
    semester_map = {"3": "Spring", "6": "Summer", "9": "Fall"}
    semester = semester_map.get(term[3], "Unknown")

    return f"{semester} {year}"


def validate_term(term: str) -> tuple[bool, str]:
    """
    Validate the term format.

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


# =============================================================================
# Filter Validation Helpers
# =============================================================================


def get_valid_values(client: OpenSearch, index: str, field: str, size: int = 500) -> list[str]:
    """
    Get all valid values for a keyword field via aggregation.

    Args:
        client: OpenSearch client
        index: Index to query
        field: Field name (will append .keyword if needed for text fields)
        size: Maximum number of values to return

    Returns:
        List of valid values for the field
    """
    response = client.search(
        index=index,
        body={
            "size": 0,
            "aggs": {
                "values": {
                    "terms": {
                        "field": field,
                        "size": size
                    }
                }
            }
        }
    )

    buckets = response.get("aggregations", {}).get("values", {}).get("buckets", [])
    return [bucket["key"] for bucket in buckets]


def fuzzy_match_value(
    input_value: str,
    valid_values: list[str],
    threshold: float = 0.6
) -> Optional[str]:
    """
    Find the best matching value from valid options.

    Matching strategy:
    1. Exact match (case-insensitive)
    2. Input is prefix of valid value
    3. Valid value is prefix of input (e.g., "CS" in "Computer Science")
    4. Word-based matching for multi-word inputs
    5. Simple similarity scoring

    Args:
        input_value: User-provided value
        valid_values: List of valid values
        threshold: Minimum similarity score (0-1)

    Returns:
        Best matching valid value, or None if no good match
    """
    if not input_value or not valid_values:
        return None

    input_lower = input_value.lower().strip()

    # Strategy 1: Exact match (case-insensitive)
    for valid in valid_values:
        if valid.lower() == input_lower:
            return valid

    # Strategy 2: Input is prefix of valid value
    for valid in valid_values:
        if valid.lower().startswith(input_lower):
            return valid

    # Strategy 3: Check abbreviation match
    # Common subject abbreviations: CS = Computer Science, MATH = Mathematics, etc.
    common_mappings = {
        "computer science": "CS",
        "mathematics": "MATH",
        "biology": "BIOL",
        "chemistry": "CHEM",
        "physics": "PHYS",
        "english": "ENGL",
        "history": "HIST",
        "psychology": "PSYC",
        "economics": "ECON",
        "political science": "POLS",
        "sociology": "SOC",
        "philosophy": "PHIL",
        "engineering": "ENGR",
        "music": "MUS",
        "art": "ART",
        "business": "BUS",
        "accounting": "ACCT",
        "marketing": "MKTG",
        "management": "MGT",
        "finance": "FIN",
        "communication": "COMM",
        "nursing": "NURS",
        "education": "EDUC",
        "kinesiology": "KINES",
    }

    if input_lower in common_mappings:
        abbrev = common_mappings[input_lower]
        if abbrev in valid_values:
            return abbrev

    # Strategy 4: Valid value contains input (for partial matches)
    for valid in valid_values:
        if input_lower in valid.lower():
            return valid

    # Strategy 5: Check if input words match valid value
    # e.g., "comp sci" might match "CS"
    input_words = set(input_lower.split())
    for valid in valid_values:
        valid_lower = valid.lower()
        # Check if all characters of valid are in input initials
        input_initials = "".join(w[0] for w in input_lower.split() if w)
        if valid_lower == input_initials:
            return valid

    # Strategy 6: Simple character overlap scoring (last resort)
    best_match = None
    best_score = 0

    for valid in valid_values:
        valid_lower = valid.lower()
        # Calculate Jaccard-like similarity on character sets
        input_chars = set(input_lower.replace(" ", ""))
        valid_chars = set(valid_lower)
        intersection = len(input_chars & valid_chars)
        union = len(input_chars | valid_chars)
        score = intersection / union if union > 0 else 0

        if score > best_score and score >= threshold:
            best_score = score
            best_match = valid

    return best_match


def validate_and_match_subject(
    client: OpenSearch,
    index: str,
    subject: str
) -> tuple[Optional[str], Optional[str]]:
    """
    Validate and fuzzy-match a subject code.

    Args:
        client: OpenSearch client
        index: Index to query
        subject: User-provided subject

    Returns:
        Tuple of (matched_subject, error_message)
        - If matched: (subject_code, None)
        - If not matched: (None, error_message_with_suggestions)
    """
    valid_subjects = get_valid_values(client, index, "subject")
    matched = fuzzy_match_value(subject, valid_subjects)

    if matched:
        return matched, None

    # No match - provide helpful suggestions
    # Find subjects that start with same letter
    first_char = subject[0].upper() if subject else ""
    suggestions = [s for s in valid_subjects if s.startswith(first_char)][:10]

    if suggestions:
        suggestion_str = ", ".join(suggestions)
        return None, f"Unknown subject '{subject}'. Similar subjects: {suggestion_str}"
    else:
        return None, f"Unknown subject '{subject}'. Use get_filter_options to see available subjects."


# =============================================================================
# Time Utilities
# =============================================================================


def time_to_minutes(time_str: str) -> Optional[int]:
    """
    Convert time string to minutes from midnight.

    Accepts formats: "9:00", "09:00", "9:00 AM", "14:30", "2:30 PM"

    Returns:
        Minutes from midnight, or None if parsing fails
    """
    if not time_str:
        return None

    time_str = time_str.strip().upper()

    # Check for AM/PM
    is_pm = "PM" in time_str
    is_am = "AM" in time_str
    time_str = time_str.replace("AM", "").replace("PM", "").strip()

    try:
        if ":" in time_str:
            parts = time_str.split(":")
            hours = int(parts[0])
            minutes = int(parts[1]) if len(parts) > 1 else 0
        else:
            hours = int(time_str)
            minutes = 0

        # Handle 12-hour format
        if is_pm and hours < 12:
            hours += 12
        elif is_am and hours == 12:
            hours = 0

        return hours * 60 + minutes
    except (ValueError, IndexError):
        return None


def minutes_to_time(minutes: int) -> str:
    """Convert minutes from midnight to readable time string."""
    hours = minutes // 60
    mins = minutes % 60

    if hours == 0:
        return f"12:{mins:02d} AM"
    elif hours < 12:
        return f"{hours}:{mins:02d} AM"
    elif hours == 12:
        return f"12:{mins:02d} PM"
    else:
        return f"{hours - 12}:{mins:02d} PM"
