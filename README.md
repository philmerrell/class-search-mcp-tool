# Boise State University Class Search MCP Tool

An MCP (Model Context Protocol) server that helps students and advisors search for classes at Boise State University. Deployed as a Docker container on AWS Lambda.

## Features

- **Smart Class Search**: Search by subject, instructor, schedule, and more
- **Schedule Conflict Detection**: Find classes that don't conflict with existing schedule
- **Gen-Ed Discovery**: Map informal terms like "gen ed" to actual requirement values
- **Fuzzy Matching**: Subject codes auto-convert ("Computer Science" -> "CS")
- **Real-time Availability**: Check seat availability and waitlist status

## Example Queries

### Explicit Queries (Direct Search)

**Basic Subject Searches**
- "Find CS classes for Spring 2026"
- "Show me online MATH classes"
- "What Biology classes are available?"

**Schedule-Based**
- "I need classes on Tuesday/Thursday mornings"
- "Find classes that meet after 5pm"
- "Show me Monday/Wednesday/Friday afternoon classes"

**Instructor**
- "What classes is Professor Vail teaching?"
- "Find classes taught by Smith"

**Section Comparison**
- "Show me all sections of CS 121"
- "Compare MATH 170 sections"

### Discovery-Required Queries (Uses suggest_filter_values First)

**Gen-Ed / Requirements**
- "I need classes that fulfill general education requirements"
- "Find courses that count toward my core requirements"
- "What classes satisfy the math gen-ed?"

**Cost/Materials**
- "Show me classes with free textbooks"
- "Find affordable course material classes"
- "I want classes with cheap books"

**Other Attributes**
- "Are there any honors sections available?"
- "Find service learning courses"

### Clarification-Required Queries (Agent Asks Follow-up Questions)

**Schedule Conflicts**
- "CS classes that don't conflict with my MWF 10am class"
  - *Agent should ask: "What time does your 10am class end?"*
- "Find MATH classes that won't overlap with my Tuesday 2pm seminar"
  - *Agent should ask: "What time does your seminar end? Does it also meet on Thursday?"*
- "I have classes at 9am and 2pm on Monday, what can I take in between?"
  - *Agent should ask for end times of both classes*

**Vague Availability**
- "I work mornings, what can I take?"
  - *Agent should ask: "What's the earliest you can start class? Which days do you work?"*
- "I need a class that fits my schedule"
  - *Agent should ask about constraints*

### Complex Multi-Constraint Queries

- "3-credit online classes that fulfill gen-ed requirements and have open seats"
  - *Should: discover gen-ed values, then search with filters*
- "Upper-division CS classes on Tuesday/Thursday that don't conflict with my MWF 10-11:15am class"
  - *Should: ask for clarification on conflict, then use check_schedule_conflicts with subject="CS", catalog_number="3*" or "4*"*
- "Affordable textbook classes in the Business department with evening options"
  - *Should: discover affordable textbook attribute, then search*
- "Find a 3-credit honors section of any math class that meets in the afternoon"
  - *Should: search with multiple filters*

### Advisor-Focused Scenarios

- "Student needs CS 121 but it's full - what alternatives exist?"
  - *Should: show other intro CS options or check waitlist*
- "Show me all 100-level classes in Computer Science with availability"
  - *Should: search with catalog_number="1*", has_open_seats=true*
- "What graduate courses are available in the Engineering department?"
  - *Should: search with academic_level="GRAD"*
- "Find hybrid nursing courses for a student who can only come to campus twice a week"
  - *Should: search with instruction_mode="Hybrid", possibly with day constraints*

## Available Tools

| Tool | Purpose |
|------|---------|
| `search_classes` | Main search with filters (subject, time, mode, etc.) |
| `find_classes_by_schedule` | Find classes within available time windows |
| `check_schedule_conflicts` | Find classes that don't conflict with existing schedule |
| `search_by_instructor` | Find all classes by a professor |
| `compare_sections` | Compare all sections of a specific course |
| `get_class_details` | Get full details for a specific class |
| `check_availability` | Quick seat/waitlist status check |
| `suggest_filter_values` | Map informal terms to system values |
| `get_filter_options` | Discover all valid values for a field |

## Term Codes

- Spring 2026 = "1263"
- Summer 2026 = "1266"
- Fall 2026 = "1269"
- Pattern: `1 + YY + semester` (3=Spring, 6=Summer, 9=Fall)

## Quick Start

### Local Development

```bash
# Start the MCP server locally
docker-compose up --build

# The server will be available at http://localhost:8000
```

### Deploy to AWS

1. Fork this repository
2. Set up AWS OIDC provider for GitHub Actions (see [CLAUDE.md](CLAUDE.md) for details)
3. Add GitHub Secret:
   - `AWS_DEPLOY_ROLE_ARN`: IAM role ARN for GitHub Actions to assume
4. Push to `main` branch to trigger deployment

### Manual Deployment

```bash
# Install CDK dependencies
cd infrastructure && npm install && cd ..

# Set environment variables
export CDK_AWS_ACCOUNT_ID="your-account-id"
export CDK_AWS_REGION="us-west-2"

# Build and deploy
./scripts/stack-mcp-lambda/build-docker.sh
./scripts/stack-mcp-lambda/push-docker.sh
./scripts/stack-mcp-lambda/deploy.sh
```

## Project Structure

```
├── mcp-tool/                    # Python MCP server
│   ├── app.py                   # Tool implementation
│   ├── opensearch_client.py     # OpenSearch connection & utilities
│   ├── Dockerfile               # Lambda container
│   └── Dockerfile.local         # Local dev container
├── infrastructure/              # CDK infrastructure
│   ├── lib/mcp-lambda-stack.ts  # Lambda + ECR stack
│   └── bin/app.ts               # CDK entry point
├── scripts/                     # CI/CD scripts
└── .github/workflows/           # GitHub Actions
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `CDK_PROJECT_PREFIX` | Resource naming prefix | `mcp-docker-lambda` |
| `CDK_AWS_REGION` | AWS region | `us-west-2` |
| `CDK_LAMBDA_MEMORY_MB` | Lambda memory | `512` |
| `CDK_LAMBDA_TIMEOUT_SECONDS` | Lambda timeout | `30` |

See [CLAUDE.md](CLAUDE.md) for detailed documentation.

## License

MIT
