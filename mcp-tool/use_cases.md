# Student Use Cases

## Schedule Building

**Explicit queries (direct tool call):**
- "Find classes that meet on Tuesday/Thursday mornings" -> `find_classes_by_schedule`
- "CS classes available MWF after 2pm" -> `search_classes` with days + start_time

**Ambiguous queries (require clarification or discovery):**
- "CS classes that don't conflict with my MWF 10am class"
  - Agent should ASK: "What time does your class end?"
  - Then use: `check_schedule_conflicts` with complete time block
- "Show me 3-credit online classes that fulfill general ed requirements"
  - Agent should FIRST: `suggest_filter_values(keyword="gen ed")`
  - Then use: `search_classes` with discovered attribute values

## Course Discovery

- "What classes is Professor Smith teaching next semester?" -> `search_by_instructor`
- "Find introductory programming classes for someone with no experience" -> `search_classes(query="introduction programming")`
- "What electives are available in the Business department?" -> `search_classes(subject="BUS")`

## Availability & Planning

- "Which sections of MATH 170 still have open seats?" -> `compare_sections`
- "Are there any evening sections of Chemistry lab?" -> `search_classes(subject="CHEM", meeting_time="evening")`
- "Find classes with low enrollment" -> `search_classes` (smaller class sizes)

## Requirement Fulfillment

**These require discovery first:**
- "What classes fulfill the Foundations of Mathematics requirement?"
  - Use: `get_filter_options(field="attributes")` or `suggest_filter_values(keyword="foundations math")`
  - Then: `search_classes(course_attribute="Foundations of Mathematics")`
- "Show me honors sections available this term" -> `search_classes(requirement_designation="HON")`
- "Find service learning courses" -> `search_classes` with service learning attribute

## Advisor Use Cases

### Helping Students Find Alternatives

- "Student needs CS 121 but it's full--what other intro CS options exist?" -> `search_classes(subject="CS", catalog_number="1*")`
- "Find all sections of this course across different times/instructors" -> `compare_sections`
- "What graduate-level courses are cross-listed with undergrad?" -> `search_classes(academic_level="GRAD")`

### Analytics & Planning

- "Which CS courses have the most available seats?" -> `search_classes(subject="CS", has_open_seats=true)`
- "How many sections of Calculus are offered?" -> `compare_sections(subject="MATH", catalog_number="170")`
- "What's the average class size in the Biology department?" -> aggregate query

### Complex Queries

- "Find upper-division (300-400 level) CS classes that meet in the afternoon"
  -> `search_classes(subject="CS", catalog_number="3*", meeting_time="afternoon")`
- "Show hybrid courses in the nursing program"
  -> `search_classes(subject="NURS", instruction_mode="Hybrid")`
- "What courses have prerequisites I should know about?"
  -> `get_class_details` for specific classes

---

## Query Classification Guide

### Explicit Queries (Ready to Search)
These have specific, known filter values:
- "CS 121 sections" -> `compare_sections`
- "Online MATH classes" -> `search_classes`
- "Professor Smith's classes" -> `search_by_instructor`
- "Tuesday/Thursday morning classes" -> `find_classes_by_schedule`

### Discovery-Required Queries
These use informal language that needs mapping:
- "gen ed classes" -> `suggest_filter_values(keyword="gen ed")` first
- "affordable textbook courses" -> `suggest_filter_values(keyword="cheap textbooks")` first
- "core requirements" -> `suggest_filter_values(keyword="core")` first

### Clarification-Required Queries
These are missing required information:
- "doesn't conflict with my 10am class" -> ASK for days and end time
- "fits my schedule" -> ASK what times/days work
- "classes I can take" -> ASK about constraints

---

## Tool Selection Matrix

| Query Pattern | Tool | Notes |
|--------------|------|-------|
| Schedule conflicts | `check_schedule_conflicts` | Requires complete time blocks |
| Time availability | `find_classes_by_schedule` | Student specifies available times |
| Subject + filters | `search_classes` | Main search tool |
| Compare sections | `compare_sections` | Same course, different sections |
| Professor lookup | `search_by_instructor` | Partial name match |
| Class details | `get_class_details` | After finding class number |
| Seat availability | `check_availability` | Quick status check |
| Discover values | `get_filter_options` | See all valid values |
| Map keywords | `suggest_filter_values` | "gen ed" -> actual values |
