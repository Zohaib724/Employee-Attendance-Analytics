# Design decisions

1. **Indexes.** A unique `employees.emp_code` index prevents duplicate employee codes. Department/code and department/join-date indexes support employee lists and department headcounts; a separate `joined_on` index supports unfiltered period headcounts. A unique `(emp_code, date)` index enforces one attendance record per employee/day. Date/employee, employee/date/status, date/status, and employee/punch-in indexes support list sorting, filtered monthly queries, and finding the most recent punch-in. Indexes are created idempotently at startup.

2. **Punch-in race.** Requests can both pass the employee lookup, but only one insert can satisfy the unique `(emp_code, date)` index. MongoDB raises `DuplicateKeyError` for the loser, which becomes HTTP 409; the winner receives 201. A check-then-insert by itself is not race-safe.

3. **Ties.** The leaderboard uses MongoDB `$rank`, so tied totals share a rank and the next rank is skipped. The limit is applied to rank, not row position, so every employee tied at a qualifying cutoff is included. Results are then ordered by late minutes and employee code.

4. **Headcount.** The department summary starts from employees who joined on or before the period end and looks up their attendance logs. Employees with no logs still count; later joiners do not. A department with no qualifying employees is omitted.

5. **100x data.** I would inspect execution plans and workload metrics, tune compound indexes to actual filters, set operational timeouts and pool limits, load-test concurrent writes, and consider pre-aggregated monthly analytics if latency measurements justified the extra complexity.
