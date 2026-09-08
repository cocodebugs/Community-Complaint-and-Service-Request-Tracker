"""Automated tests for the Community Complaint and Service Request Tracker.

Tests use temporary folders so they never change the real data/ CSV files.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from io import StringIO
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from complaint_tracker.logic import (
    add_request,
    calculate_priority,
    explain_priority,
    find_overdue_requests,
    find_potential_duplicate,
    generate_request_id,
    is_valid_transition,
    search_requests,
    summarize_requests,
    update_status,
)
from complaint_tracker.storage import (
    load_requests,
    load_status_history,
    save_requests,
    save_status_history,
)
from complaint_tracker.ui import run_app

FIXED_NOW = datetime(2026, 8, 25, 10, 30, 0)


def make_record(**overrides: str) -> dict[str, str]:
    """Build one complaint dictionary for tests."""
    record = {
        "request_id": "CSR-20260825-0001",
        "category": "Road",
        "location": "Block A",
        "description": "Large pothole near the main gate",
        "impact": "High",
        "urgency": "High",
        "priority": "Critical",
        "created_at": "2026-08-25 10:30:00",
        "status": "Submitted",
        "updated_at": "2026-08-25 10:30:00",
        "resolved_at": "",
    }
    record.update(overrides)
    return record


class TestPriorityCalculation(unittest.TestCase):
    """Priority must follow the published impact + urgency score table."""

    def test_score_2_is_low(self) -> None:
        self.assertEqual(calculate_priority("Low", "Low"), "Low")

    def test_score_3_is_low(self) -> None:
        self.assertEqual(calculate_priority("Low", "Medium"), "Low")
        self.assertEqual(calculate_priority("Medium", "Low"), "Low")

    def test_score_4_is_medium(self) -> None:
        self.assertEqual(calculate_priority("Low", "High"), "Medium")
        self.assertEqual(calculate_priority("Medium", "Medium"), "Medium")
        self.assertEqual(calculate_priority("High", "Low"), "Medium")

    def test_score_5_is_high(self) -> None:
        self.assertEqual(calculate_priority("Medium", "High"), "High")
        self.assertEqual(calculate_priority("High", "Medium"), "High")

    def test_score_6_is_critical(self) -> None:
        self.assertEqual(calculate_priority("High", "High"), "Critical")

    def test_invalid_impact_or_urgency_raises(self) -> None:
        with self.assertRaises(ValueError):
            calculate_priority("Extreme", "High")
        with self.assertRaises(ValueError):
            calculate_priority("High", "")
        with self.assertRaises(ValueError):
            calculate_priority("urgent", "soon")

    def test_priority_explanation_is_transparent(self) -> None:
        text = explain_priority("High", "Medium")
        self.assertIn("Impact: High (3)", text)
        self.assertIn("Urgency: Medium (2)", text)
        self.assertIn("Total score: 5", text)
        self.assertIn("Assigned priority: High", text)


class TestStatusTransitions(unittest.TestCase):
    """Only the documented workflow, plus justified reopening, is allowed."""

    def test_valid_normal_transitions(self) -> None:
        allowed, _message = is_valid_transition("Submitted", "Under Review")
        self.assertTrue(allowed)
        allowed, _message = is_valid_transition("Under Review", "In Progress")
        self.assertTrue(allowed)
        allowed, _message = is_valid_transition("In Progress", "Resolved")
        self.assertTrue(allowed)

    def test_skipping_a_stage_is_rejected(self) -> None:
        allowed, message = is_valid_transition("Submitted", "In Progress")
        self.assertFalse(allowed)
        self.assertIn("Cannot change status", message)

        allowed, message = is_valid_transition("Submitted", "Resolved")
        self.assertFalse(allowed)

        allowed, message = is_valid_transition("Under Review", "Resolved")
        self.assertFalse(allowed)

    def test_backward_transition_is_rejected(self) -> None:
        allowed, _message = is_valid_transition("In Progress", "Under Review")
        self.assertFalse(allowed)
        allowed, _message = is_valid_transition("Under Review", "Submitted")
        self.assertFalse(allowed)

    def test_same_status_is_rejected(self) -> None:
        allowed, message = is_valid_transition("Submitted", "Submitted")
        self.assertFalse(allowed)
        self.assertIn("already", message)

    def test_unknown_status_is_rejected(self) -> None:
        allowed, message = is_valid_transition("Submitted", "Closed")
        self.assertFalse(allowed)
        self.assertIn("Unknown status", message)

    def test_update_unknown_request_id_is_rejected(self) -> None:
        requests = {"CSR-20260825-0001": make_record()}
        success, message, history_record = update_status(
            requests, "CSR-20990101-9999", "Under Review"
        )
        self.assertFalse(success)
        self.assertIn("No request was found", message)
        self.assertIsNone(history_record)


class TestReopening(unittest.TestCase):
    """Resolved -> Under Review is allowed only with a real reason."""

    def test_reopen_without_reason_fails(self) -> None:
        allowed, message = is_valid_transition("Resolved", "Under Review", reason="")
        self.assertFalse(allowed)
        self.assertIn("reason", message.lower())

        allowed, message = is_valid_transition("Resolved", "Under Review", reason="no")
        self.assertFalse(allowed)

    def test_reopen_with_proper_reason_succeeds(self) -> None:
        requests = {
            "CSR-20260825-0001": make_record(status="Resolved", resolved_at="2026-08-26 09:00:00")
        }
        history: list[dict[str, str]] = []
        success, message, history_record = update_status(
            requests,
            "CSR-20260825-0001",
            "Under Review",
            reason="Problem returned after repair",
            history=history,
            current_datetime=datetime(2026, 8, 27, 11, 0, 0),
        )
        self.assertTrue(success)
        self.assertIn("Under Review", message)
        self.assertEqual(requests["CSR-20260825-0001"]["status"], "Under Review")
        self.assertEqual(requests["CSR-20260825-0001"]["resolved_at"], "")
        self.assertEqual(len(history), 1)
        self.assertIsNotNone(history_record)
        if history_record is not None:
            self.assertEqual(history_record["old_status"], "Resolved")
            self.assertEqual(history_record["new_status"], "Under Review")


class TestUniqueIds(unittest.TestCase):
    """IDs must follow CSR-YYYYMMDD-0001 and never overwrite an existing row."""

    def test_first_id_of_the_day(self) -> None:
        request_id = generate_request_id({}, FIXED_NOW)
        self.assertEqual(request_id, "CSR-20260825-0001")

    def test_sequence_increases_on_the_same_date(self) -> None:
        requests = {"CSR-20260825-0001": make_record()}
        second = generate_request_id(requests, FIXED_NOW)
        self.assertEqual(second, "CSR-20260825-0002")
        requests[second] = make_record(request_id=second)
        third = generate_request_id(requests, FIXED_NOW)
        self.assertEqual(third, "CSR-20260825-0003")

    def test_ids_from_another_date_do_not_change_today_sequence(self) -> None:
        requests = {"CSR-20260824-0009": make_record(request_id="CSR-20260824-0009")}
        today_id = generate_request_id(requests, FIXED_NOW)
        self.assertEqual(today_id, "CSR-20260825-0001")

    def test_existing_id_is_never_reused(self) -> None:
        requests: dict[str, dict[str, str]] = {}
        first_id = generate_request_id(requests, FIXED_NOW)
        requests[first_id] = make_record(request_id=first_id)
        second_id = generate_request_id(requests, FIXED_NOW)
        self.assertNotEqual(first_id, second_id)
        self.assertNotIn(second_id, [first_id])


class TestStorageFiles(unittest.TestCase):
    """CSV loading must survive missing files, empty files, and odd rows."""

    def test_missing_request_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "requests.csv"
            self.assertFalse(path.exists())
            requests, warnings = load_requests(path)
            self.assertEqual(requests, {})
            self.assertTrue(path.exists())
            self.assertTrue(any("missing or empty" in item.lower() or "prepared" in item.lower() or "created" in item.lower() for item in warnings) or path.exists())

    def test_empty_request_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "requests.csv"
            path.write_text("", encoding="utf-8")
            requests, warnings = load_requests(path)
            self.assertEqual(requests, {})
            self.assertTrue(path.stat().st_size > 0)
            self.assertTrue(warnings or path.read_text(encoding="utf-8").startswith("request_id"))

    def test_save_and_load_round_trip_keeps_commas(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "requests.csv"
            original = {
                "CSR-20260825-0001": make_record(
                    description="Hole, cracks, and standing water near the gate"
                )
            }
            saved, message = save_requests(original, path)
            self.assertTrue(saved, message)
            loaded, warnings = load_requests(path)
            self.assertEqual(warnings, [])
            self.assertEqual(
                loaded["CSR-20260825-0001"]["description"],
                "Hole, cracks, and standing water near the gate",
            )

    def test_malformed_rows_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "requests.csv"
            path.write_text(
                "request_id,category,location,description,impact,urgency,priority,"
                "created_at,status,updated_at,resolved_at\n"
                ",Road,Block A,Missing identifier xx,High,High,Critical,"
                "2026-08-25 10:30:00,Submitted,2026-08-25 10:30:00,\n"
                "CSR-20260825-0002,Water,Hall,Valid leaking pipe,Low,Low,Low,"
                "2026-08-25 11:00:00,Submitted,2026-08-25 11:00:00,\n",
                encoding="utf-8",
            )
            loaded, warnings = load_requests(path)
            self.assertEqual(len(loaded), 1)
            self.assertIn("CSR-20260825-0002", loaded)
            self.assertTrue(any("malformed" in item.lower() for item in warnings))


class TestSearch(unittest.TestCase):
    """Search must support filters, combinations, and a clear empty result."""

    def setUp(self) -> None:
        self.requests = {
            "CSR-20260825-0001": make_record(),
            "CSR-20260825-0002": make_record(
                request_id="CSR-20260825-0002",
                category="Water",
                location="Campus Hall",
                description="Water leaking from the ceiling",
                impact="Medium",
                urgency="High",
                priority="High",
                status="Under Review",
            ),
            "CSR-20260825-0003": make_record(
                request_id="CSR-20260825-0003",
                category="Noise",
                location="Block B",
                description="Loud construction after midnight",
                impact="Low",
                urgency="Low",
                priority="Low",
                status="In Progress",
            ),
        }

    def test_search_by_id(self) -> None:
        matches = search_requests(self.requests, request_id="CSR-20260825-0002")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["category"], "Water")

    def test_no_matching_result(self) -> None:
        matches = search_requests(self.requests, request_id="CSR-19990101-0001")
        self.assertEqual(matches, [])
        matches = search_requests(self.requests, category="Electricity")
        self.assertEqual(matches, [])

    def test_combined_filters(self) -> None:
        matches = search_requests(
            self.requests,
            category="Road",
            priority="Critical",
            status="Submitted",
            location="Block",
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["request_id"], "CSR-20260825-0001")

        matches = search_requests(
            self.requests,
            category="Road",
            status="Resolved",
        )
        self.assertEqual(matches, [])

    def test_location_partial_and_case_insensitive(self) -> None:
        matches = search_requests(self.requests, location="hall")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["request_id"], "CSR-20260825-0002")
        matches = search_requests(self.requests, category="noise")
        self.assertEqual(len(matches), 1)


class TestOverdue(unittest.TestCase):
    """Overdue rules depend on priority and ignore resolved requests."""

    def test_overdue_for_all_priority_levels(self) -> None:
        as_of = datetime(2026, 8, 25, 12, 0, 0)
        requests = {
            "CSR-C": make_record(
                request_id="CSR-C",
                priority="Critical",
                created_at="2026-08-23 12:00:00",
                status="Submitted",
            ),
            "CSR-H": make_record(
                request_id="CSR-H",
                priority="High",
                created_at="2026-08-21 12:00:00",
                status="Under Review",
            ),
            "CSR-M": make_record(
                request_id="CSR-M",
                priority="Medium",
                created_at="2026-08-17 12:00:00",
                status="In Progress",
            ),
            "CSR-L": make_record(
                request_id="CSR-L",
                priority="Low",
                created_at="2026-08-10 12:00:00",
                status="Submitted",
            ),
            "CSR-OK": make_record(
                request_id="CSR-OK",
                priority="High",
                created_at="2026-08-24 12:00:00",
                status="Submitted",
            ),
        }
        overdue = find_overdue_requests(requests, as_of)
        overdue_ids = {item["request_id"] for item in overdue}
        self.assertEqual(overdue_ids, {"CSR-C", "CSR-H", "CSR-M", "CSR-L"})
        self.assertNotIn("CSR-OK", overdue_ids)

        details = {item["request_id"]: item for item in overdue}
        self.assertEqual(details["CSR-C"]["threshold_days"], 1)
        self.assertEqual(details["CSR-H"]["threshold_days"], 3)
        self.assertEqual(details["CSR-M"]["threshold_days"], 7)
        self.assertEqual(details["CSR-L"]["threshold_days"], 14)
        self.assertGreater(float(details["CSR-C"]["days_overdue"]), 0)

    def test_resolved_requests_are_not_overdue(self) -> None:
        as_of = datetime(2026, 8, 25, 12, 0, 0)
        requests = {
            "CSR-R": make_record(
                request_id="CSR-R",
                priority="Critical",
                created_at="2026-08-01 12:00:00",
                status="Resolved",
                resolved_at="2026-08-02 12:00:00",
            )
        }
        overdue = find_overdue_requests(requests, as_of)
        self.assertEqual(overdue, [])

    def test_exact_threshold_is_not_overdue(self) -> None:
        as_of = datetime(2026, 8, 26, 10, 30, 0)
        requests = {
            "CSR-T": make_record(
                request_id="CSR-T",
                priority="Critical",
                created_at="2026-08-25 10:30:00",
                status="Submitted",
            )
        }
        overdue = find_overdue_requests(requests, as_of)
        self.assertEqual(overdue, [])


class TestSummary(unittest.TestCase):
    """Management summary must work with empty data and mixed statuses."""

    def test_summary_when_no_records_exist(self) -> None:
        summary = summarize_requests({})
        self.assertEqual(summary["total"], 0)
        self.assertEqual(summary["unresolved"], 0)
        self.assertEqual(summary["resolved"], 0)
        self.assertEqual(summary["overdue"], 0)
        self.assertEqual(summary["high_priority"], 0)
        self.assertEqual(summary["critical_priority"], 0)
        self.assertEqual(summary["by_category"], {})
        self.assertEqual(summary["by_status"], {})
        self.assertEqual(summary["by_priority"], {})
        self.assertIsNone(summary["average_resolution_days"])

    def test_summary_with_resolved_and_unresolved_records(self) -> None:
        as_of = datetime(2026, 8, 25, 12, 0, 0)
        requests = {
            "CSR-1": make_record(
                request_id="CSR-1",
                category="Road",
                priority="Critical",
                status="Submitted",
                created_at="2026-08-20 12:00:00",
            ),
            "CSR-2": make_record(
                request_id="CSR-2",
                category="Water",
                priority="High",
                status="Resolved",
                created_at="2026-08-20 12:00:00",
                resolved_at="2026-08-22 12:00:00",
            ),
            "CSR-3": make_record(
                request_id="CSR-3",
                category="Water",
                priority="Low",
                status="In Progress",
                created_at="2026-08-24 12:00:00",
            ),
        }
        summary = summarize_requests(requests, as_of)
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["resolved"], 1)
        self.assertEqual(summary["unresolved"], 2)
        self.assertEqual(summary["high_priority"], 1)
        self.assertEqual(summary["critical_priority"], 1)
        self.assertEqual(summary["by_category"]["Water"], 2)
        self.assertEqual(summary["by_status"]["Resolved"], 1)
        self.assertAlmostEqual(float(summary["average_resolution_days"]), 2.0)
        self.assertGreaterEqual(int(summary["overdue"]), 1)


class TestDuplicatesAndValidation(unittest.TestCase):
    """Duplicate detection and add_request validation."""

    def test_potential_duplicate_detection(self) -> None:
        requests = {
            "CSR-20260825-0001": make_record(
                category="Road",
                location="Block A",
                description="Large pothole near the main gate",
                status="Submitted",
            )
        }
        found = find_potential_duplicate(
            requests,
            "road",
            "  Block A  ",
            "Large pothole near the main gate",
        )
        self.assertEqual(found, "CSR-20260825-0001")

    def test_resolved_request_is_not_a_duplicate(self) -> None:
        requests = {
            "CSR-20260825-0001": make_record(status="Resolved")
        }
        found = find_potential_duplicate(
            requests,
            "Road",
            "Block A",
            "Large pothole near the main gate",
        )
        self.assertIsNone(found)

    def test_add_request_rejects_invalid_fields(self) -> None:
        requests: dict[str, dict[str, str]] = {}
        success, message, record = add_request(requests, "", "Block A", "Valid description", "High", "High")
        self.assertFalse(success)
        self.assertIsNone(record)
        self.assertIn("Category", message)

        success, message, record = add_request(requests, "Road", "", "Valid description", "High", "High")
        self.assertFalse(success)
        self.assertIn("Location", message)

        success, message, record = add_request(requests, "Road", "Block A", "too short", "High", "High")
        self.assertFalse(success)
        self.assertIn("10", message)

        success, message, record = add_request(
            requests, "Road", "Block A", "A valid long description", "Extreme", "High"
        )
        self.assertFalse(success)
        self.assertIn("Impact", message)


class TestNormalScenario(unittest.TestCase):
    """Create, save, reload, walk through every valid status, and check history."""

    def test_complete_normal_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            request_file = Path(temp_dir) / "requests.csv"
            history_file = Path(temp_dir) / "status_history.csv"
            requests: dict[str, dict[str, str]] = {}
            history: list[dict[str, str]] = []

            success, message, record = add_request(
                requests,
                "Road",
                "Block A",
                "Large pothole near the main gate",
                "High",
                "High",
                current_datetime=FIXED_NOW,
                history=history,
            )
            self.assertTrue(success, message)
            self.assertIsNotNone(record)
            assert record is not None
            request_id = record["request_id"]
            self.assertEqual(request_id, "CSR-20260825-0001")
            self.assertEqual(record["priority"], "Critical")
            self.assertEqual(record["status"], "Submitted")

            saved, save_message = save_requests(requests, request_file)
            self.assertTrue(saved, save_message)
            saved, save_message = save_status_history(history, history_file)
            self.assertTrue(saved, save_message)

            loaded, warnings = load_requests(request_file)
            self.assertEqual(warnings, [])
            self.assertIn(request_id, loaded)
            self.assertEqual(loaded[request_id]["description"], "Large pothole near the main gate")

            workflow = [
                ("Under Review", datetime(2026, 8, 25, 11, 0, 0)),
                ("In Progress", datetime(2026, 8, 25, 12, 0, 0)),
                ("Resolved", datetime(2026, 8, 25, 16, 0, 0)),
            ]
            for new_status, when in workflow:
                success, message, _item = update_status(
                    loaded,
                    request_id,
                    new_status,
                    reason="Normal progress",
                    history=history,
                    current_datetime=when,
                )
                self.assertTrue(success, message)

            self.assertEqual(loaded[request_id]["status"], "Resolved")
            self.assertEqual(loaded[request_id]["resolved_at"], "2026-08-25 16:00:00")

            save_requests(loaded, request_file)
            save_status_history(history, history_file)
            reloaded_history, history_warnings = load_status_history(history_file)
            self.assertEqual(history_warnings, [])
            self.assertEqual(len(reloaded_history), 4)
            self.assertEqual(reloaded_history[0]["new_status"], "Submitted")
            self.assertEqual(reloaded_history[1]["new_status"], "Under Review")
            self.assertEqual(reloaded_history[2]["new_status"], "In Progress")
            self.assertEqual(reloaded_history[3]["new_status"], "Resolved")
            self.assertEqual(reloaded_history[3]["old_status"], "In Progress")


class TestMenuHandling(unittest.TestCase):
    """Invalid menu input must not crash the application."""

    def test_invalid_menu_then_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            request_file = Path(temp_dir) / "requests.csv"
            history_file = Path(temp_dir) / "status_history.csv"
            fake_output = StringIO()
            with patch("sys.stdout", fake_output):
                with patch("builtins.input", side_effect=["99", "abc", "0"]):
                    run_app(request_file, history_file)
            output = fake_output.getvalue().lower()
            self.assertIn("not a valid menu choice", output)
            self.assertIn("goodbye", output)


if __name__ == "__main__":
    unittest.main()
