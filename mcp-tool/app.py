"""
MCP Tool - Current Time Server

A simple MCP server that provides the current time.
This serves as a template for building MCP tools that run in AWS Lambda.
"""

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP

# Try to import TransportSecuritySettings for DNS rebinding protection config
# This was added in a recent MCP SDK version
try:
    from mcp.server.transport_security import TransportSecuritySettings

    transport_security = TransportSecuritySettings(
        # Disable DNS rebinding protection for Lambda deployments
        # Lambda Function URLs have dynamic hostnames that won't match a static allowed list
        # Security is handled at the Lambda Function URL level with AWS IAM authentication
        enable_dns_rebinding_protection=False,
    )
except ImportError:
    # Older versions of MCP SDK don't have this setting
    transport_security = None

# Initialize the MCP server in stateless mode for Lambda compatibility
mcp_kwargs = {
    "name": "time-server",
    "instructions": "A simple MCP server that returns the current time in various formats and timezones.",
    "stateless_http": True,  # Required for Lambda/serverless environments
}

if transport_security is not None:
    mcp_kwargs["transport_security"] = transport_security

mcp = FastMCP(**mcp_kwargs)


@mcp.tool()
def get_current_time(timezone_name: str = "UTC") -> dict:
    """
    Get the current time in the specified timezone.

    Args:
        timezone_name: The timezone name (e.g., 'UTC', 'America/New_York', 'Europe/London').
                      Defaults to 'UTC'.

    Returns:
        A dictionary containing the current time in various formats.
    """
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        tz = timezone.utc
        timezone_name = "UTC"

    now = datetime.now(tz)

    return {
        "timezone": timezone_name,
        "iso8601": now.isoformat(),
        "unix_timestamp": int(now.timestamp()),
        "formatted": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "day_of_week": now.strftime("%A"),
    }


@mcp.tool()
def get_time_difference(timezone1: str = "UTC", timezone2: str = "America/New_York") -> dict:
    """
    Get the time difference between two timezones.

    Args:
        timezone1: The first timezone (default: UTC)
        timezone2: The second timezone (default: America/New_York)

    Returns:
        A dictionary containing the current time in both timezones and the offset.
    """
    try:
        tz1 = ZoneInfo(timezone1)
    except Exception:
        tz1 = timezone.utc
        timezone1 = "UTC"

    try:
        tz2 = ZoneInfo(timezone2)
    except Exception:
        tz2 = timezone.utc
        timezone2 = "UTC"

    now_utc = datetime.now(timezone.utc)
    time1 = now_utc.astimezone(tz1)
    time2 = now_utc.astimezone(tz2)

    offset1 = time1.utcoffset().total_seconds() / 3600
    offset2 = time2.utcoffset().total_seconds() / 3600
    difference = offset2 - offset1

    return {
        "timezone1": {
            "name": timezone1,
            "time": time1.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "utc_offset_hours": offset1,
        },
        "timezone2": {
            "name": timezone2,
            "time": time2.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "utc_offset_hours": offset2,
        },
        "difference_hours": difference,
    }


def lambda_handler(event, context):
    """
    AWS Lambda handler function.
    Uses Mangum to adapt the ASGI app for Lambda.
    Creates a fresh app instance for each invocation to avoid session manager reuse issues.
    """
    from mangum import Mangum

    # Create fresh app instance for each Lambda invocation
    # This is required because StreamableHTTPSessionManager can only run once per instance
    app = mcp.streamable_http_app()
    handler = Mangum(app, lifespan="off")
    return handler(event, context)


# For local development with uvicorn
if __name__ == "__main__":
    import uvicorn

    app = mcp.streamable_http_app()
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
