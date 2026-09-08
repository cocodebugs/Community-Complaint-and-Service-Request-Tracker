#!/usr/bin/env python3
"""Entry point for the Community Complaint and Service Request Tracker.

Meaningful functions such as generate_request_id, calculate_priority,
add_request, search_requests, and save_requests live in separate modules
and are imported here through the user-interface package.
"""

from complaint_tracker.ui import run_app


def main() -> None:
    """Start the menu-driven application."""
    try:
        run_app()
    except KeyboardInterrupt:
        print("\nProgram interrupted. Goodbye.")


if __name__ == "__main__":
    main()
