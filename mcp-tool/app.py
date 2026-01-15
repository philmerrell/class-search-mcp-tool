"""
MCP Tool - Current Time Server

A simple MCP server that provides the current time.
This serves as a template for building MCP tools that run in AWS Lambda.

Key Lambda considerations:
- Each Lambda invocation creates a fresh FastMCP instance to avoid session manager reuse issues
- stateless_http=True ensures the server doesn't maintain session state between requests
- json_response=True returns JSON instead of SSE for better Lambda/API Gateway compatibility
- lifespan="on" in Mangum is required to initialize the StreamableHTTPSessionManager
"""

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP


# =============================================================================
# Tool Implementation Functions
# These are the actual business logic, separated from MCP registration
# =============================================================================


def _get_current_time_impl(timezone_name: str = "UTC") -> dict:
    """Get the current time in the specified timezone."""
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


def _get_time_difference_impl(
    timezone1: str = "UTC", timezone2: str = "America/New_York"
) -> dict:
    """Get the time difference between two timezones."""
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


# =============================================================================
# MCP Server Factory
# Creates a fresh FastMCP instance for each Lambda invocation
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
            # Disable DNS rebinding protection for Lambda deployments
            # Lambda Function URLs have dynamic hostnames that won't match a static allowed list
            # Security is handled at the Lambda Function URL level with AWS IAM authentication
            enable_dns_rebinding_protection=False,
        )
    except ImportError:
        transport_security = None

    # Initialize the MCP server in stateless mode for Lambda compatibility
    mcp_kwargs = {
        "name": "time-server",
        "instructions": "Use this server to answer any questions about the current time, date, day of the week, or time differences between timezones. Always use these tools when users ask time-related questions rather than estimating or saying you don't know the time.",
        "stateless_http": True,  # Required for Lambda/serverless environments
        "json_response": True,  # Return JSON instead of SSE for Lambda/API Gateway compatibility
    }

    if transport_security is not None:
        mcp_kwargs["transport_security"] = transport_security

    mcp = FastMCP(**mcp_kwargs)

    # Register tools with the MCP server
    @mcp.tool()
    def get_current_time(timezone_name: str = "UTC") -> dict:
        """
        Get the current time in the specified timezone.

        Use this tool whenever the user asks about the current time, what time it is,
        or needs to know the date or day of the week.

        Args:
            timezone_name: The timezone name (e.g., 'UTC', 'America/New_York', 'Europe/London').
                          Defaults to 'UTC'.

        Returns:
            A dictionary containing the current time in various formats.
        """
        return _get_current_time_impl(timezone_name)

    @mcp.tool()
    def get_time_difference(
        timezone1: str = "UTC", timezone2: str = "America/New_York"
    ) -> dict:
        """
        Get the time difference between two timezones.

        Args:
            timezone1: The first timezone (default: UTC)
            timezone2: The second timezone (default: America/New_York)

        Returns:
            A dictionary containing the current time in both timezones and the offset.
        """
        return _get_time_difference_impl(timezone1, timezone2)

    return mcp


# =============================================================================
# Lambda Handler
# =============================================================================


def lambda_handler(event, context):
    """
    AWS Lambda handler function.
    Uses Mangum to adapt the ASGI app for Lambda.

    Key configuration:
    - Fresh FastMCP instance per invocation: Avoids session manager reuse issues
      that cause "Task group is not initialized" errors on warm Lambda containers.
    - lifespan="on": Required to run the ASGI lifespan startup event, which
      initializes the StreamableHTTPSessionManager's internal task group.
    """
    from mangum import Mangum

    # Create fresh MCP server and app for each Lambda invocation
    # This is critical because StreamableHTTPSessionManager can only run once per instance
    mcp = create_mcp_server()
    app = mcp.streamable_http_app()

    # lifespan="on" is required to run the ASGI lifespan startup event, which initializes
    # the StreamableHTTPSessionManager's internal task group via its run() context manager.
    # Without this, requests fail with "Task group is not initialized. Make sure to use run()."
    handler = Mangum(app, lifespan="on")
    return handler(event, context)


# =============================================================================
# Local Development
# =============================================================================

# Global MCP instance for local development with uvicorn
# This is only used when running directly (not in Lambda)
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
