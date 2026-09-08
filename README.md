# Community Complaint and Service Request Tracker

A menu-driven command-line application for recording community complaints and service requests, assigning a transparent priority, tracking valid status changes, and producing a management summary.

This is a beginner-level Python project. It uses only the Python standard library: no Django, Flask, pandas, databases, or third-party packages.

## Project overview

Small offices often keep complaints in paper notes or unstructured spreadsheets. That makes it hard to know which jobs are urgent, which ones are overdue, and whether a status change is valid.

This program:

- Records a complaint or service request.
- Gives it a unique ID.
- Stores it permanently in CSV files.
- Calculates Low, Medium, High, or Critical priority from impact and urgency.
- Lets staff search, filter, update status, and review overdue work.
- Keeps a full status-change history.
- Survives invalid typing and missing files without crashing.

## Intended users

- Small organizations
- University campus offices
- Residential community desks
- Municipal or local service teams

No programming knowledge is required to use the menus.

## Main features

1. Create a new request with category, location, description, impact, and urgency.
2. Generate a unique ID in the form `CSR-YYYYMMDD-0001`.
3. Assign priority from a published score table.
4. Warn about possible duplicate unresolved complaints before saving.
5. Search by ID and filter by category, priority, location, status, or a combination of those fields.
6. Allow only valid status changes.
7. Reopen a resolved request only with a written reason.
8. List overdue unresolved requests using priority-based deadlines.
9. Show a management summary, including average resolution time.
10. Save every create and update immediately to CSV.

## Technology and Python concepts used

- Python 3.10 or newer
- Dictionaries keyed by request ID
- Lists of status-history records
- Sets of allowed status transitions
- Functions, loops, and conditionals
- The built-in `csv`, `datetime`, `pathlib`, and `unittest` modules
- Exception handling with `try` and `except`
- Multiple modules (`logic.py`, `storage.py`, `ui.py`)
- Type hints where they make signatures easier to read

## Project structure

```
community_complaint_tracker/
├── main.py
├── complaint_tracker/
│   ├── __init__.py
│   ├── logic.py
│   ├── storage.py
│   └── ui.py
├── data/
│   ├── requests.csv
│   └── status_history.csv
├── tests/
│   ├── __init__.py
│   └── test_tracker.py
├── docs/
│   └── flowcharts.md
├── README.md
├── REPORT.md
└── .gitignore
```

- `main.py` is the entry point. It imports `run_app` from the UI module.
- `logic.py` contains ID generation, priority, search, status rules, overdue checks, and summaries.
- `storage.py` reads and writes CSV files.
- `ui.py` prints menus and asks for input.

## Priority-scoring rules

Impact and urgency each receive a score:

| Level  | Score |
|--------|-------|
| Low    | 1     |
| Medium | 2     |
| High   | 3     |

`priority score = impact score + urgency score`

| Total score | Assigned priority |
|-------------|-------------------|
| 2 or 3      | Low               |
| 4           | Medium            |
| 5           | High              |
| 6           | Critical          |

Critical is assigned only when both impact and urgency are High.

Example:

```
Impact: High (3)
Urgency: Medium (2)
Total score: 5
Assigned priority: High
```

## Status-transition rules

Normal workflow:

`Submitted → Under Review → In Progress → Resolved`

Allowed normal changes:

- Submitted → Under Review
- Under Review → In Progress
- In Progress → Resolved

The program rejects:

- Skipping a stage
- Moving backward, except for the reopen rule below
- Changing to the current status
- Updating an unknown request ID
- Any unknown status name

## Reopening rule

A resolved request may be reopened only as:

`Resolved → Under Review`

The user must enter a non-empty reason of at least five characters. This is the only justified backward transition. Reopening clears `resolved_at`.

## Duplicate-handling rule

Before a new complaint is saved, the program looks for an unresolved request whose normalized category, location, and description match. Normalization ignores capitalization and extra spaces.

If a possible duplicate is found:

- The existing request ID is shown.
- The user is asked whether to continue.
- Nothing is deleted or merged automatically.
- If the user declines, the program returns to the menu.
- If the user confirms, a new unique ID is created.

Resolved requests are not treated as duplicates, because the same problem can return later.

## Overdue thresholds

A request is overdue only if it is still unresolved and its age is greater than:

| Priority | Overdue after |
|----------|----------------|
| Critical | 1 day          |
| High     | 3 days         |
| Medium   | 7 days         |
| Low      | 14 days        |

Resolved complaints never appear as overdue.

## CSV field descriptions

`data/requests.csv`

| Field        | Meaning                                      |
|--------------|----------------------------------------------|
| request_id   | Unique ID, for example CSR-20260825-0001     |
| category     | Road, Water, Electricity, or a custom value  |
| location     | Where the problem was observed               |
| description  | Details of the complaint                     |
| impact       | Low, Medium, or High                         |
| urgency      | Low, Medium, or High                         |
| priority     | Low, Medium, High, or Critical               |
| created_at   | Date and time the request was created        |
| status       | Current workflow status                      |
| updated_at   | Date and time of the last change             |
| resolved_at  | Date and time of resolution, or blank        |

`data/status_history.csv`

| Field      | Meaning                                      |
|------------|----------------------------------------------|
| request_id | The request that changed                     |
| old_status | Previous status, blank when first created    |
| new_status | Status after the change                      |
| changed_at | Date and time of the change                  |
| reason     | Optional note; required when reopening       |

The `csv` module quotes fields that contain commas, so a description such as `Hole, cracks, and water` is stored safely.

## Installation instructions

1. Install Python 3.10 or newer.
2. Download or copy the `community_complaint_tracker` folder.
3. No extra packages need to be installed.

## How to run the program

On this Mac, use `python3` (`python` and `py` are not installed):

```bash
cd community_complaint_tracker
python3 main.py
```

You can also start it from the parent `Complaint Tracker` folder:

```bash
python3 main.py
```

On some Windows systems use `py main.py` or `python main.py`.

## How to run tests

From the `community_complaint_tracker` folder:

```bash
python -m unittest discover -s tests -v
```

or:

```bash
python3 -m unittest discover -s tests -v
```

Tests write only to temporary folders. They do not change `data/requests.csv` or `data/status_history.csv`.

## Example user interaction

```
================================================
 COMMUNITY COMPLAINT AND SERVICE REQUEST TRACKER
================================================
1. Create a new request
2. Search and filter requests
3. Update request status
4. View all requests
5. View overdue requests
6. View management summary
7. View status history
0. Exit
Enter your choice: 1

Select a category:
  1. Road
  ...
Enter the number: 1
Enter location: Block A
Enter a description of the problem (at least 10 characters): Large pothole near the main gate

Select impact (how many people are affected):
  1. Low
  2. Medium
  3. High
Enter the number: 3

Select urgency (how quickly it needs attention):
  1. Low
  2. Medium
  3. High
Enter the number: 3

Impact: High (3)
Urgency: High (3)
Total score: 6
Assigned priority: Critical

Request CSR-20260825-0001 was created with Critical priority.
Changes were saved to the CSV files.
```

If the same unresolved problem is entered again, the program shows the existing ID and asks whether to continue.

## Known limitations

- The program is designed for one person using it at a time.
- There are no user accounts or login roles.
- Photos and map pins cannot be attached.
- Overdue age uses calendar time, not working days.
- There are no email or SMS reminders.
- CSV files are simple storage, not a multi-user database.

## Possible future improvements

- Staff and supervisor roles
- Working-day overdue rules
- Optional photo or document attachments
- Printed weekly reports
- Email alerts for Critical requests
- A simple desktop or web front end that still uses these same rules
