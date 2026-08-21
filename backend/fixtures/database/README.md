# Database migration fixtures

These fixtures describe supported historical SQLite schemas as reviewable SQL.
Tests materialize each fixture into a temporary `library.db`; no binary database
and no developer or user data belongs in this directory.

- `empty`: a first installation with no user tables.
- `oldest-supported`: the earliest supported `movie` and `job` shape, including
  sentinel rows that exercise version 1 defaults and timestamp backfill.
- `current-unversioned`: the schema surface managed by version 1 plus current
  user-state and event tables, but without `schema_migrations`.

Each `expected.json` records the invariants that must survive an upgrade.
