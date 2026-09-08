"""Business rules for complaints, priority, status workflow, and summaries.

This module does not read the keyboard or print menus. It works with
dictionaries, lists, and sets so the same functions can be used by the
user interface and by automated tests.
"""

from __future__ import annotations

from datetime import datetime

DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

CATEGORIES = [
    "Road",
    "Water",
    "Electricity",
    "Waste",
    "Drainage",
    "Safety",
    "Noise",
    "Public Property",
    "Other",
]

IMPACT_LEVELS = ["Low", "Medium", "High"]
URGENCY_LEVELS = ["Low", "Medium", "High"]
PRIORITY_LEVELS = ["Low", "Medium", "High", "Critical"]
STATUS_LEVELS = ["Submitted", "Under Review", "In Progress", "Resolved"]

# Low = 1, Medium = 2, High = 3
LEVEL_SCORES = {"Low": 1, "Medium": 2, "High": 3}

# Age must be greater than this many days for an unresolved request to be overdue.
OVERDUE_THRESHOLDS = {
    "Critical": 1,
    "High": 3,
    "Medium": 7,
    "Low": 14,
}

# Allowed next statuses for each current status.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "Submitted": {"Under Review"},
    "Under Review": {"In Progress"},
    "In Progress": {"Resolved"},
    "Resolved": {"Under Review"},  # reopen only, and only with a valid reason
}

REOPEN_STATUS_FROM = "Resolved"
REOPEN_STATUS_TO = "Under Review"
MIN_DESCRIPTION_LENGTH = 10
MIN_REOPEN_REASON_LENGTH = 5


def format_datetime(value: datetime) -> str:
    """Return a timestamp string in the project's stored format.

    Parameters:
        value: A datetime object.

    Returns:
        A string such as '2026-08-25 10:30:00'.
    """
    return value.strftime(DATETIME_FORMAT)


def parse_datetime(value: str) -> datetime | None:
    """Convert a stored timestamp string into a datetime object.

    Parameters:
        value: A timestamp string.

    Returns:
        A datetime object, or None if the value cannot be parsed.
    """
    text = (value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, DATETIME_FORMAT)
    except ValueError:
        return None


def normalize_text(value: str) -> str:
    """Prepare text for comparison by ignoring case and extra spaces.

    Parameters:
        value: Any user-entered or stored string.

    Returns:
        A lowercase string with surrounding and repeated spaces removed.
    """
    return " ".join((value or "").strip().lower().split())


def canonicalize_level(value: str, allowed: list[str]) -> str | None:
    """Return the official spelling of a level if it is valid.

    Parameters:
        value: User-entered text such as 'high'.
        allowed: Official values such as ['Low', 'Medium', 'High'].

    Returns:
        The matching official value, or None if the input is not allowed.
    """
    lookup = {item.lower(): item for item in allowed}
    return lookup.get((value or "").strip().lower())


def generate_request_id(
    requests: dict[str, dict[str, str]],
    current_datetime: datetime | None = None,
) -> str:
    """Create a unique ID in the format CSR-YYYYMMDD-0001.

    The daily sequence is one higher than the largest ID already stored
    for that date. The function also checks the dictionary so an existing
    complaint is never overwritten.

    Parameters:
        requests: Loaded complaints keyed by request ID.
        current_datetime: Timestamp used for the date portion. Defaults to now.

    Returns:
        A unique request ID string.
    """
    when = current_datetime or datetime.now()
    date_part = when.strftime("%Y%m%d")
    prefix = f"CSR-{date_part}-"

    highest_sequence = 0
    for request_id in requests:
        if not request_id.startswith(prefix):
            continue
        sequence_text = request_id[len(prefix) :]
        if sequence_text.isdigit():
            sequence_number = int(sequence_text)
            if sequence_number > highest_sequence:
                highest_sequence = sequence_number

    next_sequence = highest_sequence + 1
    candidate = f"{prefix}{next_sequence:04d}"
    while candidate in requests:
        next_sequence += 1
        candidate = f"{prefix}{next_sequence:04d}"
    return candidate


def calculate_priority(impact: str, urgency: str) -> str:
    """Assign Low, Medium, High, or Critical from impact and urgency scores.

    Scoring:
        Low = 1, Medium = 2, High = 3
        total = impact score + urgency score
        2 or 3 -> Low
        4 -> Medium
        5 -> High
        6 -> Critical

    Critical is therefore used only when both impact and urgency are High.

    Parameters:
        impact: Low, Medium, or High.
        urgency: Low, Medium, or High.

    Returns:
        The assigned priority label.

    Raises:
        ValueError: If impact or urgency is not a valid level.
    """
    official_impact = canonicalize_level(impact, IMPACT_LEVELS)
    official_urgency = canonicalize_level(urgency, URGENCY_LEVELS)
    if official_impact is None or official_urgency is None:
        raise ValueError("Impact and urgency must be Low, Medium, or High.")

    total = LEVEL_SCORES[official_impact] + LEVEL_SCORES[official_urgency]
    if total <= 3:
        return "Low"
    if total == 4:
        return "Medium"
    if total == 5:
        return "High"
    return "Critical"


def explain_priority(impact: str, urgency: str) -> str:
    """Build a short, transparent explanation of a priority decision.

    Parameters:
        impact: Low, Medium, or High.
        urgency: Low, Medium, or High.

    Returns:
        A multi-line explanation including scores and the assigned priority.
    """
    official_impact = canonicalize_level(impact, IMPACT_LEVELS) or impact
    official_urgency = canonicalize_level(urgency, URGENCY_LEVELS) or urgency
    impact_score = LEVEL_SCORES[official_impact]
    urgency_score = LEVEL_SCORES[official_urgency]
    total = impact_score + urgency_score
    priority = calculate_priority(official_impact, official_urgency)
    return (
        f"Impact: {official_impact} ({impact_score})\n"
        f"Urgency: {official_urgency} ({urgency_score})\n"
        f"Total score: {total}\n"
        f"Assigned priority: {priority}"
    )


def find_potential_duplicate(
    requests: dict[str, dict[str, str]],
    category: str,
    location: str,
    description: str,
) -> str | None:
    """Find an unresolved request that matches category, location, and description.

    Matching ignores capitalization and extra spaces. Resolved requests are
    ignored because the same problem may return later as a new complaint.

    Parameters:
        requests: Loaded complaints keyed by request ID.
        category: New request category.
        location: New request location.
        description: New request description.

    Returns:
        The matching request ID, or None if no potential duplicate exists.
    """
    target = (
        normalize_text(category),
        normalize_text(location),
        normalize_text(description),
    )
    if not all(target):
        return None

    for request_id, record in requests.items():
        if record.get("status") == "Resolved":
            continue
        current = (
            normalize_text(record.get("category", "")),
            normalize_text(record.get("location", "")),
            normalize_text(record.get("description", "")),
        )
        if current == target:
            return request_id
    return None


def add_request(
    requests: dict[str, dict[str, str]],
    category: str,
    location: str,
    description: str,
    impact: str,
    urgency: str,
    current_datetime: datetime | None = None,
    history: list[dict[str, str]] | None = None,
) -> tuple[bool, str, dict[str, str] | None]:
    """Validate input, create a unique complaint, and store it in the dictionary.

    Parameters:
        requests: Loaded complaints keyed by request ID. Updated in place.
        category: Complaint category.
        location: Place where the problem was observed.
        description: Details of the problem.
        impact: Low, Medium, or High.
        urgency: Low, Medium, or High.
        current_datetime: Optional timestamp used for ID and dates.
        history: Optional status-history list to receive the creation record.

    Returns:
        A tuple of (success flag, message, new record or None).
    """
    clean_category = (category or "").strip()
    clean_location = (location or "").strip()
    clean_description = (description or "").strip()
    official_impact = canonicalize_level(impact, IMPACT_LEVELS)
    official_urgency = canonicalize_level(urgency, URGENCY_LEVELS)

    if not clean_category:
        return False, "Category cannot be blank.", None
    if not clean_location:
        return False, "Location cannot be blank.", None
    if not clean_description:
        return False, "Description cannot be blank.", None
    if len(clean_description) < MIN_DESCRIPTION_LENGTH:
        return False, "Description must contain at least 10 characters.", None
    if official_impact is None:
        return False, "Impact must be Low, Medium, or High.", None
    if official_urgency is None:
        return False, "Urgency must be Low, Medium, or High.", None

    when = current_datetime or datetime.now()
    timestamp = format_datetime(when)
    request_id = generate_request_id(requests, when)
    if request_id in requests:
        return False, f"Generated ID {request_id} already exists. The request was not saved.", None

    try:
        priority = calculate_priority(official_impact, official_urgency)
    except ValueError as error:
        return False, str(error), None

    record = {
        "request_id": request_id,
        "category": clean_category,
        "location": clean_location,
        "description": clean_description,
        "impact": official_impact,
        "urgency": official_urgency,
        "priority": priority,
        "created_at": timestamp,
        "status": "Submitted",
        "updated_at": timestamp,
        "resolved_at": "",
    }
    requests[request_id] = record

    if history is not None:
        history.append(
            {
                "request_id": request_id,
                "old_status": "",
                "new_status": "Submitted",
                "changed_at": timestamp,
                "reason": "Request created",
            }
        )

    return True, f"Request {request_id} was created with {priority} priority.", record


def search_requests(
    requests: dict[str, dict[str, str]],
    request_id: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    location: str | None = None,
    status: str | None = None,
) -> list[dict[str, str]]:
    """Find requests that match all of the provided filters.

    Text filters are case-insensitive. Location matching allows partial text.
    Filters that are None or blank are ignored.

    Parameters:
        requests: Loaded complaints keyed by request ID.
        request_id: Exact ID to find.
        category: Category to match.
        priority: Priority to match.
        location: Location text to find inside the stored location.
        status: Status to match.

    Returns:
        A list of matching request dictionaries, sorted by request ID.
    """
    wanted_id = (request_id or "").strip().lower()
    wanted_category = (category or "").strip().lower()
    wanted_priority = (priority or "").strip().lower()
    wanted_location = (location or "").strip().lower()
    wanted_status = (status or "").strip().lower()

    matches: list[dict[str, str]] = []
    for record in requests.values():
        if wanted_id and record.get("request_id", "").lower() != wanted_id:
            continue
        if wanted_category and record.get("category", "").lower() != wanted_category:
            continue
        if wanted_priority and record.get("priority", "").lower() != wanted_priority:
            continue
        if wanted_location and wanted_location not in record.get("location", "").lower():
            continue
        if wanted_status and record.get("status", "").lower() != wanted_status:
            continue
        matches.append(record)

    matches.sort(key=lambda item: item.get("request_id", ""))
    return matches


def is_valid_transition(
    current_status: str,
    new_status: str,
    reason: str = "",
) -> tuple[bool, str]:
    """Check whether a status change is allowed.

    Normal workflow:
        Submitted -> Under Review -> In Progress -> Resolved

    The only justified backward change is reopening:
        Resolved -> Under Review
    Reopening requires a non-empty reason of at least five characters.

    Parameters:
        current_status: The request's current status.
        new_status: The requested next status.
        reason: Optional explanation, required when reopening.

    Returns:
        A tuple of (is_allowed, explanation).
    """
    current = canonicalize_level(current_status, STATUS_LEVELS)
    target = canonicalize_level(new_status, STATUS_LEVELS)

    if current is None:
        return False, f"Unknown current status: {current_status}."
    if target is None:
        return False, f"Unknown status: {new_status}."
    if current == target:
        return False, f"The request is already {current}."

    allowed_next = ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed_next:
        allowed_text = ", ".join(sorted(allowed_next)) if allowed_next else "none"
        return False, (
            f"Cannot change status from {current} to {target}. "
            f"Allowed next status: {allowed_text}."
        )

    if current == REOPEN_STATUS_FROM and target == REOPEN_STATUS_TO:
        clean_reason = (reason or "").strip()
        if len(clean_reason) < MIN_REOPEN_REASON_LENGTH:
            return False, (
                "A resolved request can be reopened only with a reason "
                "of at least five characters."
            )

    return True, f"Status can change from {current} to {target}."


def update_status(
    requests: dict[str, dict[str, str]],
    request_id: str,
    new_status: str,
    reason: str = "",
    history: list[dict[str, str]] | None = None,
    current_datetime: datetime | None = None,
) -> tuple[bool, str, dict[str, str] | None]:
    """Apply a valid status change and record it in the history list.

    A successful update changes status and updated_at. Moving to Resolved
    stores resolved_at. Reopening clears resolved_at.

    Parameters:
        requests: Loaded complaints keyed by request ID. Updated in place.
        request_id: ID of the request to update.
        new_status: Requested next status.
        reason: Optional reason; required when reopening.
        history: Optional list that receives the history record.
        current_datetime: Optional timestamp for the change.

    Returns:
        A tuple of (success flag, message, history record or None).
    """
    clean_id = (request_id or "").strip()
    if not clean_id:
        return False, "Request ID cannot be blank.", None
    if clean_id not in requests:
        # Allow a case-insensitive exact match for convenience.
        matched_id = next(
            (key for key in requests if key.lower() == clean_id.lower()),
            None,
        )
        if matched_id is None:
            return False, f"No request was found with ID {clean_id}.", None
        clean_id = matched_id

    record = requests[clean_id]
    current_status = record.get("status", "")
    allowed, message = is_valid_transition(current_status, new_status, reason)
    if not allowed:
        return False, message, None

    official_new_status = canonicalize_level(new_status, STATUS_LEVELS)
    if official_new_status is None:
        return False, f"Unknown status: {new_status}.", None

    when = current_datetime or datetime.now()
    timestamp = format_datetime(when)
    old_status = current_status
    record["status"] = official_new_status
    record["updated_at"] = timestamp
    if official_new_status == "Resolved":
        record["resolved_at"] = timestamp
    elif old_status == "Resolved":
        record["resolved_at"] = ""

    history_record = {
        "request_id": clean_id,
        "old_status": old_status,
        "new_status": official_new_status,
        "changed_at": timestamp,
        "reason": (reason or "").strip(),
    }
    if history is not None:
        history.append(history_record)

    return True, f"Request {clean_id} changed from {old_status} to {official_new_status}.", history_record


def request_age_days(record: dict[str, str], as_of: datetime | None = None) -> float | None:
    """Return how many days old a request is at the given time.

    Parameters:
        record: A complaint dictionary.
        as_of: Comparison time. Defaults to now.

    Returns:
        Age in days as a float, or None if the created date is invalid.
    """
    created = parse_datetime(record.get("created_at", ""))
    if created is None:
        return None
    moment = as_of or datetime.now()
    return (moment - created).total_seconds() / 86400.0


def find_overdue_requests(
    requests: dict[str, dict[str, str]],
    as_of: datetime | None = None,
) -> list[dict[str, str | float]]:
    """Return unresolved requests whose age is greater than their priority threshold.

    Thresholds:
        Critical: 1 day
        High: 3 days
        Medium: 7 days
        Low: 14 days

    Resolved requests are never overdue.

    Parameters:
        requests: Loaded complaints keyed by request ID.
        as_of: Comparison time. Defaults to now.

    Returns:
        A list of dictionaries containing overdue details.
    """
    moment = as_of or datetime.now()
    overdue: list[dict[str, str | float]] = []

    for record in requests.values():
        if record.get("status") == "Resolved":
            continue
        priority = record.get("priority", "")
        if priority not in OVERDUE_THRESHOLDS:
            continue
        age_days = request_age_days(record, moment)
        if age_days is None:
            continue
        threshold = OVERDUE_THRESHOLDS[priority]
        if age_days > threshold:
            overdue.append(
                {
                    "request_id": record.get("request_id", ""),
                    "priority": priority,
                    "status": record.get("status", ""),
                    "created_at": record.get("created_at", ""),
                    "age_days": age_days,
                    "threshold_days": threshold,
                    "days_overdue": age_days - threshold,
                }
            )

    overdue.sort(key=lambda item: str(item.get("request_id", "")))
    return overdue


def _count_by_field(requests: dict[str, dict[str, str]], field_name: str) -> dict[str, int]:
    """Count how many requests have each value of a chosen field."""
    counts: dict[str, int] = {}
    for record in requests.values():
        value = record.get(field_name, "") or "(blank)"
        counts[value] = counts.get(value, 0) + 1
    return counts


def summarize_requests(
    requests: dict[str, dict[str, str]],
    as_of: datetime | None = None,
) -> dict[str, int | float | None | dict[str, int]]:
    """Build management counts and the average resolution time.

    Every status other than Resolved is treated as unresolved. Average
    resolution time is None when no resolved requests can be measured.

    Parameters:
        requests: Loaded complaints keyed by request ID.
        as_of: Comparison time used for overdue counting.

    Returns:
        A dictionary of summary values and count dictionaries.
    """
    moment = as_of or datetime.now()
    total = len(requests)
    resolved = 0
    high_priority = 0
    critical_priority = 0
    resolution_days: list[float] = []

    for record in requests.values():
        if record.get("status") == "Resolved":
            resolved += 1
            created = parse_datetime(record.get("created_at", ""))
            finished = parse_datetime(record.get("resolved_at", ""))
            if created is not None and finished is not None:
                resolution_days.append((finished - created).total_seconds() / 86400.0)
        if record.get("priority") == "High":
            high_priority += 1
        if record.get("priority") == "Critical":
            critical_priority += 1

    overdue_count = len(find_overdue_requests(requests, moment))
    average: float | None
    if resolution_days:
        average = sum(resolution_days) / len(resolution_days)
    else:
        average = None

    return {
        "total": total,
        "unresolved": total - resolved,
        "resolved": resolved,
        "overdue": overdue_count,
        "high_priority": high_priority,
        "critical_priority": critical_priority,
        "by_category": _count_by_field(requests, "category"),
        "by_status": _count_by_field(requests, "status"),
        "by_priority": _count_by_field(requests, "priority"),
        "average_resolution_days": average,
    }


def history_for_request(
    history: list[dict[str, str]],
    request_id: str,
) -> list[dict[str, str]]:
    """Return status-history rows for one request ID.

    Parameters:
        history: Complete status-history list.
        request_id: Request ID to match.

    Returns:
        Matching history records in the original stored order.
    """
    wanted = (request_id or "").strip().lower()
    return [row for row in history if row.get("request_id", "").lower() == wanted]
