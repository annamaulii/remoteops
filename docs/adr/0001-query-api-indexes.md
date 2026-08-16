# ADR 0001: Indexes for the Query API (work logs and approvals)

## Context

Week 8 added pagination totals and filters to `GET /organizations/{id}/work-logs`
and a new `GET /organizations/{id}/approvals` endpoint. Both are always scoped by
`organization_id`, and neither `work_logs.organization_id` nor `approvals`
(which had no `organization_id` column at all) had a supporting index. Every
query on these endpoints filters by organization first, so this is not a
speculative optimization — it is the query shape every request already takes.

## Evidence

Seeded a local Postgres instance with 50 organizations, ~4,500 work logs for
the target organization (225,000 rows total), and one decided approval per
non-`submitted` work log (~150,000 rows), then ran `EXPLAIN (ANALYZE, BUFFERS)`
for the exact query shape each endpoint issues.

**`work_logs`, filtered and ordered by `(organization_id, work_date)`:**

| | Before (no index) | After (`ix_work_logs_org_date`) |
|---|---|---|
| Plan | Parallel Seq Scan + sort | Index Scan (backward) |
| Buffers | 3,971 | 25 |
| Execution time | 7.98 ms | 0.11 ms |

**`approvals`, listed for one organization** (originally required a join
through `work_logs`/`leave_requests` since `approvals` had no
`organization_id`):

| | Join through `work_logs` (Hash Join) | Forced Nested Loop | Denormalized `organization_id` + `ix_approvals_org_created` |
|---|---|---|---|
| Buffers | 3,416 | 18,093 | 1,791 |
| Execution time | 24.8 ms | 37.2 ms | 2.1 ms |

The join-based approach was tried first and was not adequate at this scale
even with the new `work_logs` index — Postgres has no way to avoid a full
scan of `approvals` when the only path to the organization is through a join,
and forcing a nested loop (`enable_seqscan = off`) made it worse, not better.

## Decision

1. Add a composite index `ix_work_logs_org_date` on
   `work_logs (organization_id, work_date)`.
2. Add `approvals.organization_id` (backfilled from the parent work log or
   leave request via the existing `approval_target_exclusive` XOR invariant,
   then made `NOT NULL` with a `CASCADE` foreign key), plus a composite index
   `ix_approvals_org_created` on `approvals (organization_id, created_at)`.

Both indexes are plain ascending composites — Postgres serves the `DESC`
`ORDER BY` used by both endpoints via a backward index scan at the same cost,
so no `DESC` index modifier is needed (verified directly in the evidence run).

No index was added to `leave_requests`; this PR does not add new filters
there and the table has no measured query-plan problem to justify one.

## Consequences

- `approvals` now carries `organization_id` directly. It is set by the two
  decision endpoints from the same organization-scoped path parameter already
  used to validate the target work log/leave request, so it cannot diverge
  from the parent's organization in normal operation.
- Migration `5297680f8920` backfills existing rows; both indexes and the new
  column/constraint have verified `upgrade`/`downgrade` paths.
