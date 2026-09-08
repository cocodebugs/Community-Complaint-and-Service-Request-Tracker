"""Command-line menus, input validation, and display for the tracker.

This module talks to the user. Business rules stay in logic.py and file
work stays in storage.py.
"""

from __future__ import annotations

from pathlib import Path

from complaint_tracker.logic import (
    CATEGORIES,
    IMPACT_LEVELS,
    PRIORITY_LEVELS,
    STATUS_LEVELS,
    URGENCY_LEVELS,
    add_request,
    explain_priority,
    find_overdue_requests,
    find_potential_duplicate,
    history_for_request,
    search_requests,
    summarize_requests,
    update_status,
)
from complaint_tracker.storage import (
    DEFAULT_HISTORY_PATH,
    DEFAULT_REQUESTS_PATH,
    initialize_data_files,
    load_requests,
    load_status_history,
    save_requests,
    save_status_history,
)

MENU_OPTIONS = {
    "1": "Create a new request",
    "2": "Search and filter requests",
    "3": "Update request status",
    "4": "View all requests",
    "5": "View overdue requests",
    "6": "View management summary",
    "7": "View status history",
    "0": "Exit",
}

SEARCH_MENU_OPTIONS = {
    "1": "Search by request ID",
    "2": "Filter by category",
    "3": "Filter by priority",
    "4": "Filter by location",
    "5": "Filter by status",
    "6": "Combine several filters",
    "7": "Show all requests",
    "0": "Return to main menu",
}


def run_app(
    requests_path: Path | str | None = None,
    history_path: Path | str | None = None,
) -> None:
    """Load saved data and run the main menu until the user exits.

    Parameters:
        requests_path: Optional CSV path used instead of the default file.
        history_path: Optional history CSV path used instead of the default file.
    """
    request_file = Path(requests_path) if requests_path else DEFAULT_REQUESTS_PATH
    history_file = Path(history_path) if history_path else DEFAULT_HISTORY_PATH

    print()
    print("Loading Community Complaint and Service Request Tracker...")
    startup_messages = initialize_data_files(request_file, history_file)
    for message in startup_messages:
        print(f"  {message}")

    requests, request_warnings = load_requests(request_file)
    history, history_warnings = load_status_history(history_file)
    for warning in request_warnings + history_warnings:
        print(f"  Warning: {warning}")
    print(f"Loaded {len(requests)} request(s) and {len(history)} history record(s).")

    while True:
        _print_main_menu()
        choice = _prompt_text("Enter your choice")
        if choice is None:
            print("\nNo more input was available. Exiting.")
            break

        if choice == "0":
            print("Thank you for using the Community Complaint Tracker. Goodbye.")
            break
        if choice == "1":
            _create_request(requests, history, request_file, history_file)
        elif choice == "2":
            _search_and_filter(requests)
        elif choice == "3":
            _update_request_status(requests, history, request_file, history_file)
        elif choice == "4":
            _display_request_table(list(requests.values()), "All requests")
        elif choice == "5":
            _show_overdue(requests)
        elif choice == "6":
            _show_summary(requests)
        elif choice == "7":
            _show_history(history, requests)
        else:
            print("That was not a valid menu choice. Please enter a number from the menu.")


def _print_main_menu() -> None:
    """Display the main application menu."""
    print()
    print("================================================")
    print(" COMMUNITY COMPLAINT AND SERVICE REQUEST TRACKER")
    print("================================================")
    for key, label in MENU_OPTIONS.items():
        print(f"{key}. {label}")


def _prompt_text(label: str) -> str | None:
    """Read one line of input. Returns None on end-of-file.

    Parameters:
        label: Prompt shown to the user.

    Returns:
        The stripped input string, or None if input is not available.
    """
    try:
        return input(f"{label}: ").strip()
    except EOFError:
        return None
    except KeyboardInterrupt:
        print("\nInput cancelled.")
        return ""


def _prompt_required(label: str, minimum_length: int = 1) -> str | None:
    """Keep asking until the user enters text of the required length.

    Parameters:
        label: Prompt shown to the user.
        minimum_length: Smallest allowed number of characters.

    Returns:
        Valid text, an empty string if the user cancelled, or None on EOF.
    """
    while True:
        value = _prompt_text(label)
        if value is None:
            return None
        if len(value) >= minimum_length:
            return value
        if minimum_length <= 1:
            print("This field cannot be blank. Please try again.")
        else:
            print(f"Please enter at least {minimum_length} characters.")


def _prompt_yes_no(question: str) -> bool | None:
    """Ask a yes/no question. Returns True, False, or None on EOF."""
    while True:
        answer = _prompt_text(f"{question} (y/n)")
        if answer is None:
            return None
        lowered = answer.lower()
        if lowered in {"y", "yes"}:
            return True
        if lowered in {"n", "no"}:
            return False
        print("Please enter y or n.")


def _prompt_from_list(title: str, options: list[str], allow_other: bool = False) -> str | None:
    """Let the user pick an item by number.

    Parameters:
        title: Heading shown above the numbered list.
        options: Values the user may choose.
        allow_other: If True and the last option is Other, ask for custom text.

    Returns:
        The chosen value, empty string if cancelled, or None on EOF.
    """
    print()
    print(title)
    for index, option in enumerate(options, start=1):
        print(f"  {index}. {option}")

    while True:
        choice = _prompt_text("Enter the number")
        if choice is None:
            return None
        if not choice.isdigit():
            print("Please enter a number from the list.")
            continue
        number = int(choice)
        if number < 1 or number > len(options):
            print("That number is not in the list. Please try again.")
            continue
        selected = options[number - 1]
        if allow_other and selected == "Other":
            custom = _prompt_required("Enter a custom category")
            if custom is None:
                return None
            if custom == "":
                return ""
            return custom
        return selected


def _save_all(
    requests: dict[str, dict[str, str]],
    history: list[dict[str, str]],
    request_file: Path,
    history_file: Path,
) -> None:
    """Save both CSV files and report any file error without crashing."""
    saved_requests, request_message = save_requests(requests, request_file)
    saved_history, history_message = save_status_history(history, history_file)
    if saved_requests and saved_history:
        print("Changes were saved to the CSV files.")
        return
    if not saved_requests:
        print(f"Warning: {request_message}")
    if not saved_history:
        print(f"Warning: {history_message}")


def _create_request(
    requests: dict[str, dict[str, str]],
    history: list[dict[str, str]],
    request_file: Path,
    history_file: Path,
) -> None:
    """Collect a new complaint, check for duplicates, then save it."""
    print()
    print("Create a new request")
    print("--------------------")

    category = _prompt_from_list("Select a category:", CATEGORIES, allow_other=True)
    if category is None or category == "":
        print("Request creation was cancelled.")
        return

    location = _prompt_required("Enter location")
    if location is None or location == "":
        print("Request creation was cancelled.")
        return

    description = _prompt_required(
        "Enter a description of the problem (at least 10 characters)",
        minimum_length=10,
    )
    if description is None or description == "":
        print("Request creation was cancelled.")
        return

    impact = _prompt_from_list("Select impact (how many people are affected):", IMPACT_LEVELS)
    if impact is None or impact == "":
        print("Request creation was cancelled.")
        return

    urgency = _prompt_from_list("Select urgency (how quickly it needs attention):", URGENCY_LEVELS)
    if urgency is None or urgency == "":
        print("Request creation was cancelled.")
        return

    print()
    print(explain_priority(impact, urgency))

    duplicate_id = find_potential_duplicate(requests, category, location, description)
    if duplicate_id:
        print()
        print(f"A similar unresolved request already exists: {duplicate_id}")
        existing = requests[duplicate_id]
        print(f"  Status: {existing.get('status', '')}")
        print(f"  Location: {existing.get('location', '')}")
        print(f"  Description: {existing.get('description', '')}")
        confirmed = _prompt_yes_no("Do you still want to create a new request?")
        if confirmed is None or not confirmed:
            print("The new request was not created.")
            return

    success, message, record = add_request(
        requests,
        category,
        location,
        description,
        impact,
        urgency,
        history=history,
    )
    print()
    print(message)
    if success and record is not None:
        _display_request_detail(record)
        _save_all(requests, history, request_file, history_file)


def _search_and_filter(requests: dict[str, dict[str, str]]) -> None:
    """Show the search submenu and display matching requests."""
    while True:
        print()
        print("Search and filter")
        print("-----------------")
        for key, label in SEARCH_MENU_OPTIONS.items():
            print(f"{key}. {label}")

        choice = _prompt_text("Enter your choice")
        if choice is None or choice == "0":
            return
        if choice == "1":
            request_id = _prompt_text("Enter request ID")
            if request_id is None:
                return
            matches = search_requests(requests, request_id=request_id)
            _show_search_results(matches)
            if len(matches) == 1:
                _display_request_detail(matches[0])
        elif choice == "2":
            category = _prompt_from_list("Select a category:", CATEGORIES, allow_other=True)
            if category is None or category == "":
                continue
            _show_search_results(search_requests(requests, category=category))
        elif choice == "3":
            priority = _prompt_from_list("Select a priority:", PRIORITY_LEVELS)
            if priority is None or priority == "":
                continue
            _show_search_results(search_requests(requests, priority=priority))
        elif choice == "4":
            location = _prompt_text("Enter location text to find")
            if location is None:
                return
            _show_search_results(search_requests(requests, location=location))
        elif choice == "5":
            status = _prompt_from_list("Select a status:", STATUS_LEVELS)
            if status is None or status == "":
                continue
            _show_search_results(search_requests(requests, status=status))
        elif choice == "6":
            _combined_filter(requests)
        elif choice == "7":
            _display_request_table(list(requests.values()), "All requests")
        else:
            print("That was not a valid search choice. Please try again.")


def _combined_filter(requests: dict[str, dict[str, str]]) -> None:
    """Ask for several optional filters and apply them together."""
    print()
    print("Leave a field blank to skip that filter.")
    request_id = _prompt_text("Request ID")
    category = _prompt_text("Category")
    priority = _prompt_text("Priority")
    location = _prompt_text("Location")
    status = _prompt_text("Status")
    if None in {request_id, category, priority, location, status}:
        return
    matches = search_requests(
        requests,
        request_id=request_id or None,
        category=category or None,
        priority=priority or None,
        location=location or None,
        status=status or None,
    )
    _show_search_results(matches)


def _show_search_results(matches: list[dict[str, str]]) -> None:
    """Display matches or a clear no-result message."""
    if not matches:
        print("No matching requests were found.")
        return
    _display_request_table(matches, f"Matching requests ({len(matches)})")


def _update_request_status(
    requests: dict[str, dict[str, str]],
    history: list[dict[str, str]],
    request_file: Path,
    history_file: Path,
) -> None:
    """Ask for an ID and a new status, then apply a valid change."""
    print()
    print("Update request status")
    print("---------------------")
    request_id = _prompt_required("Enter request ID")
    if request_id is None or request_id == "":
        print("Status update was cancelled.")
        return

    matches = search_requests(requests, request_id=request_id)
    if not matches:
        print(f"No request was found with ID {request_id}.")
        return

    record = matches[0]
    print()
    print("Current request:")
    _display_request_detail(record)
    print("Normal workflow: Submitted -> Under Review -> In Progress -> Resolved")
    print("A resolved request may be reopened only to Under Review, with a reason.")

    new_status = _prompt_from_list("Select the new status:", STATUS_LEVELS)
    if new_status is None or new_status == "":
        print("Status update was cancelled.")
        return

    reason = _prompt_text("Enter a reason (required when reopening; press Enter to skip)")
    if reason is None:
        print("Status update was cancelled.")
        return

    success, message, _history_record = update_status(
        requests,
        record["request_id"],
        new_status,
        reason=reason,
        history=history,
    )
    print()
    print(message)
    if success:
        _display_request_detail(requests[record["request_id"]])
        _save_all(requests, history, request_file, history_file)


def _show_overdue(requests: dict[str, dict[str, str]]) -> None:
    """Display unresolved requests that have passed their priority deadline."""
    overdue = find_overdue_requests(requests)
    print()
    print("Overdue requests")
    print("----------------")
    if not overdue:
        print("There are no overdue unresolved requests.")
        return

    print(
        f"{'ID':<22} {'Priority':<10} {'Status':<14} {'Created':<20} "
        f"{'Age (days)':>10} {'Threshold':>10} {'Days overdue':>13}"
    )
    print("-" * 103)
    for item in overdue:
        print(
            f"{str(item['request_id']):<22} "
            f"{str(item['priority']):<10} "
            f"{str(item['status']):<14} "
            f"{str(item['created_at']):<20} "
            f"{float(item['age_days']):>10.1f} "
            f"{float(item['threshold_days']):>10.0f} "
            f"{float(item['days_overdue']):>13.1f}"
        )


def _show_summary(requests: dict[str, dict[str, str]]) -> None:
    """Display management counts and average resolution time."""
    summary = summarize_requests(requests)
    average = summary["average_resolution_days"]
    average_text = "Not available" if average is None else f"{float(average):.2f} days"

    print()
    print("================================================")
    print(" MANAGEMENT SUMMARY")
    print("================================================")
    print(f"Total requests:              {summary['total']}")
    print(f"Unresolved requests:         {summary['unresolved']}")
    print(f"Resolved requests:           {summary['resolved']}")
    print(f"Overdue requests:            {summary['overdue']}")
    print(f"High-priority requests:      {summary['high_priority']}")
    print(f"Critical-priority requests:  {summary['critical_priority']}")
    print(f"Average resolution time:     {average_text}")
    _print_counts("Counts by category", summary["by_category"])
    _print_counts("Counts by status", summary["by_status"])
    _print_counts("Counts by priority", summary["by_priority"])


def _print_counts(title: str, counts: dict[str, int]) -> None:
    """Print a small count table, or '(none)' when there are no values."""
    print()
    print(f"{title}:")
    if not counts:
        print("  (none)")
        return
    for key in sorted(counts.keys()):
        print(f"  {key}: {counts[key]}")


def _show_history(
    history: list[dict[str, str]],
    requests: dict[str, dict[str, str]],
) -> None:
    """Show all history or the history of one request ID."""
    print()
    print("Status history")
    print("--------------")
    if not history:
        print("No status-history records are stored yet.")
        return

    request_id = _prompt_text("Enter a request ID, or press Enter to view all history")
    if request_id is None:
        return
    rows = history_for_request(history, request_id) if request_id else history
    if request_id and request_id not in requests and not rows:
        print("No matching requests were found.")
        return
    if not rows:
        print("No status-history records are stored for that request.")
        return

    print(
        f"{'Request ID':<22} {'Old status':<14} {'New status':<14} "
        f"{'Changed at':<20} {'Reason'}"
    )
    print("-" * 90)
    for row in rows:
        reason = row.get("reason", "") or "(none)"
        print(
            f"{row.get('request_id', ''):<22} "
            f"{(row.get('old_status') or '(new)'):<14} "
            f"{row.get('new_status', ''):<14} "
            f"{row.get('changed_at', ''):<20} "
            f"{reason}"
        )


def _display_request_table(records: list[dict[str, str]], title: str) -> None:
    """Print requests in a readable table without external packages."""
    print()
    print(title)
    print("-" * len(title))
    if not records:
        print("No matching requests were found.")
        return

    ordered = sorted(records, key=lambda item: item.get("request_id", ""))
    print(
        f"{'ID':<22} {'Category':<16} {'Location':<16} "
        f"{'Priority':<10} {'Status':<14} {'Created'}"
    )
    print("-" * 100)
    for record in ordered:
        print(
            f"{_fit(record.get('request_id', ''), 22):<22} "
            f"{_fit(record.get('category', ''), 16):<16} "
            f"{_fit(record.get('location', ''), 16):<16} "
            f"{_fit(record.get('priority', ''), 10):<10} "
            f"{_fit(record.get('status', ''), 14):<14} "
            f"{record.get('created_at', '')}"
        )


def _display_request_detail(record: dict[str, str]) -> None:
    """Print every stored field for one request."""
    print()
    print(f"Request ID:   {record.get('request_id', '')}")
    print(f"Category:     {record.get('category', '')}")
    print(f"Location:     {record.get('location', '')}")
    print(f"Description:  {record.get('description', '')}")
    print(f"Impact:       {record.get('impact', '')}")
    print(f"Urgency:      {record.get('urgency', '')}")
    print(f"Priority:     {record.get('priority', '')}")
    print(f"Status:       {record.get('status', '')}")
    print(f"Created at:   {record.get('created_at', '')}")
    print(f"Updated at:   {record.get('updated_at', '')}")
    print(f"Resolved at:  {record.get('resolved_at', '') or '(not resolved)'}")


def _fit(text: str, width: int) -> str:
    """Shorten a table cell so long text does not break the columns."""
    value = text or ""
    if len(value) <= width:
        return value
    if width <= 3:
        return value[:width]
    return value[: width - 3] + "..."
