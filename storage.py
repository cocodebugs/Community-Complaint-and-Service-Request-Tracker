"""CSV file operations for complaints and status history.

This module is responsible only for reading and writing files. It does not
decide priority, validate status changes, or display menus.
"""

from __future__ import annotations

import csv
from pathlib import Path

# Paths are built from this file's location so the program works even if
# it is started from a different working directory.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = _PROJECT_ROOT / "data"
DEFAULT_REQUESTS_PATH = DEFAULT_DATA_DIR / "requests.csv"
DEFAULT_HISTORY_PATH = DEFAULT_DATA_DIR / "status_history.csv"

REQUEST_FIELDS = [
    "request_id",
    "category",
    "location",
    "description",
    "impact",
    "urgency",
    "priority",
    "created_at",
    "status",
    "updated_at",
    "resolved_at",
]

HISTORY_FIELDS = [
    "request_id",
    "old_status",
    "new_status",
    "changed_at",
    "reason",
]


def initialize_data_files(
    requests_path: Path | str | None = None,
    history_path: Path | str | None = None,
) -> list[str]:
    """Create the data directory and CSV files with headers if needed.

    Parameters:
        requests_path: Optional path to the requests CSV file.
        history_path: Optional path to the status-history CSV file.

    Returns:
        A list of human-readable messages describing what was created.
    """
    messages: list[str] = []
    requests_file = Path(requests_path) if requests_path else DEFAULT_REQUESTS_PATH
    history_file = Path(history_path) if history_path else DEFAULT_HISTORY_PATH

    try:
        requests_file.parent.mkdir(parents=True, exist_ok=True)
        history_file.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        messages.append(f"Could not create the data folder: {error}")
        return messages

    if not requests_file.exists() or requests_file.stat().st_size == 0:
        if _write_header_file(requests_file, REQUEST_FIELDS):
            messages.append(f"Prepared request file: {requests_file}")
        else:
            messages.append(f"Could not prepare request file: {requests_file}")

    if not history_file.exists() or history_file.stat().st_size == 0:
        if _write_header_file(history_file, HISTORY_FIELDS):
            messages.append(f"Prepared history file: {history_file}")
        else:
            messages.append(f"Could not prepare history file: {history_file}")

    return messages


def load_requests(filepath: Path | str | None = None) -> tuple[dict[str, dict[str, str]], list[str]]:
    """Load complaints from CSV into a dictionary keyed by request ID.

    Missing or empty files are created with headers. Malformed rows are
    skipped so one bad line cannot crash the program.

    Parameters:
        filepath: Optional CSV path. Uses the default project data file if omitted.

    Returns:
        A tuple of (requests dictionary, warning messages).
    """
    path = Path(filepath) if filepath else DEFAULT_REQUESTS_PATH
    warnings: list[str] = []
    requests: dict[str, dict[str, str]] = {}

    try:
        missing_or_empty = (not path.exists()) or path.stat().st_size == 0
        if missing_or_empty:
            initialize_data_files(requests_path=path, history_path=path.parent / "status_history.csv")
            if not path.exists():
                warnings.append(f"Request file was missing and could not be created: {path}")
                return {}, warnings
            warnings.append("Request file was missing or empty and has been created.")
            if path.stat().st_size == 0 or _file_has_only_header(path):
                return {}, warnings

        with path.open("r", newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            if not reader.fieldnames:
                warnings.append("The request file has no header row. Starting with no records.")
                return {}, warnings

            missing_columns = [name for name in REQUEST_FIELDS if name not in reader.fieldnames]
            if missing_columns:
                warnings.append(
                    "The request file is missing columns: "
                    + ", ".join(missing_columns)
                    + ". Some data may be skipped."
                )

            for row_number, row in enumerate(reader, start=2):
                record, row_warning = _row_to_request(row, row_number)
                if row_warning:
                    warnings.append(row_warning)
                if record is None:
                    continue
                request_id = record["request_id"]
                if request_id in requests:
                    warnings.append(
                        f"Skipped duplicate request ID on row {row_number}: {request_id}."
                    )
                    continue
                requests[request_id] = record

    except PermissionError:
        warnings.append(f"Permission denied when reading the request file: {path}")
        return {}, warnings
    except OSError as error:
        warnings.append(f"Could not read the request file: {error}")
        return {}, warnings

    return requests, warnings


def save_requests(
    requests: dict[str, dict[str, str]],
    filepath: Path | str | None = None,
) -> tuple[bool, str]:
    """Save all complaints to CSV.

    Data is written to a temporary file first, then renamed into place so a
    failed write is less likely to destroy the previous file.

    Parameters:
        requests: Dictionary of complaint records keyed by request ID.
        filepath: Optional CSV path.

    Returns:
        A tuple of (success flag, message).
    """
    path = Path(filepath) if filepath else DEFAULT_REQUESTS_PATH
    return _save_rows(
        path=path,
        fieldnames=REQUEST_FIELDS,
        rows=[_request_to_row(requests[key]) for key in sorted(requests.keys())],
        label="request",
    )


def load_status_history(
    filepath: Path | str | None = None,
) -> tuple[list[dict[str, str]], list[str]]:
    """Load status-history records from CSV.

    Parameters:
        filepath: Optional CSV path.

    Returns:
        A tuple of (history list, warning messages).
    """
    path = Path(filepath) if filepath else DEFAULT_HISTORY_PATH
    warnings: list[str] = []
    history: list[dict[str, str]] = []

    try:
        if not path.exists() or path.stat().st_size == 0:
            initialize_data_files(requests_path=path.parent / "requests.csv", history_path=path)
            return [], ["History file was missing or empty and has been created."]

        with path.open("r", newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            if not reader.fieldnames:
                warnings.append("The history file has no header row. Starting with no records.")
                return [], warnings

            for row_number, row in enumerate(reader, start=2):
                record, row_warning = _row_to_history(row, row_number)
                if row_warning:
                    warnings.append(row_warning)
                if record is not None:
                    history.append(record)

    except PermissionError:
        warnings.append(f"Permission denied when reading the history file: {path}")
        return [], warnings
    except OSError as error:
        warnings.append(f"Could not read the history file: {error}")
        return [], warnings

    return history, warnings


def save_status_history(
    history: list[dict[str, str]],
    filepath: Path | str | None = None,
) -> tuple[bool, str]:
    """Save status-history records to CSV.

    Parameters:
        history: List of status-change dictionaries.
        filepath: Optional CSV path.

    Returns:
        A tuple of (success flag, message).
    """
    path = Path(filepath) if filepath else DEFAULT_HISTORY_PATH
    rows = [_history_to_row(item) for item in history]
    return _save_rows(path=path, fieldnames=HISTORY_FIELDS, rows=rows, label="history")


def _write_header_file(path: Path, fieldnames: list[str]) -> bool:
    """Write a CSV file that contains only a header row."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
        return True
    except OSError:
        return False


def _file_has_only_header(path: Path) -> bool:
    """Return True if the CSV file has no data rows."""
    try:
        with path.open("r", newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            return next(reader, None) is None
    except OSError:
        return True


def _save_rows(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, str]],
    label: str,
) -> tuple[bool, str]:
    """Write rows to CSV using a temporary file, then replace the target."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        with temporary_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        temporary_path.replace(path)
        return True, f"Saved {len(rows)} {label} record(s)."
    except PermissionError:
        return False, f"Permission denied when saving the {label} file: {path}"
    except OSError as error:
        return False, f"Could not save the {label} file: {error}"


def _row_to_request(row: dict[str, str | None], row_number: int) -> tuple[dict[str, str] | None, str | None]:
    """Convert one CSV row into a request record, or skip it if it is unusable."""
    cleaned = {key: (row.get(key) or "").strip() for key in REQUEST_FIELDS}
    if not cleaned["request_id"]:
        return None, f"Skipped malformed request row {row_number}: missing request_id."
    if not cleaned["status"]:
        return None, f"Skipped malformed request row {row_number}: missing status."
    return cleaned, None


def _request_to_row(record: dict[str, str]) -> dict[str, str]:
    """Convert a request record into a CSV row with every required column."""
    return {field: record.get(field, "") for field in REQUEST_FIELDS}


def _row_to_history(row: dict[str, str | None], row_number: int) -> tuple[dict[str, str] | None, str | None]:
    """Convert one CSV row into a history record, or skip it if it is unusable."""
    cleaned = {key: (row.get(key) or "").strip() for key in HISTORY_FIELDS}
    if not cleaned["request_id"] or not cleaned["new_status"]:
        return None, f"Skipped malformed history row {row_number}: missing required fields."
    return cleaned, None


def _history_to_row(record: dict[str, str]) -> dict[str, str]:
    """Convert a history record into a CSV row with every required column."""
    return {field: record.get(field, "") for field in HISTORY_FIELDS}
