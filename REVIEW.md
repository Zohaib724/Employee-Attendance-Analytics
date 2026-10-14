# Starter review

| # | Where | Defect | Concrete symptom/test | Fix in revised `app/main.py` |
|---|---|---|---|---|
| 1 | MongoClient setup | The starter defaulted to a local URI and did not test database availability in `/health`. | Stop MongoDB and `/health` still returned 200. | Environment variables remain configurable; `/health` pings MongoDB and returns 503 on failure. |
| 2 | `compute_late_minutes` | Used a naive timestamp and did not consistently normalize IST/UTC. | Same instant interpreted under different host time zones can produce different lateness. | Convert epoch milliseconds to UTC and calculate against the IST shift start. |
| 3 | `compute_late_minutes` | Late calculation used a simple date replacement, which fails around overnight shifts and has boundary subtleties. | Punch-in at 09:40:00 vs 09:40:01 for a 09:30 shift. | Enforce the strict 10-minute grace rule and whole-second instants. |
| 4 | `compute_work_hours` | Python `round` uses bankers' rounding in tie cases, not the required decimal half-up rule. | Durations exactly halfway between hundredths. | Use `Decimal` with `ROUND_HALF_UP`. |
| 5 | `compute_overtime` | Always constructed shift end on the same date and did not correctly handle overnight shifts or the 30-minute threshold. | 22:00–06:00 shift and punch-out after midnight. | Resolve overnight shift end on the following day; only count overtime at 30 minutes or more. |
| 6 | `GET /health` | Returned success without checking MongoDB. | Database unavailable but readiness probe returned 200. | Execute MongoDB ping and return 503 on failure. |
| 7 | `POST /employees` | Duplicate check then insert is a race; created timestamp was naive and response did not convert it to epoch milliseconds. | Parallel duplicate employee creates or timestamp response validation. | Unique database index handles races; server timestamp is UTC and API values are milliseconds. |
| 8 | `GET /employees` | Skip calculation used `page * page_size`, total ignored the filter, and results were not sorted. | Page 1 omitted first page; filtered department total was wrong. | Use `(page-1)*page_size`, filtered count, and `emp_code` ascending sort. |
| 9 | `POST /attendance/punch-in` | Missing-employee check was absent; timestamps used host-local time; falsey `punched_at=0` silently became now; check-then-insert was unsafe. | Unknown employee or concurrent requests. | Validate employee and timestamp; derive IST attendance date; unique `(emp_code,date)` index enforces one record. |
| 10 | `POST /attendance/punch-in` | It returned a synthetic `id`, contrary to the natural-key model, and did not normalize API timestamps. | Response unexpectedly exposes `id` or BSON values. | Return the contract fields and epoch milliseconds; do not expose Mongo `_id`. |
| 11 | `GET /attendance` | Loaded the whole collection into Python and counted only after fetching; pagination and sorting were in memory. | Large collection becomes slow and memory-heavy. | Apply filters, indexed sort, skip/limit and `count_documents` in MongoDB. |
| 12 | Validation across endpoints | Starter had no strict timestamp, date, status, or pagination validation. | Invalid seconds timestamp, malformed date, page 0, or unknown status. | Pydantic and explicit contract validation return 422. |
| 13 | Startup | No indexes were created. | Duplicate natural keys and collection scans at scale. | Create idempotent unique and query-supporting indexes at startup. |

## Reviewed and retained

- `emp_code` is used as the business identifier, not MongoDB `_id`.
- Attendance date is a calendar string, while instants are BSON datetimes internally.
- MongoDB collections remain `employees` and `attendance_logs`, as specified in `DATA_MODEL.md`.
